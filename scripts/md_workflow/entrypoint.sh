#!/bin/bash
set -e

# FORCE TERMINAL TO USE THE MICROMAMBA ENVIRONMENT PATHS EXPANSION
export MAMBA_ROOT_PREFIX=/root/micromamba
export PATH="/root/micromamba/envs/md_env/bin:/usr/local/bin:$PATH"
export CONDA_PREFIX="/root/micromamba/envs/md_env"

# GPU related GROMACS tuning
export GMX_ENABLE_DIRECT_GPU_COMM=1
export GMX_GPU_PME_PP_COMMS=1
export GMX_GPU_DD_COMMS=1

echo "--- GPU Pre-flight Check ---"
if [ "$USE_GPU" = "true" ]; then
  # Verify NVIDIA visibility
  if command -v nvidia-smi &>/dev/null; then
    nvidia-smi -L
  else
    echo "Warning: nvidia-smi not found. GPU may not be accessible."
  fi

  # Run GROMACS test simulation
  /root/micromamba/envs/md_env/bin/python3 /app/test_gpu.py || exit 1
else
  echo "Skipping GPU test (USE_GPU=false)"
fi

echo "--- MD Workflow Container Started ---"
echo "Config: $CONFIG_FILE"
echo "Output: $OUTDIR"
echo "Workdir: $WORKDIR"
echo "GPU: $USE_GPU"

# Ensure directories exist
mkdir -p "$OUTDIR"
mkdir -p "$WORKDIR"

# Construct arguments for md_workflow.py
CMD_ARGS="--config $CONFIG_FILE --outdir $OUTDIR --workdir $WORKDIR --no-docker"

if [ "$USE_GPU" = "true" ]; then
  CMD_ARGS="$CMD_ARGS --gpu"
else
  CMD_ARGS="$CMD_ARGS --no-gpu"
fi

# Run the smoke test to ensure everything is perfect before main workflow
echo "--- Running Pipeline Smoke Test ---"
/bin/bash /app/run_smoke_test.sh

# Main execution (commented out by default if smoke test is the priority,
# but uncommented here for actual production use as requested)
echo "--- Starting Main MD Workflow ---"
/root/micromamba/envs/md_env/bin/python3 /app/md_workflow.py $CMD_ARGS
/root/micromamba/envs/md_env/bin/python3 /app/post_md.py --outdir $OUTDIR --no-docker

echo "--- MD Workflow Container Completed ---"
echo "Results are available in: $OUTDIR"
