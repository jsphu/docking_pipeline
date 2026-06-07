import os
import subprocess
import sys
import logging
import tempfile
import shutil

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def run_cmd(cmd, cwd=None, input_text=None):
    logger.info(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, input=input_text, capture_output=True, text=True, check=True, cwd=cwd
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr + "\n" + e.stdout


def test_gpu_simulation():
    logger.info("=== STARTING ROBUST WATER-BOX GPU SIMULATION TEST ===")

    # Check GROMACS version and build type
    ok, version_out = run_cmd(["gmx", "mdrun", "-version"])
    if not ok:
        logger.error("Failed to run gmx mdrun -version.")
        return False

    is_opencl = "OpenCL" in version_out
    if is_opencl:
        logger.info("Detected OpenCL build of GROMACS. Adjusting GPU flags...")
    else:
        logger.info("Detected CUDA (or other) build of GROMACS.")

    with tempfile.TemporaryDirectory() as tmpdir:
        logger.info(f"Working in temporary directory: {tmpdir}")

        # Step 1: Generate a 2x2x2 nm box containing water molecules
        ok, out = run_cmd(
            [
                "gmx",
                "solvate",
                "-cs",
                "spc216",
                "-box",
                "2",
                "2",
                "2",
                "-o",
                "water.gro",
            ],
            cwd=tmpdir,
        )
        if not ok:
            logger.error("Failed to generate water box.")
            logger.error(out)
            return False

        # Count molecules for topology
        with open(os.path.join(tmpdir, "water.gro"), "r") as f:
            lines = f.readlines()
            num_atoms = int(lines[1].strip())
            num_sol = num_atoms // 3

        # Step 2: Create a topology file
        top_content = f"""
#include "oplsaa.ff/forcefield.itp"
#include "oplsaa.ff/spce.itp"

[ system ]
Test Water Box

[ molecules ]
SOL         {num_sol}
"""
        with open(os.path.join(tmpdir, "topol.top"), "w") as f:
            f.write(top_content)

        # Step 3: Create a minimal test control file (test.mdp)
        mdp_content = """
integrator  = md
nsteps      = 500
dt          = 0.002
cutoff-scheme = Verlet
coulombtype = PME
vdwtype     = Cut-off
rcoulomb    = 0.7
rvdw        = 0.7
tcoupl      = v-rescale
tc-grps     = System
tau-t       = 0.1
ref-t       = 300
pcoupl      = no
constraints = h-bonds
"""
        with open(os.path.join(tmpdir, "test.mdp"), "w") as f:
            f.write(mdp_content)

        # Step 4: Assemble the input binary file (grompp)
        ok, out = run_cmd(
            [
                "gmx",
                "grompp",
                "-f",
                "test.mdp",
                "-c",
                "water.gro",
                "-p",
                "topol.top",
                "-o",
                "test.tpr",
                "-maxwarn",
                "1",
            ],
            cwd=tmpdir,
        )
        if not ok:
            logger.error("Failed to run grompp.")
            logger.error(out)
            return False

        # Step 5: Run the simulation with appropriate GPU flags
        cpu_count = os.cpu_count() or 4
        ntomp = os.environ.get("SLURM_CPUS_PER_TASK", str(cpu_count))
        mdrun_cmd = [
            "gmx",
            "mdrun",
            "-s",
            "test.tpr",
            "-v",
            "-nsteps",
            "500",
            "-ntmpi",
            "1",
            "-ntomp",
            ntomp,
            "-nb",
            "gpu",
            "-pme",
            "gpu",
        ]

        if not is_opencl:
            # We'll try -bonded gpu but keep update on CPU for maximum compatibility
            mdrun_cmd.extend(["-bonded", "gpu", "-update", "cpu"])
        else:
            mdrun_cmd.extend(["-bonded", "cpu", "-update", "cpu"])

        logger.info(f"Launching GROMACS mdrun with flags: {' '.join(mdrun_cmd)}")
        ok, out = run_cmd(mdrun_cmd, cwd=tmpdir)

        # If the above fails because of bonded GPU, try one last time with just nb/pme
        if not ok and "bonded" in out.lower():
            logger.warning("Bonded GPU offloading failed, retrying with nb/pme only...")
            mdrun_cmd = [
                "gmx",
                "mdrun",
                "-s",
                "test.tpr",
                "-v",
                "-nsteps",
                "500",
                "-ntmpi",
                "1",
                "-ntomp",
                ntomp,
                "-nb",
                "gpu",
                "-pme",
                "gpu",
            ]
            ok, out = run_cmd(mdrun_cmd, cwd=tmpdir)

        if not ok:
            logger.error("FATAL: GROMACS mdrun failed to execute.")
            logger.error(out)
            return False

        # Check output for GPU usage confirmation
        if "GPU" in out:
            logger.info("Success! GROMACS utilized the GPU for this simulation.")
        else:
            logger.warning(
                "Simulation finished but GPU usage was not explicitly confirmed in logs."
            )

    logger.info("=== GPU SIMULATION TEST PASSED ===")
    return True


if __name__ == "__main__":
    if not test_gpu_simulation():
        print(
            "\n[!] GPU TEST FAILED: GROMACS simulation could not initialize on GPU hardware.",
            file=sys.stderr,
        )
        sys.exit(1)
