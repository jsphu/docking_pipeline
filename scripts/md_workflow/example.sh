#!/usr/bin/env bash

echo "Welcome to examples."
echo ""
echo "This scripts main purpose is to serve you"
echo "to understand usage of the pipeline"
echo ""
echo "This script will not run the pipeline."
echo ""

echo "This pipeline is made for users who do not want to"
echo "process the confusing steps of gromacs, but it is"
echo "always good practice to learn it from the bests."
echo "Check professional tutorials of gromacs for beginners."
echo "||      mdtutorials.com/gmx     ||"
echo "You can understand and learn every step here."
echo "This script is only to guide you for to run the pipeline."
echo ""
echo "If you are ready,"
read -p "type [y] to proceed... " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo "See you later!"
  exit 1
fi

echo -e "\n\n\n\n\n\n"
echo "In the first guide, this pipeline is written with python3."
echo "So if you are going to use the pipeline you need to activate the"
echo "python environment first."
echo ""
echo "You can use 'conda' to activate the environment."
echo "If you did run 'conda.install' and 'docker.install', you"
echo "should have an environment called 'md_env'"
echo "You need to activate it before launching the workflow."
echo "Type this ||    conda activate md_env     ||"
read -p "Proceed to next guide: [y/n]? " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo "See you later!"
  exit 1
fi

echo -e "\n\n\n\n\n\n"
echo "Great, you have a conda environment, now lets look at"
echo "our help to understand what is going on."
echo "Type this ||    python3 md_workflow.py --help   ||"
echo "(NOTE) The script will handle it, do not exit now."
read -p "Type [y] to proceed. " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo "See you later!"
  exit 1
fi
echo -e "\n\n\n\n\n\n"

cat <<'EOF'
usage: md_workflow.py [-h] [--config CONFIG] [--protein PROTEIN [PROTEIN ...]]
                      [--ligand LIGAND [LIGAND ...]] [--outdir OUTDIR]
                      [--workdir WORKDIR] [--gpu] [--no-gpu] [--docker]
                      [--no-docker] [--image IMAGE] [--skip-prep]

Automated MD Workflow for Protein-Ligand Complexes

options:
  -h, --help            show this help message and exit
  --config, -c CONFIG   Path to config file
  ... [hidden 13 lines for simplicity]
EOF

echo ""
echo "Now we can see the help message."
echo "Lets look at first the 'config'"
echo "You can find an example of config inside here"
echo "Run this: ||    cat config.json     ||"
echo "(NOTE) The script will handle it, do not exit now."

read -p "Type [y] to proceed. " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo "See you later!"
  exit 1
fi
echo -e "\n\n\n\n\n\n"

cat <<'EOF'
{
  ... [hidden 22 lines for simplicity]
  "proteins": [{ "file": "5TBM.pdb", "id": "5TBM" }],
  "ligands": [
    {
      "file": "leads/5TBM_COMBINED-SCREENED-MOLECULES-35019-LOW_34389.pdbqt",
      "id": "COMBINED-SCREENED-MOLECULES-35019-LOW_34389",
      "SMILES": "O=C1CC=C(C=C1)c1nn(c2ccccc2)c(=O)c2c1cccc2"
    }
  ],
  "em": { "nsteps": 50000, "emtol": 1000.0, "emstep": 0.01 },
  "nvt": { "nsteps": 50000, "dt": 0.002, "tau_t": 0.1 },
  "npt": { "nsteps": 50000, "dt": 0.002, "tau_t": 0.1, "tau_p": 2.0 },
  "md": {
    "nsteps": 500000, "dt": 0.002, "tau_t": 0.1, "tau_p": 2.0,
    "nstxout": 0, "nstvout": 0, "nstfout": 0, "nstxtcout": 5000,
    "nstenergy": 5000, "nstlog": 5000
  }
}
EOF

echo ""
echo "There are many parameters interacting here."
echo "Don't worry! This guide breaks down exactly what they mean."
echo ""

read -p "Type [y] to proceed. " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo "See you later!"
  exit 1
fi
echo -e "\n\n\n\n\n\n"
cat <<'EOF'
----------------------------------------------------------------
EXAMINING CONFIGURATION SETTINGS (config.json)
----------------------------------------------------------------
The file coordinates structural algorithms, environments, and physics constants.

A. System Environment & Parameter Physics:
* force_field ("amber99sb-ildn"): Dictates the mathematical energy equations 
  used to calculate molecular bonds and atoms behaviors.
* water_model ("tip3p"): Implements a classic three-site rigid water molecule 
  matrix to solvate your system.
