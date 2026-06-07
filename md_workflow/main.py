import argparse
import sys
import os
import subprocess


def main():
    description = """
Bio-Workflow CLI: A unified interface for Molecular Dynamics workflows.

Available Commands:
  workflow  - Run the full MD simulation pipeline (Ligand prep -> GROMACS -> MD).
  post-md   - Perform trajectory analysis (RMSD, RMSF, Rg) and generate reports.
  plot      - Generate high-quality plots from GROMACS .xvg files.
  server    - Start the FastAPI web server for status monitoring and notifications.
  misc      - Run utility scripts (installers, smoke tests, etc.) from misc/ folder.
"""
    epilog = """
Examples:
  python main.py workflow --protein protein.pdb --ligand ligand.sdf
  python main.py post-md --outdir results/ --select complex_1
  python main.py plot data.xvg -o plot.png
  python main.py misc smoke-test
"""
    parser = argparse.ArgumentParser(
        description=description,
        usage="python main.py <command> [args]",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", title="commands")

    # We add subparsers without help=False to show descriptions in the main help
    subparsers.add_parser("workflow", help="Automated MD simulation pipeline", add_help=False)
    subparsers.add_parser("post-md", help="Post-MD analysis and reporting", add_help=False)
    subparsers.add_parser("plot", help="XVG plotting utility", add_help=False)
    subparsers.add_parser("server", help="Monitoring and notification server", add_help=False)
    subparsers.add_parser("misc", help="Utility scripts from misc/ folder", add_help=False)

    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(1)

    args, remaining = parser.parse_known_args()

    # Reconstruct sys.argv for sub-mains
    sys.argv = [args.command] + remaining

    match args.command:
        case "workflow":
            from src.workflow import main as workflow_main

            workflow_main()

        case "post-md":
            from src.post_md import main as post_md_main

            post_md_main()

        case "plot":
            from misc.plotter import main as plotter_main

            plotter_main()

        case "server":
            from misc.server import main as server_main

            server_main()

        case "misc":
            if not remaining:
                print("Usage: misc <script> [args]")
                misc_dir = "misc"
                scripts = [""] + [
                    f
                    for f in os.listdir(misc_dir)
                    if os.path.isfile(os.path.join(misc_dir, f))
                    and not f.endswith(".pyc")
                    and not f.startswith("__")
                ]
                print(f"\nAvailable scripts: {'\n\t'.join(scripts)}")
                sys.exit(1)

            script_name = sys.argv.pop(1)
            misc_dir = "misc"

            # Mapping logic
            candidates = [
                script_name,
                f"{script_name}.sh",
                f"{script_name}.py",
                script_name.replace("-", "."),
                script_name.replace("-", "_"),
                f"{script_name.replace('-', '.')}.install",
                f"{script_name.replace('-', '.')}.kurulum",
                f"run_{script_name}.sh",
                f"run_{script_name.replace('-', '_')}.sh",
            ]

            script_path = None
            for cand in candidates:
                p = os.path.join(misc_dir, cand)
                if os.path.exists(p) and os.path.isfile(p):
                    script_path = p
                    break

            if not script_path:
                print(f"Error: Could not find script for '{script_name}' in misc/")
                sys.exit(1)

            print(f"Executing: {script_path} {' '.join(sys.argv[1:])}")
            if script_path.endswith(".py"):
                cmd = [sys.executable, script_path] + sys.argv[1:]
            else:
                # Assume shell/executable
                cmd = ["bash", script_path] + sys.argv[1:]

            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                sys.exit(e.returncode)

        case _:
            # This part might be redundant because argparse handles unknown commands,
            # but if dest="command" is None (though we checked len(sys.argv)), we handle it.
            parser.print_help()
            if args.command:
                print(f"Unknown command: {args.command}")
            sys.exit(1)


if __name__ == "__main__":
    main()
