import os
import argparse
import glob
import sys
import shutil
from src.config_loader import load_config
from src.gmx_utils import run_gmx, run_command
from src.logger_utils import setup_logger
from src.plotting import plot_xvg
from src.report_utils import generate_html_report

# Setup Logger
setup_logger()
logger = setup_logger("post_md")

def get_files(path, extensions):
    """Retrieves files from a path or directory with specific extensions."""
    if os.path.isfile(path):
        return [os.path.abspath(path)]
    elif os.path.isdir(path):
        files = []
        for ext in extensions:
            files.extend(
                [os.path.abspath(f) for f in glob.glob(os.path.join(path, f"*{ext}"))]
            )
        return files
    glob_files = glob.glob(path)
    if glob_files:
        files = []
        for f in glob_files:
            if any(f.endswith(ext) for ext in extensions):
                files.append(os.path.abspath(f))
        return files
    return []

def get_ligand_group(tpr, complex_name, workdir, args):
    """Identifies the ligand group name using make_ndx."""
    ndx_file = os.path.join(workdir, f"{complex_name}.ndx")
    # Run make_ndx and capture output to see groups
    # We use a dummy command 'q' to just exit and save the default groups
    if not run_gmx(
        ["make_ndx"],
        input_files={"-f": tpr},
        output_files={"-o": ndx_file},
        stdin="q\n",
        use_docker=args.docker,
        image=args.image,
        host_root=args.host_root,
        cwd=workdir,
    ):
        return "SOL" # Fallback

    # Usually, the ligand is the last group before water/ions if it was added last.
    # Or we can look for common ligand names: LIG, UNK, etc.
    # We can also try to parse the ndx file.
    groups = []
    if os.path.exists(ndx_file):
        with open(ndx_file, "r") as f:
            for line in f:
                if line.startswith("["):
                    groups.append(line.strip("[] \n"))
    
    # Priority: LIG, UNK, or the group after "Water_and_Ions" or similar.
    for g in groups:
        if g.upper() in ["LIG", "UNK"]:
            return g
    
    # If not found, look for any group that isn't standard
    standard = ["System", "Protein", "Protein-H", "C-alpha", "Backbone", "MainChain", 
                "MainChain+Cb", "MainChain+H", "SideChain", "SideChain-H", "Prot-Masses", 
                "non-Protein", "Water", "SOL", "non-Water", "Ion", "NA", "CL", "Water_and_Ions"]
    
    for g in groups:
        if g not in standard:
            return g
            
    return "non-Protein" # Final fallback

