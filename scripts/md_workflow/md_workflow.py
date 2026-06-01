import os
import argparse
import shutil
import glob
import sys
from src.config_loader import load_config
from src.gmx_utils import run_gmx, run_command
from src.md_utils import generate_mdp_files, run_step, concatenate_trajectories
from src.mol_prep import prepare_ligand, prepare_ligand_from_file
from src.top_utils import (
    merge_complex,
    update_topology,
    setup_system,
    prepare_protein,
    handle_posre,
    fix_gro,
)
from src.logger_utils import setup_logger
from src.transfer_utils import archive_and_upload
from src.notify_utils import Notifier

# Setup Global Root Logger
setup_logger()
logger = setup_logger("md_workflow")


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


def main():
    cpu_count = os.cpu_count() or 1
    default_cpus = min(cpu_count, 16)

    parser = argparse.ArgumentParser(description="Automated MD Workflow")
    parser.add_argument(
        "--config", "-c", default="config.json", help="Path to config file"
    )
    parser.add_argument("--protein", "-p", nargs="+", help="Protein files")
    parser.add_argument("--ligand", "-l", nargs="+", help="Ligand files")
    parser.add_argument("--outdir", "-o", default="results", help="Output directory")
    parser.add_argument("--workdir", "-w", default="work", help="Working directory")
    parser.add_argument("--gpu", action="store_true", default=True, help="Enable GPU")
    parser.add_argument("--no-gpu", action="store_false", dest="gpu")
    parser.add_argument(
        "--docker", action="store_true", default=True, help="Run via Docker"
    )
    parser.add_argument("--no-docker", action="store_false", dest="docker")
    parser.add_argument(
        "--image", default="nvcr.io/hpc/gromacs:2023.2", help="Docker image"
    )
    parser.add_argument("--skip-prep", action="store_true", help="Skip preparation")
    parser.add_argument("--cpus", type=int, default=default_cpus, help="CPUs")
    parser.add_argument("--upload", action="store_true", help="Upload results")
    parser.add_argument(
        "--resume", action="store_true", help="Resume directly from TPR/CPT"
    )
    parser.add_argument(
        "--notify-interval", type=int, default=1800, help="Notify interval"
    )
    parser.add_argument("--log", help="Log file")

    args = parser.parse_args()
    if args.log:
        setup_logger("md_workflow", log_file=args.log)

    outdir = os.path.abspath(args.outdir)
    workdir = os.path.abspath(args.workdir)
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(workdir, exist_ok=True)
    host_root = os.environ.get("HOST_PWD", os.getcwd())

    logger.info(f"Starting workflow. Outdir: {outdir}, Workdir: {workdir}")

    # Load Configuration
    cfg = {}
    config_path = os.path.abspath(args.config)
    if os.path.exists(config_path):
        cfg = load_config(config_path)

    cfg.setdefault("md", {"nsteps": 500000, "dt": 0.002, "tau_t": 0.1, "tau_p": 2.0})
    notifier = Notifier(cfg.get("notifications", {}))
    if not notifier.is_configured():
        notifier = None

    # --- DIRECT RESUME MODE (BLIND RESUME) ---
    found_resumable = []
    if args.resume:
        logger.info("--- Resume Mode Active: Scanning for existing MD files ---")
        # Search for *_md.tpr in outdir and workdir
        for search_path in [outdir, workdir]:
            logger.info(f"Scanning {search_path} for resumable files...")
            tpr_files = glob.glob(os.path.join(search_path, "*_md.tpr"))
            for tpr in tpr_files:
                complex_name = os.path.basename(tpr).replace("_md.tpr", "")
                cpt = tpr.replace(".tpr", ".cpt")
                if os.path.exists(cpt):
                    logger.info(
                        f"Found resumable complex: {complex_name} (TPR/CPT exist)"
                    )
                    # Ensure files are in outdir for consistent execution
                    if os.path.dirname(tpr) != outdir:
                        shutil.copy(tpr, os.path.join(outdir, os.path.basename(tpr)))
                        shutil.copy(cpt, os.path.join(outdir, os.path.basename(cpt)))

                    if complex_name not in found_resumable:
                        found_resumable.append(complex_name)
                else:
                    logger.warning(
                        f"Found TPR for {complex_name} but CPT is missing. Skipping direct resume."
                    )

        if found_resumable:
            logger.info(f"Total resumable complexes identified: {found_resumable}")
            os.chdir(workdir)
            mdp_paths = generate_mdp_files(cfg, workdir)

            for complex_name in found_resumable:
                logger.info(
                    f">>> [RESUME] Starting Production MD for: {complex_name} <<<"
                )
                try:
                    run_step(
                        "md",
                        mdp_paths["md.mdp"],
                        None,  # gro is None for direct resume
                        None,  # top is None for direct resume
                        complex_name,
                        outdir,
                        workdir,
                        gpu=args.gpu,
                        prev_cpt=os.path.join(outdir, f"{complex_name}_md.cpt"),
                        use_docker=args.docker,
                        image=args.image,
                        host_root=host_root,
                        cpus=args.cpus,
                        notify_interval=args.notify_interval,
                        notifier=notifier,
                    )

                    logger.info(
                        f"Finished resumed MD for {complex_name}. Concatenating trajectories..."
                    )
                    concatenate_trajectories(
                        complex_name,
                        outdir,
                        use_docker=args.docker,
                        image=args.image,
                        host_root=host_root,
                        cpus=args.cpus,
                    )
                except Exception as e:
                    logger.error(f"Failed to resume {complex_name}: {e}")

            # If ONLY resuming (no new inputs), finish here
            if not args.protein and not args.ligand and "proteins" not in cfg:
                logger.info("Resume phase complete. No new inputs to process.")
                if args.upload:
                    archive_and_finish(outdir, workdir, notifier)
                return

    # --- NORMAL MODE (Preparation + Simulation) ---
    logger.info("--- Entering Normal Workflow Phase ---")

    # Resolve Proteins
    protein_files = []
    if args.protein:
        for p_path in args.protein:
            protein_files.extend(get_files(p_path, [".pdb", ".pdbqt"]))
    if "proteins" in cfg:
        for p in cfg["proteins"]:
            p_abs = os.path.abspath(
                os.path.join(os.path.dirname(config_path), p["file"])
            )
            if os.path.exists(p_abs):
                protein_files.append(p_abs)
            else:
                logger.warning(f"Protein file from config not found: {p_abs}")
    protein_files = list(set(protein_files))

    # Resolve Ligands
    ligands_to_prep = []
    if args.ligand:
        for l_path in args.ligand:
            files = get_files(l_path, [".pdbqt", ".mol2", ".sdf"])
            for f in files:
                ligands_to_prep.append(
                    {"file": f, "id": os.path.splitext(os.path.basename(f))[0]}
                )
    if "ligands" in cfg:
        for l in cfg["ligands"]:
            # Priority to ID from JSON, then filename
            l_id = l.get("id") or (
                os.path.splitext(os.path.basename(l["file"]))[0]
                if "file" in l
                else "unk"
            )
            entry = {"id": l_id}
            if "file" in l:
                entry["file"] = os.path.abspath(
                    os.path.join(os.path.dirname(config_path), l["file"])
                )
            if "smiles" in l:
                entry["smiles"] = l["smiles"]
            if not any(lp.get("id") == entry["id"] for lp in ligands_to_prep):
                ligands_to_prep.append(entry)

    if not protein_files or not ligands_to_prep:
        if args.resume and found_resumable:
            logger.info("Workflow finished (all tasks were resumes).")
            if args.upload:
                archive_and_finish(outdir, workdir, notifier)
            return
        else:
            logger.error("No valid protein/ligand inputs found to process.")
            return

    os.chdir(workdir)
    mdp_paths = generate_mdp_files(cfg, workdir)

    # Prepare Ligands
    ligand_data = {}
    prep_dir = os.path.join(workdir, "md_prep")
    os.makedirs(prep_dir, exist_ok=True)
    for lig in ligands_to_prep:
        lig_id = lig["id"]
        lig_prep_dir = os.path.join(prep_dir, f"ligand_{lig_id}")

        # Check if already done or if we can skip
        if any(
            os.path.exists(os.path.join(outdir, f"{p_id}_{lig_id}_md.gro"))
            for p_id in [
                os.path.splitext(os.path.basename(pf))[0] for pf in protein_files
            ]
        ):
            logger.info(
                f"Complex with ligand {lig_id} already exists in outdir. Skipping ligand prep."
            )
            continue

        if args.skip_prep:
            continue

        logger.info(f"Preparing topology for ligand {lig_id}")
        if "file" in lig and os.path.exists(lig["file"]):
            itp, gro = prepare_ligand_from_file(
                lig["file"],
                lig_prep_dir,
                run_command,
                smiles=lig.get("smiles"),
                cpus=args.cpus,
            )
        elif "smiles" in lig:
            itp, gro = prepare_ligand(
                lig["id"], lig["smiles"], lig_prep_dir, run_command, cpus=args.cpus
            )
        else:
            logger.warning(f"Cannot prepare ligand {lig_id}: file/smiles missing.")
            continue

        if itp and gro:
            ligand_data[lig_id] = {"itp": itp, "gro": gro}

    # Main Prep+Sim Loop
    for prot_input in protein_files:
        prot_id = os.path.splitext(os.path.basename(prot_input))[0]
        prot_file, _ = prepare_protein(prot_input, workdir)
        if not prot_file:
            continue

        for lig_id, lig_paths in ligand_data.items():
            complex_name = f"{prot_id}_{lig_id}"
            if os.path.exists(os.path.join(outdir, f"{complex_name}_md.gro")):
                continue

            logger.info(f"--- Setting up complex: {complex_name} ---")
            try:
                prot_gro_raw = os.path.join(workdir, f"{complex_name}_prot_raw.gro")
                prot_top = os.path.join(workdir, f"{complex_name}_prot.top")

                if not run_gmx(
                    [
                        "pdb2gmx",
                        "-ff",
                        cfg.get("force_field", "amber99sb-ildn"),
                        "-water",
                        cfg.get("water_model", "tip3p"),
                        "-ignh",
                    ],
                    input_files={"-f": prot_file},
                    output_files={"-o": prot_gro_raw, "-p": prot_top},
                    use_docker=args.docker,
                    image=args.image,
                    host_root=host_root,
                    cwd=workdir,
                    cpus=args.cpus,
                ):
                    continue

                fix_gro(prot_gro_raw)
                handle_posre(prot_top, workdir, complex_name)
                complex_gro = os.path.join(workdir, f"{complex_name}_complex.gro")
                lig_itp_local = os.path.join(
                    workdir, os.path.basename(lig_paths["itp"])
                )
                shutil.copy(lig_paths["itp"], lig_itp_local)
                merge_complex(prot_gro_raw, lig_paths["gro"], complex_gro)
                update_topology(prot_top, lig_itp_local, workdir)

                final_gro = setup_system(
                    complex_gro,
                    prot_top,
                    complex_name,
                    cfg,
                    outdir,
                    workdir,
                    use_docker=args.docker,
                    image=args.image,
                    host_root=host_root,
                    cpus=args.cpus,
                )

                gro, cpt = run_step(
                    "em",
                    mdp_paths["em.mdp"],
                    final_gro,
                    prot_top,
                    complex_name,
                    outdir,
                    workdir,
                    gpu=args.gpu,
                    cpus=args.cpus,
                )
                gro, cpt = run_step(
                    "nvt",
                    mdp_paths["nvt.mdp"],
                    gro,
                    prot_top,
                    complex_name,
                    outdir,
                    workdir,
                    gpu=args.gpu,
                    cpus=args.cpus,
                )
                gro, cpt = run_step(
                    "npt",
                    mdp_paths["npt.mdp"],
                    gro,
                    prot_top,
                    complex_name,
                    outdir,
                    workdir,
                    gpu=args.gpu,
                    prev_cpt=cpt,
                    cpus=args.cpus,
                )
                run_step(
                    "md",
                    mdp_paths["md.mdp"],
                    gro,
                    prot_top,
                    complex_name,
                    outdir,
                    workdir,
                    gpu=args.gpu,
                    prev_cpt=cpt,
                    cpus=args.cpus,
                    notifier=notifier,
                )
                concatenate_trajectories(
                    complex_name,
                    outdir,
                    use_docker=args.docker,
                    image=args.image,
                    host_root=host_root,
                )
            except Exception as e:
                logger.error(f"Error in complex {complex_name}: {e}")

    if args.upload:
        archive_and_finish(outdir, workdir, notifier)


def archive_and_finish(outdir, workdir, notifier):
    import datetime

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"results_{timestamp}.zip"
    archive_path = os.path.join(workdir, archive_name)
    shutil.make_archive(archive_path.replace(".zip", ""), "zip", outdir)
    url = archive_and_upload(archive_path)
    if url and notifier:
        notifier.notify_all(f"Workflow Complete: {url}")


if __name__ == "__main__":
    main()
