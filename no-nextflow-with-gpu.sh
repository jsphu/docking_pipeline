#!/usr/bin/env bash
# =============================================================================
# run_gpu_docking.sh — Standalone Vina-GPU docking runner (no Nextflow)
#
# Give it a PDBQT file (single or multi-ligand). It will:
#   1. Run vina_split inside the Docker image to produce individual files
#   2. Seed the OpenCL kernel cache from the image
#   3. Run AutoDock-Vina-GPU-2-1 against the split ligands
#   4. Print a top-hits summary
#
# Usage:
#   ./run_gpu_docking.sh --ligand <file.pdbqt> [OPTIONS]
#
# Required:
#   --ligand PATH          Any PDBQT file — single ligand or multi-model library
#
# Optional:
#   --receptor PATH        Receptor PDBQT       [data/protein5TBM_prepared.pdbqt]
#   --outdir PATH          Results directory    [results]
#   --image NAME           Docker image         [vina-gpu:latest]
#   --center_x FLOAT                            [24.27]
#   --center_y FLOAT                            [-0.31]
#   --center_z FLOAT                            [-10.55]
#   --size_x FLOAT                              [10.0]
#   --size_y FLOAT                              [10.0]
#   --size_z FLOAT                              [10.0]
#   --exhaustiveness INT   Search depth         [8]
#   --thread_size INT      OpenCL threads       [1000]
#   --num_modes INT        Poses per ligand     [9]
#   --energy_range FLOAT   kcal/mol window      [3.0]
#   --override             Re-split even if split dir is already populated
#   --dry_run              Print the docker command without running
#   --help
# =============================================================================

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'
info() { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() {
  echo -e "${RED}[ERROR]${NC} $*" >&2
  exit 1
}
header() { echo -e "\n${BOLD}${CYAN}══ $* ══${NC}"; }

# ── Defaults ──────────────────────────────────────────────────────────────────
LIGAND=""
RECEPTOR="data/protein5TBM_prepared.pdbqt"
OUTDIR="results"
IMAGE="vina-gpu:latest"
CENTER_X=24.27
CENTER_Y=-0.31
CENTER_Z=-10.55
SIZE_X=10.0
SIZE_Y=10.0
SIZE_Z=10.0
EXHAUSTIVENESS=8
THREAD_SIZE=1000
NUM_MODES=9
ENERGY_RANGE=3.0
OVERRIDE=false
DRY_RUN=false

# ── Arg parsing ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
  --ligand)
    LIGAND="$2"
    shift 2
    ;;
  --receptor)
    RECEPTOR="$2"
    shift 2
    ;;
  --outdir)
    OUTDIR="$2"
    shift 2
    ;;
  --image)
    IMAGE="$2"
    shift 2
    ;;
  --center_x)
    CENTER_X="$2"
    shift 2
    ;;
  --center_y)
    CENTER_Y="$2"
    shift 2
    ;;
  --center_z)
    CENTER_Z="$2"
    shift 2
    ;;
  --size_x)
    SIZE_X="$2"
    shift 2
    ;;
  --size_y)
    SIZE_Y="$2"
    shift 2
    ;;
  --size_z)
    SIZE_Z="$2"
    shift 2
    ;;
  --exhaustiveness)
    EXHAUSTIVENESS="$2"
    shift 2
    ;;
  --thread_size)
    THREAD_SIZE="$2"
    shift 2
    ;;
  --num_modes)
    NUM_MODES="$2"
    shift 2
    ;;
  --energy_range)
    ENERGY_RANGE="$2"
    shift 2
    ;;
  --override)
    OVERRIDE=true
    shift
    ;;
  --dry_run)
    DRY_RUN=true
    shift
    ;;
  --help | -h)
    sed -n '2,37p' "$0" | sed 's/^# \?//; /^=\+$/d'
    exit 0
    ;;
  *) error "Unknown argument: $1  (run with --help)" ;;
  esac
done

# ── Validate ──────────────────────────────────────────────────────────────────
header "Validating inputs"

[[ -z "$LIGAND" ]] && error "--ligand is required. Example: --ligand data/IMiD_lib_2000.pdbqt"
[[ -f "$LIGAND" ]] || error "Ligand file not found: $LIGAND"
[[ -f "$RECEPTOR" ]] || error "Receptor file not found: $RECEPTOR"

command -v docker &>/dev/null || error "docker not found — please install Docker"
docker info &>/dev/null 2>&1 || error "Docker daemon not running or insufficient permissions"

if docker run --rm --gpus all --entrypoint nvidia-smi "$IMAGE" &>/dev/null 2>&1; then
  success "GPU accessible via Docker"
else
  warn "nvidia-smi check failed — continuing, but will abort inside container if no GPU"
fi