def analyze_complex(complex_name, outdir, workdir, cfg, args):
    logger.info(f"--- Analyzing Complex: {complex_name} ---")
    
    tpr = os.path.join(outdir, f"{complex_name}_md.tpr")
    xtc = os.path.join(outdir, f"{complex_name}_md.xtc")
    
    if not os.path.exists(tpr) or not os.path.exists(xtc):
        logger.warning(f"Skipping {complex_name}: Production MD files (tpr/xtc) missing in {outdir}.")
        return

    analysis_dir = os.path.join(outdir, f"analysis_{complex_name}")
    os.makedirs(analysis_dir, exist_ok=True)
    
    plots_collected = {}

    # 1. PBC Treatment: NoPBC and Fitted Trajectories
    # We center on Protein and output System
    nopbc_xtc = os.path.join(analysis_dir, f"{complex_name}_noPBC.xtc")
    if not os.path.exists(nopbc_xtc):
        logger.info(f"Fixing PBC for {complex_name}...")
        run_gmx(
            ["trjconv", "-pbc", "mol", "-center"],
            input_files={"-f": xtc, "-s": tpr},
            output_files={"-o": nopbc_xtc},
            stdin="Protein\nSystem\n",
            use_docker=args.docker,
            image=args.image,
            host_root=args.host_root,
            cwd=workdir,
        )

    fitted_xtc = os.path.join(analysis_dir, f"{complex_name}_fitted.xtc")
    if not os.path.exists(fitted_xtc):
        logger.info(f"Fitting trajectory for {complex_name}...")
        run_gmx(
            ["trjconv", "-fit", "rot+trans"],
            input_files={"-f": nopbc_xtc, "-s": tpr},
            output_files={"-o": fitted_xtc},
            stdin="Backbone\nSystem\n",
            use_docker=args.docker,
            image=args.image,
            host_root=args.host_root,
            cwd=workdir,
        )

    # Identify Ligand Group
    lig_group = get_ligand_group(tpr, complex_name, workdir, args)
    logger.info(f"Identified Ligand Group: {lig_group}")

    # 2. RMSD Analysis
    # Protein Backbone
    rmsd_prot = os.path.join(analysis_dir, "rmsd_protein.xvg")
    rmsd_prot_plot = rmsd_prot.replace(".xvg", ".png")
    if not os.path.exists(rmsd_prot):
        logger.info(f"Calculating Protein RMSD for {complex_name}...")
        run_gmx(
            ["rms", "-tu", "ns"],
            input_files={"-f": fitted_xtc, "-s": tpr},
            output_files={"-o": rmsd_prot},
            stdin="Backbone\nBackbone\n",
            use_docker=args.docker,
            image=args.image,
            host_root=args.host_root,
            cwd=workdir,
        )
        plot_xvg(rmsd_prot, rmsd_prot_plot)
    plots_collected["Protein RMSD"] = rmsd_prot_plot

    # Ligand RMSD (Fit to Backbone)
    rmsd_lig = os.path.join(analysis_dir, "rmsd_ligand.xvg")
    rmsd_lig_plot = rmsd_lig.replace(".xvg", ".png")
    if not os.path.exists(rmsd_lig):
        logger.info(f"Calculating Ligand RMSD for {complex_name}...")
        run_gmx(
            ["rms", "-tu", "ns"],
            input_files={"-f": fitted_xtc, "-s": tpr},
            output_files={"-o": rmsd_lig},
            stdin="Backbone\n" + f"{lig_group}\n",
            use_docker=args.docker,
            image=args.image,
            host_root=args.host_root,
            cwd=workdir,
        )
        plot_xvg(rmsd_lig, rmsd_lig_plot)
    plots_collected["Ligand RMSD"] = rmsd_lig_plot

    # 3. RMSF Analysis (Protein C-alpha)
    rmsf_prot = os.path.join(analysis_dir, "rmsf_protein.xvg")
    rmsf_prot_plot = rmsf_prot.replace(".xvg", ".png")
    if not os.path.exists(rmsf_prot):
        logger.info(f"Calculating Protein RMSF for {complex_name}...")
        run_gmx(
            ["rmsf", "-res"],
            input_files={"-f": fitted_xtc, "-s": tpr},
            output_files={"-o": rmsf_prot},
            stdin="C-alpha\n",
            use_docker=args.docker,
            image=args.image,
            host_root=args.host_root,
            cwd=workdir,
        )
        plot_xvg(rmsf_prot, rmsf_prot_plot)
    plots_collected["Protein RMSF"] = rmsf_prot_plot

    # 4. Radius of Gyration (Protein Backbone)
    rg_prot = os.path.join(analysis_dir, "rg_protein.xvg")
    rg_prot_plot = rg_prot.replace(".xvg", ".png")
    if not os.path.exists(rg_prot):
        logger.info(f"Calculating Radius of Gyration for {complex_name}...")
        run_gmx(
            ["gyrate"],
            input_files={"-f": fitted_xtc, "-s": tpr},
            output_files={"-o": rg_prot},
            stdin="Backbone\n",
            use_docker=args.docker,
            image=args.image,
            host_root=args.host_root,
            cwd=workdir,
        )
        plot_xvg(rg_prot, rg_prot_plot)
    plots_collected["Radius of Gyration"] = rg_prot_plot

    # 5. Hydrogen Bonds (Protein - Ligand)
    hbonds = os.path.join(analysis_dir, "hbonds.xvg")
    hbonds_plot = hbonds.replace(".xvg", ".png")
    if not os.path.exists(hbonds):
        logger.info(f"Calculating Hydrogen Bonds for {complex_name}...")
        run_gmx(
            ["hbond"],
            input_files={"-f": fitted_xtc, "-s": tpr},
            output_files={"-num": hbonds},
            stdin="Protein\n" + f"{lig_group}\n",
            use_docker=args.docker,
            image=args.image,
            host_root=args.host_root,
            cwd=workdir,
        )
        plot_xvg(hbonds, hbonds_plot)
    plots_collected["Hydrogen Bonds"] = hbonds_plot

    # Generate HTML Report
    metadata = {
        "Force Field": cfg.get("force_field", "N/A"),
        "Water Model": cfg.get("water_model", "N/A"),
        "Temperature": f"{cfg.get('temperature', 300)} K",
        "Ligand Group": lig_group,
        "Complex Name": complex_name
    }
    report_path = generate_html_report(complex_name, analysis_dir, plots_collected, metadata)
    logger.info(f"Report generated: {report_path}")

    logger.info(f"Completed Analysis for {complex_name}. Results in {analysis_dir}")

