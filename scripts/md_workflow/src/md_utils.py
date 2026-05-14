import os
import logging
from .gmx_utils import run_gmx

logger = logging.getLogger(__name__)


def generate_mdp_files(cfg, outdir):
    """Generates MDP files based on the provided configuration."""
    temp = cfg["temperature"]
    press = cfg["pressure"]

    mdps = {
        "em.mdp": f"""
integrator      = steep
emtol           = 10000.0
emstep          = 0.0005
nsteps          = 100000
nstlist         = 1
cutoff-scheme   = {cfg["cutoff_scheme"]}
coulombtype     = {cfg["coulombtype"]}
rcoulomb        = {cfg["rcoulomb"]}
rvdw            = {cfg["rvdw"]}
pbc             = xyz
""",
        "nvt.mdp": f"""
define                  = -DPOSRES
integrator              = md
nsteps                  = {cfg["nvt"]["nsteps"]}
dt                      = {cfg["nvt"]["dt"]}
nstxout                 = 500
nstvout                 = 500
nstenergy               = 500
nstlog                  = 500
continuation            = no
constraint_algorithm    = {cfg["constraint_algorithm"]}
constraints             = {cfg["constraints"]}
lincs_iter              = {cfg["lincs_iter"]}
lincs_order             = {cfg["lincs_order"]}
cutoff-scheme           = {cfg["cutoff_scheme"]}
nstlist                 = {cfg["nstlist"]}
rcoulomb                = {cfg["rcoulomb"]}
rvdw                    = {cfg["rvdw"]}
DispCorr                = {cfg["disp_corr"]}
coulombtype             = {cfg["coulombtype"]}
pme_order               = {cfg["pme_order"]}
fourierspacing          = {cfg["fourierspacing"]}
tcoupl                  = {cfg["tcoupl"]}
tc-grps                 = System
tau_t                   = {cfg["nvt"]["tau_t"]}
ref_t                   = {temp}
pcoupl                  = no
pbc                     = xyz
Gen_vel                 = yes
gen_temp                = {temp}
gen_seed                = -1
""",
        "npt.mdp": f"""
define                  = -DPOSRES
integrator              = md
nsteps                  = {cfg["npt"]["nsteps"]}
dt                      = {cfg["npt"]["dt"]}
nstxout                 = 500
nstvout                 = 500
nstenergy               = 500
nstlog                  = 500
continuation            = yes
constraint_algorithm    = {cfg["constraint_algorithm"]}
constraints             = {cfg["constraints"]}
lincs_iter              = {cfg["lincs_iter"]}
lincs_order             = {cfg["lincs_order"]}
cutoff-scheme           = {cfg["cutoff_scheme"]}
nstlist                 = {cfg["nstlist"]}
rcoulomb                = {cfg["rcoulomb"]}
rvdw                    = {cfg["rvdw"]}
DispCorr                = {cfg["disp_corr"]}
coulombtype             = {cfg["coulombtype"]}
pme_order               = {cfg["pme_order"]}
fourierspacing          = {cfg["fourierspacing"]}
tcoupl                  = {cfg["tcoupl"]}
tc-grps                 = System
tau_t                   = {cfg["npt"]["tau_t"]}
ref_t                   = {temp}
pcoupl                  = {cfg["pcoupl"]}
pcoupltype              = {cfg["pcoupltype"]}
tau_p                   = {cfg["npt"]["tau_p"]}
ref_p                   = {press}
compressibility         = {cfg["compressibility"]}
refcoord_scaling        = com
pbc                     = xyz
gen_vel                 = no
""",
        "md.mdp": f"""
integrator              = md
nsteps                  = {cfg["md"]["nsteps"]}
dt                      = {cfg["md"]["dt"]}
nstxout                 = {cfg["md"]["nstxout"]}
nstvout                 = {cfg["md"]["nstvout"]}
nstfout                 = {cfg["md"]["nstfout"]}
nstxtcout               = {cfg["md"]["nstxtcout"]}
nstenergy               = {cfg["md"]["nstenergy"]}
nstlog                  = {cfg["md"]["nstlog"]}
continuation            = yes
constraint_algorithm    = {cfg["constraint_algorithm"]}
constraints             = {cfg["constraints"]}
lincs_iter              = {cfg["lincs_iter"]}
lincs_order             = {cfg["lincs_order"]}
cutoff-scheme           = {cfg["cutoff_scheme"]}
nstlist                 = {cfg["nstlist"]}
rcoulomb                = {cfg["rcoulomb"]}
rvdw                    = {cfg["rvdw"]}
DispCorr                = {cfg["disp_corr"]}
coulombtype             = {cfg["coulombtype"]}
pme_order               = {cfg["pme_order"]}
fourierspacing          = {cfg["fourierspacing"]}
tcoupl                  = {cfg["tcoupl"]}
tc-grps                 = System
tau_t                   = {cfg["md"]["tau_t"]}
ref_t                   = {temp}
pcoupl                  = {cfg["pcoupl"]}
pcoupltype              = {cfg["pcoupltype"]}
tau_p                   = {cfg["md"]["tau_p"]}
ref_p                   = {press}
compressibility         = {cfg["compressibility"]}
pbc                     = xyz
gen_vel                 = no
""",
    }
    mdp_paths = {}
    for name, content in mdps.items():
        path = os.path.abspath(os.path.join(outdir, name))
        with open(path, "w") as f:
            f.write(content.strip())
        mdp_paths[name] = path
    logger.info(f"MDP files generated in {outdir}.")
    return mdp_paths


