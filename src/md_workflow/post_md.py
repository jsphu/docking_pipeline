import os
import argparse
import glob
import sys
import shutil
import difflib
from .config_loader import load_config
from .gmx_utils import run_gmx, run_command
from .logger_utils import setup_logger
from .plotting import plot_xvg, get_xvg_stats
from .report_utils import generate_html_report, generate_master_report
from .transfer_utils import archive_and_upload

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
    if not tpr or not os.path.exists(tpr):
        return "UNK"
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
        cpus=args.cpus,
    ):
        return "SOL"  # Fallback

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
    standard = [
        "System",
        "Protein",
        "Protein-H",
        "C-alpha",
        "Backbone",
        "MainChain",
        "MainChain+Cb",
        "MainChain+H",
        "SideChain",
        "SideChain-H",
        "Prot-Masses",
        "non-Protein",
        "Water",
        "SOL",
        "non-Water",
        "Ion",
        "NA",
        "CL",
        "Water_and_Ions",
    ]

    for g in groups:
        if g not in standard:
            return g

    return "non-Protein"  # Final fallback


def analyze_complex(complex_name, outdir, workdir, cfg, args):
    logger.info(f"--- Analyzing Complex: {complex_name} ---")

    tpr = os.path.join(outdir, f"{complex_name}_md.tpr")
    # Prefer combined xtc if it exists
    combined_xtc = os.path.join(outdir, f"{complex_name}_md_combined.xtc")
    standard_xtc = os.path.join(outdir, f"{complex_name}_md.xtc")

    xtc = combined_xtc if os.path.exists(combined_xtc) else standard_xtc

    if not args.report_only:
        if not os.path.exists(tpr) or not os.path.exists(xtc):
            logger.warning(
                f"Skipping {complex_name}: Production MD files (tpr/xtc) missing in {outdir}."
            )
            return None

    if xtc == combined_xtc:
        logger.info(f"Using concatenated trajectory: {os.path.basename(xtc)}")
    else:
        logger.info(f"Using standard trajectory: {os.path.basename(xtc)}")

    analysis_dir = os.path.join(outdir, f"analysis_{complex_name}")
    os.makedirs(analysis_dir, exist_ok=True)

    plots_collected = {}

    # 1. PBC Treatment: NoPBC and Fitted Trajectories
    # We center on Protein and output System
    nopbc_xtc = os.path.join(analysis_dir, f"{complex_name}_noPBC.xtc")
    fitted_xtc = os.path.join(analysis_dir, f"{complex_name}_fitted.xtc")

    if not args.report_only:
        # Force re-run if source xtc is newer than existing nopbc_xtc
        force_pbc = False
        if os.path.exists(nopbc_xtc):
            if os.path.getmtime(xtc) > os.path.getmtime(nopbc_xtc):
                logger.info(
                    f"Source trajectory {os.path.basename(xtc)} is newer than {os.path.basename(nopbc_xtc)}. Forcing PBC fix."
                )
                force_pbc = True

        if not os.path.exists(nopbc_xtc) or force_pbc:
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
                cpus=args.cpus,
            )

        force_fit = force_pbc
        if os.path.exists(fitted_xtc) and not force_fit:
            if os.path.getmtime(nopbc_xtc) > os.path.getmtime(fitted_xtc):
                force_fit = True

        if not os.path.exists(fitted_xtc) or force_fit:
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
                cpus=args.cpus,
            )

        # Identify Ligand Group
        lig_group = get_ligand_group(tpr, complex_name, workdir, args)
        logger.info(f"Identified Ligand Group: {lig_group}")
    else:
        force_fit = False
        lig_group = "UNK"

    # Helper to run and collect
    def run_analysis(
        tool, input_flags, output_file, stdin, plot_title, extra_args=None
    ):
        out_path = os.path.join(analysis_dir, output_file)
        plot_path = out_path.replace(".xvg", ".png")

        if args.report_only:
            if not os.path.exists(out_path):
                logger.warning(f"Analysis XVG file {out_path} missing in report-only mode.")
                return
            if not os.path.exists(plot_path):
                plot_xvg(out_path, plot_path)
            stats = get_xvg_stats(out_path)
            plots_collected[plot_title] = {"path": plot_path, "stats": stats}
            return

        # Force re-run if fitted_xtc is newer than out_path
        force_run = force_fit
        if os.path.exists(out_path) and not force_run:
            if os.path.getmtime(fitted_xtc) > os.path.getmtime(out_path):
                force_run = True

        if not os.path.exists(out_path) or force_run:

            logger.info(f"Calculating {plot_title} for {complex_name}...")
            # Prepare output flag based on tool
            output_flags = {"-o": out_path}
            if tool in ["hbond", "hbond-legacy"]:
                output_flags = {"-num": out_path}

            gmx_args = [tool]
            if extra_args:
                gmx_args.extend(extra_args)

            success = run_gmx(
                gmx_args,
                input_files=input_flags,
                output_files=output_flags,
                stdin=stdin,
                use_docker=args.docker,
                image=args.image,
                host_root=args.host_root,
                cwd=workdir,
                cpus=args.cpus,
            )
            if success and os.path.exists(out_path):
                plot_xvg(out_path, plot_path)
            else:
                logger.warning(f"Failed to calculate {plot_title} for {complex_name}")
                return
        else:
            if not os.path.exists(plot_path):
                plot_xvg(out_path, plot_path)

        if os.path.exists(out_path):
            stats = get_xvg_stats(out_path)
            plots_collected[plot_title] = {"path": plot_path, "stats": stats}

    # 2. RMSD Analysis
    run_analysis(
        "rms",
        {"-f": fitted_xtc, "-s": tpr, "-tu": "ns"},
        "rmsd_protein.xvg",
        "Backbone\nBackbone\n",
        "Protein RMSD",
    )
    run_analysis(
        "rms",
        {"-f": fitted_xtc, "-s": tpr, "-tu": "ns"},
        "rmsd_ligand.xvg",
        "Backbone\n" + f"{lig_group}\n",
        "Ligand RMSD",
    )

    # 3. RMSF Analysis
    run_analysis(
        "rmsf",
        {"-f": fitted_xtc, "-s": tpr},
        "rmsf_protein.xvg",
        "C-alpha\n",
        "Protein RMSF",
        extra_args=["-res"],
    )

    # 4. Radius of Gyration
    run_analysis(
        "gyrate",
        {"-f": fitted_xtc, "-s": tpr},
        "rg_protein.xvg",
        "Backbone\n",
        "Radius of Gyration",
    )

    # 5. Hydrogen Bonds
    # Using hbond-legacy because the new hbond (GROMACS 2024+) often fails to recognize
    # donors/acceptors in acpype-generated ligand topologies.
    run_analysis(
        "hbond-legacy",
        {"-f": fitted_xtc, "-s": tpr},
        "hbonds.xvg",
        "Protein\n" + f"{lig_group}\n",
        "Hydrogen Bonds",
    )

    # Generate HTML Report
    metadata = {
        "Force Field": cfg.get("force_field", "N/A"),
        "Water Model": cfg.get("water_model", "N/A"),
        "Temperature": f"{cfg.get('temperature', 300)} K",
        "Ligand Group": lig_group,
        "Complex Name": complex_name,
    }
    # For individual report, we need to pass a dict of title -> path
    legacy_plots = {k: v["path"] for k, v in plots_collected.items()}
    report_path = generate_html_report(
        complex_name, analysis_dir, legacy_plots, metadata
    )
    logger.info(f"Report generated: {report_path}")

    logger.info(f"Completed Analysis for {complex_name}. Results in {analysis_dir}")

    return {
        "complex_name": complex_name,
        "analysis_dir": analysis_dir,
        "plots": plots_collected,
        "metadata": metadata,
    }