# Confirm vina_split is in the image
if ! docker run --rm --entrypoint sh "$IMAGE" -c "command -v vina_split" &>/dev/null 2>&1; then
  error "vina_split not found in image '$IMAGE'. Add it to your Dockerfile:
  RUN cp /opt/Vina-GPU-2.1/AutoDock-Vina-GPU-2.1/vina_split /usr/local/bin/ 2>/dev/null || \
      apt-get install -y autodock-vina"
fi
success "vina_split present in image"

# ── Work directories ──────────────────────────────────────────────────────────
LIGAND_STEM=$(basename "$LIGAND" .pdbqt)       # e.g. "IMiD_lib_2000"
WORK_DIR="$(pwd)/.docking_work/${LIGAND_STEM}" # isolated per input file
SPLIT_DIR="${WORK_DIR}/split"
KERNEL_DIR="${WORK_DIR}/kernels"
ABS_OUTDIR="$(realpath -m "$OUTDIR")"
ABS_RECEPTOR="$(realpath "$RECEPTOR")"
ABS_LIGAND="$(realpath "$LIGAND")"

mkdir -p "$SPLIT_DIR" "$KERNEL_DIR" "$ABS_OUTDIR"

# ── Step 1: vina_split ────────────────────────────────────────────────────────
header "Step 1: Splitting ligands with vina_split"

EXISTING=$(find "$SPLIT_DIR" -maxdepth 1 -name "*.pdbqt" 2>/dev/null | wc -l)

if [[ "$EXISTING" -gt 0 && "$OVERRIDE" == false ]]; then
  success "Found $EXISTING existing split files — skipping (pass --override to redo)"
