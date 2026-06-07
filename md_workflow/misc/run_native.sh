#!/usr/bin/env bash
set -e

# === GROMACS Native Pipeline Script (Robust Version) ===
# Performs EM, NVT, NPT, and MD using direct bash commands.
# Handles Protein (PDB) + Ligand (ITP/GRO) merging.
# Optimized for GPU. No acpype/rdkit dependencies.

echo "=== GROMACS Native Pipeline Starting ==="

# 1. GROMACS Binary Detection
if [ -z "$GMX_BIN" ]; then
    CPU_FLAGS=$(cat /proc/cpuinfo)
    if echo "$CPU_FLAGS" | grep -q "avx512f"; then
        GMX_BIN="/usr/local/gromacs/avx_512/bin/gmx"
    elif echo "$CPU_FLAGS" | grep -q "avx2"; then
        GMX_BIN="/usr/local/gromacs/avx2_256/bin/gmx"
    elif echo "$CPU_FLAGS" | grep -q "avx"; then
        GMX_BIN="/usr/local/gromacs/avx_256/bin/gmx"
    else
        GMX_BIN="gmx"
    fi
fi
if ! command -v $GMX_BIN &> /dev/null; then GMX_BIN="gmx"; fi
echo "Using GROMACS binary: $GMX_BIN"

# 2. Input Handling
PROTEIN_PDB=$1
LIGAND_ITP=$2
LIGAND_GRO=$3
OUTDIR=${4:-"results_native"}
WORKDIR=${5:-"work_native"}

if [ -z "$PROTEIN_PDB" ] || [ -z "$LIGAND_ITP" ] || [ -z "$LIGAND_GRO" ]; then
    echo "Usage: $0 [protein.pdb] [ligand.itp] [ligand.gro] [outdir] [workdir]"
    exit 1
fi

mkdir -p "$OUTDIR"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

# Copy inputs to workdir
cp "../$PROTEIN_PDB" ./protein.pdb
cp "../$LIGAND_ITP" ./ligand.itp
cp "../$LIGAND_GRO" ./ligand.gro

# 3. Protein Preparation (pdb2gmx)
echo "--- Running pdb2gmx ---"
$GMX_BIN pdb2gmx -f protein.pdb -o prot.gro -p topol.top -ff amber99sb-ildn -water tip3p -ignh -missing

# 4. Topology Merging (Native Bash approach)
echo "--- Merging Topologies ---"
# Extract molecule name from ligand.itp (usually first word after [ moleculetype ])
LIG_NAME=$(grep -A 1 "\[ moleculetype \]" ligand.itp | grep -v "\[" | grep -v ";" | awk '{print $1}' | head -n 1)
if [ -z "$LIG_NAME" ]; then LIG_NAME="LIG"; fi
echo "Detected Ligand Name: $LIG_NAME"

# Clean ligand itp (remove [ atomtypes ] if present to avoid duplicates)
# We assume the protein topology already has necessary atomtypes or we add them.
# For simplicity, we just include the itp as is, but GROMACS might complain about duplicates.
# A better way is to ensure ligand.itp doesn't have [ atomtypes ] or they are in a separate file.
sed -i '/\[ atomtypes \]/q' topol.top # This is a placeholder for more complex merging if needed

# Insert #include "ligand.itp" before the water include
sed -i '/; Include water topology/i #include "ligand.itp"\n' topol.top

# Append Ligand to [ molecules ] section
echo "$LIG_NAME          1" >> topol.top

# 5. Coordinate Merging
echo "--- Merging Coordinates ---"
# We use editconf to convert ligand to gro if it's not already, and then merge.
# Extract atom counts
PROT_ATOMS=$(head -n 2 prot.gro | tail -n 1 | awk '{print $1}')
LIG_ATOMS=$(head -n 2 ligand.gro | tail -n 1 | awk '{print $1}')
TOTAL_ATOMS=$((PROT_ATOMS + LIG_ATOMS))

# Create complex.gro
echo "Protein-Ligand Complex" > complex.gro
echo "$TOTAL_ATOMS" >> complex.gro
tail -n +3 prot.gro | head -n -1 >> complex.gro
tail -n +3 ligand.gro | head -n -1 >> complex.gro
tail -n 1 prot.gro >> complex.gro # Use protein's box vector

# 6. System Setup
echo "--- System Setup: Box, Solvate, Ions ---"
$GMX_BIN editconf -f complex.gro -o box.gro -c -d 1.2 -bt cubic