def reconstruct_result(complex_name, outdir):
    """Attempts to reconstruct an analysis result from existing files."""
    analysis_dir = os.path.join(outdir, f"analysis_{complex_name}")
    if not os.path.exists(analysis_dir):
        # Try to find a similar directory name in case of typos
        existing_analyses = [d for d in os.listdir(outdir) if d.startswith("analysis_")]
        complex_names = [d.replace("analysis_", "") for d in existing_analyses]
        matches = difflib.get_close_matches(
            complex_name, complex_names, n=1, cutoff=0.7
        )
        if matches:
            logger.warning(
                f"Analysis directory for '{complex_name}' not found. Using closest match: '{matches[0]}'"
            )
            analysis_dir = os.path.join(outdir, f"analysis_{matches[0]}")
            complex_name = matches[0]
        else:
            logger.warning(
                f"Analysis directory for '{complex_name}' not found. Skipping."
            )
            return None

    logger.info(f"Reconstructing analysis data for: {complex_name}")

    plot_map = {
        "Protein RMSD": "rmsd_protein.xvg",
        "Ligand RMSD": "rmsd_ligand.xvg",
        "Protein RMSF": "rmsf_protein.xvg",
        "Radius of Gyration": "rg_protein.xvg",
        "Hydrogen Bonds": "hbonds.xvg",
    }

    plots_collected = {}
    for title, xvg_name in plot_map.items():
        xvg_path = os.path.join(analysis_dir, xvg_name)
        png_path = xvg_path.replace(".xvg", ".png")
        if os.path.exists(xvg_path) and os.path.exists(png_path):
            stats = get_xvg_stats(xvg_path)
            plots_collected[title] = {"path": png_path, "stats": stats}

    if not plots_collected:
        logger.warning(f"No plot files found in {analysis_dir}. Skipping.")
        return None

    return {
        "complex_name": complex_name,
        "analysis_dir": analysis_dir,
        "plots": plots_collected,
        "metadata": {"Complex Name": complex_name, "Source": "Existing Analysis"},
    }