def main():
    parser = argparse.ArgumentParser(
        description="Post-MD Analysis Workflow for Protein-Ligand Complexes"
    )
    parser.add_argument(
        "--config", "-c", default="config.json", help="Path to config file"
    )
    parser.add_argument(
        "--protein", "-p", nargs="+", help="Protein files (PDB/PDBQT) or IDs"
    )
    parser.add_argument(
        "--ligand", "-l", nargs="+", help="Ligand files or IDs"
    )
    parser.add_argument("--outdir", "-o", default="results", help="Output directory where MD results are stored")
    parser.add_argument("--workdir", "-w", default="work", help="Working directory")
    parser.add_argument(
        "--docker", action="store_true", default=True, help="Run via Docker"
    )
    parser.add_argument("--no-docker", action="store_false", dest="docker")
    parser.add_argument(
        "--image", default="nvcr.io/hpc/gromacs:2023.2", help="Docker image"
    )

    args = parser.parse_args()
    args.host_root = os.path.dirname(os.path.abspath(__file__))
    outdir = os.path.abspath(args.outdir)
    workdir = os.path.abspath(args.workdir)
    os.makedirs(workdir, exist_ok=True)

    config_path = os.path.abspath(args.config)
    cfg = load_config(config_path) if os.path.exists(config_path) else {}

    # Resolve Proteins and Ligands to find complexes
    protein_ids = []
    if args.protein:
        for p in args.protein:
            protein_ids.append(os.path.splitext(os.path.basename(p))[0])
    if "proteins" in cfg:
        for p in cfg["proteins"]:
            protein_ids.append(p.get("id", os.path.splitext(os.path.basename(p["file"]))[0]))
    
    ligand_ids = []
    if args.ligand:
        for l in args.ligand:
            ligand_ids.append(os.path.splitext(os.path.basename(l))[0])
    if "ligands" in cfg:
        for l in cfg["ligands"]:
            ligand_ids.append(l["id"])

    protein_ids = list(set(protein_ids))
    ligand_ids = list(set(ligand_ids))

    # If no IDs specified, scan outdir for complexes
    complexes = []
    if not protein_ids or not ligand_ids:
        logger.info("Scanning output directory for completed MD complexes...")
        xtc_files = glob.glob(os.path.join(outdir, "*_md.xtc"))
        for f in xtc_files:
            name = os.path.basename(f).replace("_md.xtc", "")
            complexes.append(name)
    else:
        for pid in protein_ids:
            for lid in ligand_ids:
                complexes.append(f"{pid}_{lid}")

    if not complexes:
        logger.error("No complexes identified for analysis.")
        return

    logger.info(f"Found {len(complexes)} complexes to analyze.")
    
    # Change to work directory for GROMACS temporary files
    original_cwd = os.getcwd()
    os.chdir(workdir)
    
    try:
        for comp in complexes:
            analyze_complex(comp, outdir, workdir, cfg, args)
    finally:
        os.chdir(original_cwd)

if __name__ == "__main__":
    main()