else
  if [[ "$OVERRIDE" == true && "$EXISTING" -gt 0 ]]; then
    info "Override: removing $EXISTING existing split files"
    rm -f "${SPLIT_DIR}"/*.pdbqt
  fi

  info "Running vina_split on $(basename "$ABS_LIGAND")..."

  # Mount the input file read-only and the split dir as the working directory.
  # vina_split writes <prefix>_ligand_N.pdbqt relative to --input, so we set
  # --input to a path inside /split and work there — output stays in /split.
  docker run --rm \
    -v "${ABS_LIGAND}:/split/input.pdbqt:ro" \
    -v "${SPLIT_DIR}:/split" \
    --workdir /split \
    --entrypoint vina_split \
    "$IMAGE" \
    --input /split/input.pdbqt \
    --ligand ligand

  # Remove the symlinked/copied input from the split dir if present
  rm -f "${SPLIT_DIR}/input.pdbqt"

  EXISTING=$(find "$SPLIT_DIR" -maxdepth 1 -name "*.pdbqt" 2>/dev/null | wc -l)
  success "vina_split produced $EXISTING individual PDBQT files"
fi

LIGAND_COUNT=$(find "$SPLIT_DIR" -maxdepth 1 -name "*.pdbqt" | wc -l)
[[ "$LIGAND_COUNT" -eq 0 ]] &&
  error "No .pdbqt files found after vina_split — check that your input file has valid MODEL records"

# ── Step 2: OpenCL kernel cache ───────────────────────────────────────────────
header "Step 2: Preparing OpenCL kernel cache"

if [[ -d "$KERNEL_DIR/OpenCL" ]]; then
  BIN_COUNT=$(find "$KERNEL_DIR" -name "*.bin" 2>/dev/null | wc -l)
  if [[ "$BIN_COUNT" -gt 0 ]]; then
    success "Reusing $BIN_COUNT cached kernel .bin file(s) from previous run"
  else
    info "Kernel sources present — .bin files will be JIT-compiled on first run (~60s)"
  fi
else
  info "Seeding kernel cache from image..."
  docker run --rm \
    -v "${KERNEL_DIR}:/kc" \
    --entrypoint bash \
    "$IMAGE" \
    -c "cp -r /usr/local/bin/OpenCL /kc/"
  success "Kernel sources ready in ${KERNEL_DIR}"
fi

# ── Step 3: GPU docking ───────────────────────────────────────────────────────
header "Step 3: GPU Docking"
info "Receptor    : $ABS_RECEPTOR"
info "Ligands     : $SPLIT_DIR ($LIGAND_COUNT files)"
info "Output      : $ABS_OUTDIR"
info "Grid center : ($CENTER_X, $CENTER_Y, $CENTER_Z)"
info "Grid size   : ${SIZE_X} × ${SIZE_Y} × ${SIZE_Z} Å"
info "Threads     : $THREAD_SIZE  |  Depth: $EXHAUSTIVENESS  |  Modes: $NUM_MODES"

# Build the script that runs inside the container.
# The single-quoted heredoc keeps container-side variables unexpanded ($NVIDIA_OCL etc).
# Host-side values (CENTER_X, THREAD_SIZE …) are substituted by bash now via the
# double-quoted section appended after.
INNER_SCRIPT=''
read -r -d '' INNER_SCRIPT <<'INNEREOF' || true
set -euo pipefail

echo "══ Running Internal Diagnostics ══"

# 1. Find the actual library path dynamically
# We search common injection points for the NVIDIA OpenCL lib
TARGET_LIB=$(find /usr/lib /usr/local/lib /lib -name "libnvidia-opencl.so*" 2>/dev/null | head -n 1)

if [[ -z "$TARGET_LIB" ]]; then
    echo "[ERROR] libnvidia-opencl.so NOT FOUND in the container."
    echo "This usually means the NVIDIA Container Toolkit is not mounting the OpenCL drivers."
    echo "Check if 'nvidia-container-toolkit' is installed on the host."
    exit 1
fi

echo "[INFO] Found NVIDIA OpenCL library at: $TARGET_LIB"

# 2. Create the ICD registration using the ABSOLUTE path
mkdir -p /etc/OpenCL/vendors
echo "$TARGET_LIB" > /etc/OpenCL/vendors/nvidia.icd

# 3. Set environment variables
export OCL_ICD_VENDORS=/etc/OpenCL/vendors
# Ensure the directory containing the library is in the search path
export LD_LIBRARY_PATH="$(dirname "$TARGET_LIB"):${LD_LIBRARY_PATH:-}"

echo "[INFO] Checking OpenCL via clinfo..."
if ! clinfo | grep -i "NVIDIA" > /dev/null; then
    echo "[ERROR] Still no NVIDIA platform found."
    echo "Showing all detected platforms for debugging:"
    clinfo || echo "clinfo failed entirely."
    exit 1
fi
echo "[SUCCESS] OpenCL Platform detected!"
clinfo | grep -E "Platform Name|Device Name" | head -n 2

ulimit -s unlimited
export CUDA_CACHE_MAXSIZE=2147483648 # Give JIT cache 2GB of room

echo "[INFO] Starting docking..."
INNEREOF

# Append the Vina invocation — host vars expand here
INNER_SCRIPT+="
AutoDock-Vina-GPU-2-1 \\
    --receptor /receptor.pdbqt \\
    --ligand_directory /ligands \\
    --output_directory /out \\
    --thread ${THREAD_SIZE} \\
    --search_depth ${EXHAUSTIVENESS} \\
    --center_x ${CENTER_X} \\
    --center_y ${CENTER_Y} \\
    --center_z ${CENTER_Z} \\
    --size_x ${SIZE_X} \\
    --size_y ${SIZE_Y} \\
    --size_z ${SIZE_Z} \\
    --num_modes ${NUM_MODES} \\
    --energy_range ${ENERGY_RANGE} \\
    --rilc_bfgs 0 \\
    --opencl_binary_path /kernels

echo '[INFO] Docking complete.'
"

DOCKER_CMD=(
  docker run --rm
  --gpus all
  --env NVIDIA_DRIVER_CAPABILITIES=all # Must be 'all' for OpenCL
  --env NVIDIA_VISIBLE_DEVICES=all
  --shm-size=2g
  -v "${ABS_RECEPTOR}:/receptor.pdbqt:ro"
  -v "${SPLIT_DIR}:/ligands:ro"
  -v "${ABS_OUTDIR}:/out"
  -v "${KERNEL_DIR}:/kernels"
  --entrypoint bash
  "$IMAGE"
  -c "${INNER_SCRIPT}"
)

if [[ "$DRY_RUN" == true ]]; then
  warn "DRY RUN — docker command that would execute:"
  echo ""
  printf '  %s \\\n' "${DOCKER_CMD[@]}"
  echo ""
  exit 0
fi

START=$(date +%s)
"${DOCKER_CMD[@]}"
ELAPSED=$(($(date +%s) - START))

# ── Step 4: Summary ───────────────────────────────────────────────────────────
header "Step 4: Results"

DOCKED=$(find "$ABS_OUTDIR" -name "*.pdbqt" 2>/dev/null | wc -l)
success "Finished in ${ELAPSED}s — $DOCKED output file(s) in $ABS_OUTDIR"

if [[ "$DOCKED" -eq 0 ]]; then
  warn "No output PDBQT files found — check the docking log above for errors"
elif [[ "$DOCKED" -lt "$LIGAND_COUNT" ]]; then
  warn "$DOCKED / $LIGAND_COUNT ligands produced output"
else
  success "All $LIGAND_COUNT ligands docked successfully"
fi

if [[ "$DOCKED" -gt 0 ]]; then
  echo ""
  info "Top 10 hits by best binding affinity:"
  printf "  %-52s  %s\n" "Ligand" "Affinity"
  printf "  %-52s  %s\n" "──────" "────────"
  grep -rl "REMARK VINA RESULT" "$ABS_OUTDIR" |
    xargs grep -h "REMARK VINA RESULT" |
    awk -v dir="$ABS_OUTDIR" '{print $4, FILENAME}' |
    sort -k1 -n |
    head -10 |
    while read -r score file; do
      printf "  %-52s  %s kcal/mol\n" "$(basename "$file" .pdbqt)" "$score"
    done 2>/dev/null || true
fi