def main():
    # Detect default CPU limit
    cpu_count = os.cpu_count() or 1
    default_cpus = min(cpu_count, 16)

    parser = argparse.ArgumentParser(
        description="Post-MD Analysis Workflow for Protein-Ligand Complexes",
        prog="post-md",
    )
    parser.add_argument(
        "--config", "-c", default="config.json", help="Path to config file"
    )
    parser.add_argument(
        "--protein", "-p", nargs="+", help="Protein files (PDB/PDBQT) or IDs"
    )
    parser.add_argument("--ligand", "-l", nargs="+", help="Ligand files or IDs")
    parser.add_argument(
        "--select",
        "-s",
        nargs="+",
        help="Specific complex names to analyze (e.g. 6NJS_LIG1)",
    )
    parser.add_argument(
        "--master-only",
        "-m",
        action="store_true",
        help="Only generate master report from existing analysis",
    )
    parser.add_argument(
        "--master-output",
        default="master_analysis_report.html",
        help="Filename for the master report",
    )
    parser.add_argument(
        "--outdir",
        "-o",
        default="results",
        help="Output directory where MD results are stored",
    )
    parser.add_argument("--workdir", "-w", default="work", help="Working directory")
    parser.add_argument(
        "--docker", action="store_true", default=True, help="Run via Docker"
    )
    parser.add_argument("--no-docker", action="store_false", dest="docker")
    parser.add_argument(
        "--image", default="nvcr.io/hpc/gromacs:2023.2", help="Docker image"
    )
    parser.add_argument(
        "--cpus",
        type=int,
        default=default_cpus,
        help=f"Maximum number of CPUs for GROMACS (Default: {default_cpus})",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only plot and generate individual HTML reports, do not execute GROMACS commands",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Archive results and upload to external service",
    )
    args = parser.parse_args()
    args.host_root = os.path.dirname(os.path.abspath(__file__))
    outdir = os.path.abspath(args.outdir)
    workdir = os.path.abspath(args.workdir)
    os.makedirs(workdir, exist_ok=True)

    config_path = os.path.abspath(args.config)
    cfg = load_config(config_path) if os.path.exists(config_path) else {}

    complexes = []

    # 1. Selection by explicit names
    if args.select:
        complexes = args.select
    # 2. Selection by Protein/Ligand IDs
    elif args.protein or args.ligand or (cfg.get("proteins") and cfg.get("ligands")):
        protein_ids = []
        if args.protein:
            for p in args.protein:
                protein_ids.append(os.path.splitext(os.path.basename(p))[0])
        if "proteins" in cfg:
            for p in cfg["proteins"]:
                # Consistently use filename base for protein IDs as workflow.py does
                protein_ids.append(os.path.splitext(os.path.basename(p["file"]))[0])

        ligand_ids = []
        if args.ligand:
            for l in args.ligand:
                ligand_ids.append(os.path.splitext(os.path.basename(l))[0])
        if "ligands" in cfg:
            for l in cfg["ligands"]:
                l_id = l.get("id") or (
                    os.path.splitext(os.path.basename(l["file"]))[0]
                    if "file" in l
                    else "unknown"
                )
                ligand_ids.append(l_id)

        protein_ids = list(set(protein_ids))
        ligand_ids = list(set(ligand_ids))

        for pid in protein_ids:
            for lid in ligand_ids:
                complexes.append(f"{pid}_{lid}")
    # 3. Auto-scan if nothing else specified
    else:
        if args.master_only:
            logger.info("Scanning output directory for completed analysis directories...")
            analysis_dirs = glob.glob(os.path.join(outdir, "analysis_*"))
            for d in analysis_dirs:
                if os.path.isdir(d):
                    name = os.path.basename(d).replace("analysis_", "")
                    complexes.append(name)
        else:
            logger.info("Scanning output directory for completed MD complexes...")
            xtc_files = glob.glob(os.path.join(outdir, "*_md.xtc"))
            for f in xtc_files:
                name = os.path.basename(f).replace("_md.xtc", "")
                complexes.append(name)

    if not complexes:
        logger.error("No complexes identified for analysis.")
        return

    logger.info(f"Identified {len(complexes)} complexes.")

    # Change to work directory for GROMACS temporary files
    original_cwd = os.getcwd()
    os.chdir(workdir)

    all_results = []
    try:
        for comp in complexes:
            if args.master_only:
                res = reconstruct_result(comp, outdir)
            else:
                res = analyze_complex(comp, outdir, workdir, cfg, args)

            if res:
                all_results.append(res)

        if all_results:
            # Override filename if provided
            report_name = args.master_output
            if not report_name.endswith(".html"):
                report_name += ".html"

            master_report = generate_master_report(all_results, outdir)
            # If the name is different from default, rename it
            default_path = os.path.join(outdir, "master_analysis_report.html")
            final_path = os.path.join(outdir, report_name)
            if default_path != final_path:
                shutil.move(default_path, final_path)

            logger.info(f"--- Master Comparison Report Generated: {final_path} ---")

            # Auto-upload if requested
            if args.upload:
                archive_and_upload(outdir)

        else:
            logger.warning("No results collected for master report.")
    finally:
        os.chdir(original_cwd)


if __name__ == "__main__":
    main()
