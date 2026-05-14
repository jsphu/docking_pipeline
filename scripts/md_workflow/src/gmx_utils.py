import os
import logging
import subprocess

logger = logging.getLogger(__name__)


def setup_acpype_libs():
    """
    Returns the path to acpype's internal library folder.
    """
    try:
        import acpype

        acpype_dir = os.path.dirname(acpype.__file__)
        original_lib_path = os.path.join(acpype_dir, "amber_linux", "lib")
        if os.path.exists(original_lib_path):
            return original_lib_path
    except ImportError:
        pass
    return None


def run_command(cmd, shell=False, cwd=None):
    """Utility to run shell commands and handle errors."""
    logger.info(f"Running: {' '.join(cmd) if isinstance(cmd, list) else cmd}")

    env = os.environ.copy()
    lib_path = setup_acpype_libs()
    if lib_path:
        existing_ld = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = (
            f"{lib_path}:{existing_ld}" if existing_ld else lib_path
        )

    result = subprocess.run(
        cmd, shell=shell, capture_output=True, text=True, env=env, cwd=cwd
    )
    if result.returncode != 0:
        logger.error(f"Error (Exit Code {result.returncode}):")
        logger.error(f"STDOUT: {result.stdout}")
        logger.error(f"STDERR: {result.stderr}")
        return False
    return True


def run_gmx(
    args,
    input_files=None,
    output_files=None,
    stdin=None,
    env=None,
    cwd=None,
    use_docker=False,
    image="nvcr.io/hpc/gromacs:2023.2",
    host_root=None,
):
    """Utility to run GROMACS commands locally or via Docker."""
    gmx_cmd = ["gmx"] + args

    # Map input/output files to command arguments
    if input_files:
        for flag, path in input_files.items():
            gmx_cmd.extend([flag, path])
    if output_files:
        for flag, path in output_files.items():
            gmx_cmd.extend([flag, path])

    if not use_docker:
        # Fallback to local gmxapi or subprocess
        if stdin:
            result = subprocess.run(
                gmx_cmd, input=stdin, capture_output=True, text=True, env=env, cwd=cwd
            )
            if result.returncode != 0:
                logger.error(f"Error: {result.stderr}")
                return False
            return True
        return run_command(gmx_cmd, env=env, cwd=cwd)
    else:
        # Docker mode
        project_root = host_root or os.getcwd()

        container_workdir = "/workflow"
        if cwd:
            abs_cwd = os.path.abspath(cwd)
            if abs_cwd.startswith(project_root):
                container_workdir = abs_cwd.replace(project_root, "/workflow")

        docker_base = [
            "docker",
            "run",
            "--gpus",
            "all",
            "-i",
            "--rm",
            "-v",
            f"{project_root}:/workflow",
            "-w",
            container_workdir,
            "-u",
            f"{os.getuid()}:{os.getgid()}",
            image,
        ]

        # Map all paths in gmx_cmd to be relative to /workflow
        mapped_gmx_cmd = []
        for part in gmx_cmd:
            if isinstance(part, str) and part.startswith(project_root):
                mapped_gmx_cmd.append(part.replace(project_root, "/workflow"))
            else:
                mapped_gmx_cmd.append(str(part))

        full_cmd = docker_base + mapped_gmx_cmd
        logger.info(f"Docker Running: {' '.join(full_cmd)}")
        result = subprocess.run(full_cmd, input=stdin, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Docker Error (Code {result.returncode}):\n{result.stderr}")
            return False
        return True
