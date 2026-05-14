import os
import argparse
import shutil
import glob
import sys
from src.config_loader import load_config
from src.gmx_utils import run_gmx, run_command
from src.md_utils import generate_mdp_files, run_step
from src.mol_prep import prepare_ligand, prepare_ligand_from_file
from src.top_utils import merge_complex, update_topology, setup_system, prepare_protein, handle_posre, fix_gro
from src.logger_utils import setup_logger

# Setup Global Root Logger
setup_logger()
logger = setup_logger("md_workflow")

"""
Molecular Dynamics Workflow with GROMACS Docker integration and RDKit preparation.
Supports batch processing of docking results (PDBQT files).
"""

def get_files(path, extensions):
    """Retrieves files from a path or directory with specific extensions."""
    if os.path.isfile(path):
        return [os.path.abspath(path)]
    elif os.path.isdir(path):
        files = []
        for ext in extensions:
            files.extend([os.path.abspath(f) for f in glob.glob(os.path.join(path, f"*{ext}"))])
        return files
    glob_files = glob.glob(path)
    if glob_files:
        files = []
        for f in glob_files:
            if any(f.endswith(ext) for ext in extensions):
                files.append(os.path.abspath(f))
        return files
    return []

def main():
    parser = argparse.ArgumentParser(description="Automated MD Workflow for Protein-Ligand Complexes")
    parser.add_argument("--config", "-c", default="config.json", help="Path to config file")
    parser.add_argument("--protein", "-p", nargs="+", help="Protein files (PDB/PDBQT) or directories")
    parser.add_argument("--ligand", "-l", nargs="+", help="Ligand files (SMILES/PDBQT/MOL2) or directories")
    parser.add_argument("--outdir", "-o", default="results", help="Output directory")
    parser.add_argument("--workdir", "-w", default="work", help="Working directory")
    parser.add_argument("--gpu", action="store_true", default=True, help="Enable GPU acceleration")
    parser.add_argument("--no-gpu", action="store_false", dest="gpu")
    parser.add_argument("--docker", action="store_true", default=True, help="Run via Docker")
    parser.add_argument("--no-docker", action="store_false", dest="docker")
    parser.add_argument("--image", default="nvcr.io/hpc/gromacs:2023.2", help="Docker image")
    
    args = parser.parse_args()

    host_root = os.path.dirname(os.path.abspath(__file__))
    outdir = os.path.abspath(args.outdir)
    workdir = os.path.abspath(args.workdir)
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(workdir, exist_ok=True)
    
    config_path = os.path.abspath(args.config)
    cfg = load_config(config_path) if os.path.exists(config_path) else {}
    
    # Defaults
    if "em" not in cfg: cfg["em"] = {"emtol": 1000.0, "emstep": 0.01, "nsteps": 50000}
    if "nvt" not in cfg: cfg["nvt"] = {"nsteps": 50000, "dt": 0.002, "tau_t": 0.1}
    if "npt" not in cfg: cfg["npt"] = {"nsteps": 50000, "dt": 0.002, "tau_t": 0.1, "tau_p": 2.0}
    if "md" not in cfg: cfg["md"] = {"nsteps": 500000, "dt": 0.002, "tau_t": 0.1, "tau_p": 2.0, "nstxout": 5000, "nstvout": 5000, "nstfout": 5000, "nstxtcout": 5000, "nstenergy": 5000, "nstlog": 5000}
    cfg.setdefault("temperature", 300)
    cfg.setdefault("pressure", 1.0)
    cfg.setdefault("box_buffer", 1.0)
    cfg.setdefault("box_type", "cubic")
    cfg.setdefault("force_field", "amber99sb-ildn")
    cfg.setdefault("water_model", "tip3p")
    cfg.setdefault("cutoff_scheme", "Verlet")
    cfg.setdefault("coulombtype", "PME")
    cfg.setdefault("rcoulomb", 1.0)
    cfg.setdefault("rvdw", 1.0)
    cfg.setdefault("constraint_algorithm", "lincs")
    cfg.setdefault("constraints", "h-bonds")
    cfg.setdefault("lincs_iter", 1)
    cfg.setdefault("lincs_order", 4)
    cfg.setdefault("nstlist", 10)
    cfg.setdefault("disp_corr", "EnerPres")
    cfg.setdefault("pme_order", 4)
    cfg.setdefault("fourierspacing", 0.16)
    cfg.setdefault("tcoupl", "V-rescale")
    cfg.setdefault("pcoupl", "Parrinello-Rahman")
    cfg.setdefault("pcoupltype", "isotropic")
    cfg.setdefault("compressibility", "4.5e-5")

    # Resolve Proteins
    protein_files = []
    if args.protein:
        for p_path in args.protein:
            protein_files.extend(get_files(p_path, [".pdb", ".pdbqt"]))
    if "proteins" in cfg:
        for p in cfg["proteins"]:
            protein_files.append(os.path.abspath(os.path.join(os.path.dirname(config_path), p["file"])))
    protein_files = list(set(protein_files))

    # Resolve Ligands
    ligands_to_prep = []
    if args.ligand:
        for l_path in args.ligand:
            files = get_files(l_path, [".pdbqt", ".mol2", ".sdf"])
            for f in files:
                ligands_to_prep.append({"file": f, "id": os.path.splitext(os.path.basename(f))[0]})
    if "ligands" in cfg:
        for l in cfg["ligands"]:
            if "file" in l:
                path = os.path.abspath(os.path.join(os.path.dirname(config_path), l["file"]))
                if not any(lp.get("file") == path for lp in ligands_to_prep):
                    ligands_to_prep.append({"file": path, "id": l["id"]})
            elif "smiles" in l:
                if not any(lp.get("smiles") == l["smiles"] for lp in ligands_to_prep):
                    ligands_to_prep.append({"smiles": l["smiles"], "id": l["id"]})

    if not protein_files or not ligands_to_prep:
        logger.error(f"No proteins or ligands specified. (Proteins: {len(protein_files)}, Ligands: {len(ligands_to_prep)})")
        return

    # Change to work directory
    os.chdir(workdir)
    mdp_paths = generate_mdp_files(cfg, workdir)

    # Prepare Ligands
    ligand_data = {}
    prep_dir = os.path.join(workdir, "md_prep")
    os.makedirs(prep_dir, exist_ok=True)
    for lig in ligands_to_prep:
        logger.info(f"--- Preparing Topology for Ligand {lig['id']} ---")
        if "file" in lig:
            itp, gro = prepare_ligand_from_file(lig["file"], os.path.join(prep_dir, f"ligand_{lig['id']}"), run_command)
        else:
            itp, gro = prepare_ligand(lig["id"], lig["smiles"], os.path.join(prep_dir, f"ligand_{lig['id']}"), run_command)
        if itp and gro:
            ligand_data[lig["id"]] = {"itp": itp, "gro": gro}

    # Main Loop
    for prot_input in protein_files:
        prot_file, prot_id = prepare_protein(prot_input, workdir)
        if not prot_file: continue

        for lig_id, lig_paths in ligand_data.items():
            complex_name = f"{prot_id}_{lig_id}"
            logger.info(f"--- Processing Complex: {complex_name} ---")

            # 1. Run pdb2gmx
            prot_gro_raw = os.path.join(workdir, f"{complex_name}_prot_raw.gro")
            prot_top = os.path.join(workdir, f"{complex_name}_prot.top")
            logger.info(f"--- Running pdb2gmx for {complex_name} ---")
            if not run_gmx(["pdb2gmx", "-ff", cfg["force_field"], "-water", cfg["water_model"], "-ignh", "-missing"],
                          input_files={"-f": prot_file}, output_files={"-o": prot_gro_raw, "-p": prot_top},
                          use_docker=args.docker, image=args.image, host_root=host_root, cwd=workdir):
                logger.critical(f"CRITICAL ERROR: pdb2gmx failed for {complex_name}. Exiting.")
                sys.exit(1)

            # 2. Repair pdb2gmx output in-place
            fix_gro(prot_gro_raw)

            # 3. Center the repaired protein to get a GOOD reference frame
            prot_gro = os.path.join(workdir, f"{complex_name}_prot.gro")
            if not run_gmx(["editconf", "-c"], input_files={"-f": prot_gro_raw}, output_files={"-o": prot_gro},
                          use_docker=args.docker, image=args.image, host_root=host_root, cwd=workdir):
                logger.critical(f"CRITICAL ERROR: editconf centering failed for {complex_name}. Exiting.")
                sys.exit(1)

            # Ensure unique posre.itp per complex
            handle_posre(prot_top, workdir, complex_name)

            complex_gro = os.path.join(workdir, f"{complex_name}_complex.gro")
            try:
                # 4. Merge protein and ligand
                # Since prot_gro is centered, merge_complex will now center the ligand to origin automatically
                lig_itp_local = os.path.join(workdir, os.path.basename(lig_paths["itp"]))
                shutil.copy(lig_paths["itp"], lig_itp_local)
                
                merge_complex(prot_gro, lig_paths["gro"], complex_gro)
                update_topology(prot_top, lig_itp_local, workdir)
                
                final_gro = setup_system(complex_gro, prot_top, complex_name, cfg, outdir, workdir,
                                        use_docker=args.docker, image=args.image, host_root=host_root)
            except Exception as e:
                logger.critical(f"CRITICAL ERROR: Preparation failed for {complex_name}: {e}. Exiting.")
                sys.exit(1)

            # Simulation Steps
            try:
                logger.info(f"Starting EM for {complex_name}...")
                gro, cpt = run_step("em", mdp_paths["em.mdp"], final_gro, prot_top, complex_name, outdir, workdir, gpu=args.gpu, use_docker=args.docker, image=args.image, host_root=host_root)
                
                logger.info(f"Starting NVT for {complex_name}...")
                gro, cpt = run_step("nvt", mdp_paths["nvt.mdp"], gro, prot_top, complex_name, outdir, workdir, gpu=args.gpu, use_docker=args.docker, image=args.image, host_root=host_root)
                
                logger.info(f"Starting NPT for {complex_name}...")
                gro, cpt = run_step("npt", mdp_paths["npt.mdp"], gro, prot_top, complex_name, outdir, workdir, gpu=args.gpu, prev_cpt=cpt, use_docker=args.docker, image=args.image, host_root=host_root)
                
                logger.info(f"Starting Production MD for {complex_name}...")
                run_step("md", mdp_paths["md.mdp"], gro, prot_top, complex_name, outdir, workdir, gpu=args.gpu, prev_cpt=cpt, use_docker=args.docker, image=args.image, host_root=host_root)
                
                logger.info(f"Successfully completed MD for {complex_name}.")
                
                # Copy results
                final_files = glob.glob(os.path.join(workdir, f"{complex_name}*"))
                for f in final_files:
                    shutil.copy(f, outdir)
                    
            except Exception as e:
                logger.critical(f"CRITICAL ERROR: Simulation failed for {complex_name}: {e}. Exiting.")
                sys.exit(1)

if __name__ == "__main__":
    main()