* box_type ("cubic") & box_buffer (1.0): Places the protein-ligand structure 
  in a cube and adds a 1.0 nm safety padding buffer to its boundaries so the 
  macromolecule does not interact with its own periodic images.

B. Electrostastics & Boundaries:
* coulombtype ("PME"): Uses Particle Mesh Ewald summation to evaluate long-range 
  electrostatic forces precisely without slowing down your system.
* cutoff_scheme ("Verlet"): A grid-based neighborhood list engine that figures 
  out which atoms are close enough to exert non-bonded forces on each other.

C. Detailed Phase Breakdowns:
* em (Energy Minimization): Relaxes the structure. It takes small steps (emstep: 0.01) 
  until structural forces settle below the tolerated threshold (emtol: 1000.0).
* nvt (Constant Number, Volume, Temperature): Heats up your system to 300K 
  smoothly utilizing a time-step scale (dt: 0.002 ps).
* npt (Constant Number, Pressure, Temperature): Stabilizes the system pressure 
  to 1.0 bar, utilizing isotropic scaling (compressibility: 4.5e-5).
* md (Production Run): The final collection run. It simulates 500,000 steps 
  of real structural movement, logging trajectories (nstxtcout) and energies 
  every 5,000 intervals.

EOF

echo "These all needed parameters for gromacs to work."
echo "But we are not worrying about them now."
echo "Let's see what is the most important for us (this pipeline)."

read -p "Type [y] to proceed. " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo "See you later!"
  exit 1
fi
echo -e "\n\n\n\n\n\n"

echo "We have 2 fields inside config file."
echo "'proteins' and 'ligands'"
echo "They are taking a list of objects."
echo "Which should look like this:"
cat <<'EOF'
  proteins: [
    { "file": "relative/path/to/protein/pdb-or-pdbqt"
        //    ^^^^^^^^^^^ relative to the config file.
        //    as an example (pdbs/protein.pdb):
        //        | config.json
        //        | pdbs/
        //        --| protein.pdb
        //          | ligand.smi
        //        | md_workflow.py
        //        | src/
        //
        //    in this tree, protein.pdb can be found like this:
        //          "file": "pdbs/protein.pdb"

      "id": "unique-name-for-molecule" // anything approved.
    }
  ],

EOF
echo "Two important fields: 'id' and 'file'"
echo "Next ligands:"
read -p "Type [y] to proceed. " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo "See you later!"
  exit 1
fi
echo -e "\n\n\n\n\n\n"
cat <<'EOF'
  ligands: [
    { "file": "relative/path/to/ligand/pdbqt"
        //    ^^^^^^^^^^^ relative to the config file.
        //    relation is same as proteins.
        //    the file must be docking poses, to align the
        //    posing for proteins. You need to do docking first.

      "id": "unique-name-for-molecule" // anything approved.
      "SMILES": "O=C(c1nn(C)c(=O)c2c1cccc2)Nc1cccc2c1cccc2" // smiles format of ligand
        //       ^^^^^^ this is an example smiles.
        //       this is needed if the preperation fails to build molecular format.
    },
    { "file": ... // you can add as long as you want.
    } // <-- do not forget to removing trailing comma at the last item.
  ],

EOF
read -p "Type [y] to proceed. " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo "See you later!"
  exit 1
fi
echo -e "\n\n\n\n\n\n"
# Detailed educational breakdown starts here
cat <<'EOF'
----------------------------------------------------------------
CLI ARGUMENTS EXPLORATION (md_workflow.py)
----------------------------------------------------------------
The script takes flags directly from your command terminal to control 
how it executes your Molecular Dynamics jobs.

* --config (-c): Passes a JSON configuration path. If you define variables 
  here, they override or set up defaults for the run.
* --protein (-p) & --ligand (-l): Allows you to feed raw structures directly.
  You can point directly to single files or whole directories containing your 
  screened compounds.
* --gpu / --no-gpu: Tells GROMACS whether it should use your NVIDIA hardware. 
  Highly recommended to keep --gpu active on WSL to finish steps infinitely faster.
* --docker / --no-docker: Explicitly instructs Python whether to execute commands
  via local packages or send tasks straight to an isolated container.

EOF
read -p "Type [y] to proceed. " -rsn1 isY
if [[ ${isY,,} != "y" ]]; then
  echo "See you later!"
  exit 1
fi
echo -e "\n\n\n\n\n\n"

echo "That is all for now. you can start running your first GPU with docker pipeline:"
echo ""
echo "||  python3 md_workflow.py -c config.json -w work/ -o results --gpu --docker  ||"
echo ""
echo "That's all! you are good to go!"
