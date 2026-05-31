#!/usr/bin/env bash
set -e

echo "=== GROMACS GPU Pipeline Test ==="

# Auto-detect CPU features to select the fastest GROMACS binary
CPU_FLAGS=$(cat /proc/cpuinfo)

if echo "$CPU_FLAGS" | grep -q "avx512f"; then
  GMX_BIN="/usr/local/gromacs/avx_512/bin/gmx"
elif echo "$CPU_FLAGS" | grep -q "avx2"; then
  GMX_BIN="/usr/local/gromacs/avx2_256/bin/gmx"
elif echo "$CPU_FLAGS" | grep -q "avx"; then
  GMX_BIN="/usr/local/gromacs/avx_256/bin/gmx"
else
  GMX_BIN="/usr/local/gromacs/sse4.1/bin/gmx"
fi

echo "Selected optimized GROMACS binary: $GMX_BIN"

# 1. Clean up old files from previous runs
echo "Cleaning working directory..."
rm -f water.gro topol.top test.mdp test.tpr confout.gro ener.edr md.log state.cpt traj.trr

# 2. Generate the coordinates
echo "Generating water coordinates..."
$GMX_BIN solvate -cs spc216 -box 3 3 3 -o water.gro

# 2b. Dynamically extract the exact number of water molecules generated
# It parses the number of 'SOL' occurrences in the final coordinate entries
NUM_SOL=$(grep -c "SOL" water.gro || true)
# Since there are 3 atoms per water molecule, divide the total matched atoms by 3
NUM_SOL=$((NUM_SOL / 3))

echo "Detected $NUM_SOL water molecules generated. Updating topology..."

# 3. Create the topology file using the dynamic count
echo "Writing topology file..."
cat <<EOF >topol.top
; Include forcefield parameters
#include "amber99sb-ildn.ff/forcefield.itp"

; Include water topology
#include "amber99sb-ildn.ff/spce.itp"

[ system ]
Pure Water Box Test

[ molecules ]
SOL               $NUM_SOL
EOF

# 4. Create the simulation settings file
echo "Writing MDP configurations..."
cat <<'EOF' >test.mdp
; Run control
integrator              = md
nsteps                  = 1000
dt                      = 0.002

; Neighbor searching and electrostatics
cutoff-scheme           = Verlet
nstlist                 = 10
rlist                   = 0.9
coulombtype             = PME
rcoulomb                = 0.9
rvdw                    = 0.9

; Temperature coupling
tcoupl                  = v-rescale
tc-grps                 = System
tau-t                   = 0.1
ref-t                   = 300

; Pressure coupling
pcoupl                  = no

; Velocity generation
gen-vel                 = yes
gen-temp                = 300

; Constraints
constraints             = h-bonds
EOF

# 5. Assemble the simulation binary input
echo "Compiling system parameters with grompp..."
$GMX_BIN grompp -f test.mdp -c water.gro -p topol.top -o test.tpr

# 6. Execute mdrun utilizing GPU offloading
echo "Launching mdrun on GPU..."
$GMX_BIN mdrun -s test.tpr -v -nb gpu -pme gpu

echo "=== Pipeline Completed Successfully ==="
