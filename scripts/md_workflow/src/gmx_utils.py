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


def run_command(cmd, shell=False, cwd=None, env=None, cpus=None):
    """Utility to run shell commands and handle errors with real-time logging."""
    logger.info(f"Running: {' '.join(cmd) if isinstance(cmd, list) else cmd}")

    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    
    if cpus:
        full_env["OMP_NUM_THREADS"] = str(cpus)
    
    lib_path = setup_acpype_libs()
    if lib_path:
        existing_ld = full_env.get("LD_LIBRARY_PATH", "")
        full_env["LD_LIBRARY_PATH"] = (
            f"{lib_path}:{existing_ld}" if existing_ld else lib_path
        )

    try:
        process = subprocess.Popen(
            cmd, 
            shell=shell, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            env=full_env, 
            cwd=cwd,
            bufsize=1
        )

        for line in process.stdout:
            clean_line = line.strip()
            if clean_line:
                logger.info(f"[CMD] {clean_line}")

        process.wait()
        
        if process.returncode != 0:
            logger.error(f"Command failed with Exit Code {process.returncode}")
            return False
        return True
    except Exception as e:
        logger.error(f"Failed to run command: {e}")
        return False


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
    cpus=None,
):
    """Utility to run GROMACS commands locally or via Docker with real-time logging."""
    gmx_cmd = ["gmx"] + args

    # Map input/output files to command arguments
    if input_files:
        for flag, path in input_files.items():
            gmx_cmd.extend([flag, path])
    if output_files:
        for flag, path in output_files.items():
            gmx_cmd.extend([flag, path])

    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    if cpus:
        full_env["OMP_NUM_THREADS"] = str(cpus)

    if not use_docker:
        full_cmd = gmx_cmd
        target_cwd = cwd
    else:
        # Docker mode
        project_root = host_root or os.getcwd()
        container_workdir = "/workflow"
        if cwd:
            abs_cwd = os.path.abspath(cwd)
            if abs_cwd.startswith(project_root):
                container_workdir = abs_cwd.replace(project_root, "/workflow")

        docker_base = ["docker", "run", "--gpus", "all", "-i", "--rm"]
        if cpus:
            docker_base.extend(["--cpus", str(cpus)])
        docker_base.extend([
            "-v", f"{project_root}:/workflow",
            "-w", container_workdir,
            "-u", f"{os.getuid()}:{os.getgid()}",
            image,
        ])

        mapped_gmx_cmd = []
        for part in gmx_cmd:
            if isinstance(part, str) and part.startswith(project_root):
                mapped_gmx_cmd.append(part.replace(project_root, "/workflow"))
            else:
                mapped_gmx_cmd.append(str(part))

        full_cmd = docker_base + mapped_gmx_cmd
        target_cwd = None # Docker handles workdir

    logger.info(f"Executing: {' '.join(full_cmd)}")
    
    try:
        # We use Popen to stream output to our logger (and thus to the --log file)
        process = subprocess.Popen(
            full_cmd,
            stdin=subprocess.PIPE if stdin else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Merge stderr into stdout for combined logging
            text=True,
            env=full_env,
            cwd=target_cwd,
            bufsize=1, # Line buffered
        )

        if stdin:
            # If stdin is provided, we send it and then close
            process.stdin.write(stdin)
            process.stdin.close()

        # Stream the output line by line to the logger
        for line in process.stdout:
            clean_line = line.strip()
            if clean_line:
                logger.info(f"[GMX] {clean_line}")

        process.wait()
        
        if process.returncode != 0:
            logger.error(f"GMX Command failed with Exit Code {process.returncode}")
            return False
        return True
        
    except Exception as e:
        logger.error(f"Failed to execute GMX command: {e}")
        return False