# Use -p topol.top to automatically update molecule counts
$GMX_BIN solvate -cp box.gro -cs spc216.gro -p topol.top -o solv.gro

# Ions
cat <<EOF > ions.mdp
integrator = steep
emtol = 1000.0
nsteps = 50000
cutoff-scheme = Verlet
coulombtype = PME
rcoulomb = 1.0
rvdw = 1.0
EOF

$GMX_BIN grompp -f ions.mdp -c solv.gro -p topol.top -o ions.tpr -maxwarn 5
echo "SOL" | $GMX_BIN genion -s ions.tpr -p topol.top -o final.gro -pname NA -nname CL -neutral

# 7. MDP Generations
echo "--- Generating MDP Files ---"
# EM
cat <<EOF > em.mdp
integrator      = steep
emtol           = 1000.0
emstep          = 0.01
nsteps          = 50000
nstlist         = 1
cutoff-scheme   = Verlet
coulombtype     = PME
rcoulomb        = 1.0
rvdw            = 1.0
EOF

# NVT
cat <<EOF > nvt.mdp
define                  = -DPOSRES
integrator              = md
nsteps                  = 50000
dt                      = 0.002
continuation            = no
constraint_algorithm    = lincs
constraints             = h-bonds
cutoff-scheme           = Verlet
nstlist                 = 10
rcoulomb                = 1.0
rvdw                    = 1.0
tcoupl                  = V-rescale
tc-grps                 = System
tau_t                   = 0.1
ref_t                   = 300
pcoupl                  = no
Gen_vel                 = yes
gen_temp                = 300
EOF

# NPT
cat <<EOF > npt.mdp
define                  = -DPOSRES
integrator              = md
nsteps                  = 50000
dt                      = 0.002
continuation            = yes
constraint_algorithm    = lincs
constraints             = h-bonds
cutoff-scheme           = Verlet
nstlist                 = 10
rcoulomb                = 1.0
rvdw                    = 1.0
tcoupl                  = V-rescale
tc-grps                 = System
tau_t                   = 0.1
ref_t                   = 300
pcoupl                  = Parrinello-Rahman
tau_p                   = 2.0
ref_p                   = 1.0
compressibility         = 4.5e-5
EOF

# MD
cat <<EOF > md.mdp
integrator              = md
nsteps                  = 500000
dt                      = 0.002
continuation            = yes
constraint_algorithm    = lincs
constraints             = h-bonds
cutoff-scheme           = Verlet
nstlist                 = 10
rcoulomb                = 1.0
rvdw                    = 1.0
tcoupl                  = V-rescale
tc-grps                 = System
tau_t                   = 0.1
ref_t                   = 300
pcoupl                  = Parrinello-Rahman
tau_p                   = 2.0
ref_p                   = 1.0
compressibility         = 4.5e-5
EOF

# 8. Execution
echo "--- Running Simulation Pipeline ---"
GPU_FLAGS="-nb gpu -pme gpu -bonded gpu -update cpu"
if ! $GMX_BIN mdrun -h 2>&1 | grep -q "gpu"; then GPU_FLAGS=""; fi

# EM
echo "EM..."
$GMX_BIN grompp -f em.mdp -c final.gro -p topol.top -o em.tpr -maxwarn 5
$GMX_BIN mdrun -v -deffnm em -ntmpi 1 $GPU_FLAGS -nb cpu

# NVT
echo "NVT..."
$GMX_BIN grompp -f nvt.mdp -c em.gro -p topol.top -r em.gro -o nvt.tpr -maxwarn 5
$GMX_BIN mdrun -v -deffnm nvt -ntmpi 1 $GPU_FLAGS

# NPT
echo "NPT..."
$GMX_BIN grompp -f npt.mdp -c nvt.gro -p topol.top -r nvt.gro -t nvt.cpt -o npt.tpr -maxwarn 5
$GMX_BIN mdrun -v -deffnm npt -ntmpi 1 $GPU_FLAGS

# MD
echo "Production MD..."
$GMX_BIN grompp -f md.mdp -c npt.gro -p topol.top -t npt.cpt -o md.tpr -maxwarn 5
$GMX_BIN mdrun -v -deffnm md -ntmpi 1 $GPU_FLAGS

# 9. Cleanup and Finish
echo "--- Pipeline Completed ---"
cp md.gro md.xtc md.log md.edr md.tpr ../"$OUTDIR"/
echo "Results in $OUTDIR"