def run_step(
    step_name,
    mdp_path,
    gro,
    top,
    output_prefix,
    outdir,
    workdir,
    gpu=True,
    prev_cpt=None,
    use_docker=False,
    image="nvcr.io/hpc/gromacs:2023.2",
    host_root=None,
):
    """Runs a single GROMACS step using direct gmx calls (supporting Docker)."""
    target_dir = outdir if step_name == "md" else workdir
    tpr = os.path.abspath(os.path.join(target_dir, f"{output_prefix}_{step_name}.tpr"))

    grompp_args = ["grompp", "-maxwarn", "5"]
    if step_name in ["nvt", "npt"]:
        grompp_args.extend(["-r", gro])

    grompp_input = {"-f": mdp_path, "-c": gro, "-p": top}
    if prev_cpt:
        grompp_input["-t"] = prev_cpt

    if not run_gmx(
        grompp_args,
        input_files=grompp_input,
        output_files={"-o": tpr},
        use_docker=use_docker,
        image=image,
        host_root=host_root,
        cwd=target_dir,
    ):
        raise RuntimeError(f"grompp ({step_name}) failed")

    md_out_base = f"{output_prefix}_{step_name}"
    md_out_abs = os.path.abspath(os.path.join(target_dir, md_out_base))

    md_args = ["mdrun", "-deffnm", md_out_abs]
    if gpu and step_name != "em":
        md_args.extend(["-nb", "gpu", "-pme", "gpu", "-bonded", "gpu"])
    elif gpu and step_name == "em":
        # Force CPU for EM to avoid GPU crashes on high strain
        md_args.extend(["-nb", "cpu"])

    if not run_gmx(
        md_args,
        input_files={"-s": tpr},
        use_docker=use_docker,
        image=image,
        host_root=host_root,
        cwd=target_dir,
    ):
        if (
            not use_docker
        ):  # Only fallback if not using docker (docker should have correct drivers)
            logger.warning("Warning: GPU failed locally, falling back to CPU...")
            if not run_gmx(
                ["mdrun", "-deffnm", md_out_abs],
                input_files={"-s": tpr},
                cwd=target_dir,
            ):
                raise RuntimeError(f"mdrun ({step_name}) failed on CPU")
        else:
            raise RuntimeError(f"mdrun ({step_name}) failed in Docker")

    return os.path.abspath(f"{md_out_abs}.gro"), os.path.abspath(f"{md_out_abs}.cpt")
