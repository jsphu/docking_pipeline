#!/bin/bash
set -e

# Cleanup function to kill background server
cleanup() {
  echo "--- Stopping Web Server (PID: $SERVER_PID) ---"
  kill $SERVER_PID || true
}
trap cleanup EXIT

# FORCE TERMINAL TO USE THE MICROMAMBA ENVIRONMENT PATHS EXPANSION
export MAMBA_ROOT_PREFIX=/root/micromamba
export PATH="/root/micromamba/envs/md_env/bin:/usr/local/bin:$PATH"
export CONDA_PREFIX="/root/micromamba/envs/md_env"

# GPU related GROMACS tuning (Disabled for stability, enable ONLY if system supports P2P/NVLink)
export GMX_ENABLE_DIRECT_GPU_COMM=0
export GMX_GPU_PME_PP_COMMS=0
export GMX_GPU_DD_COMMS=0

if [ "$PREFLIGHT_CHECK" = "false" ]; then
  echo "Skipping GPU test (PREFLIGHT_CHECK=false)"
  echo "Only skip if you sure about the environment!"
else
  if [ "$USE_GPU" = "true" ]; then
    echo "--- GPU Pre-flight Check ---"
    # Verify NVIDIA visibility
    if command -v nvidia-smi &>/dev/null; then
      nvidia-smi -L
    else
      echo "Warning: nvidia-smi not found. GPU may not be accessible."
    fi

    # Run GROMACS test simulation
    python3 /app/test_gpu.py || exit 1
  else
    echo "Skipping GPU test (USE_GPU=false)"
  fi
fi

echo "--- MD Workflow Container Started ---"
echo "Config: $CONFIG_FILE"
echo "Output: $OUTDIR"
echo "Workdir: $WORKDIR"
echo "GPU: $USE_GPU"

# Ensure directories exist
mkdir -p "$OUTDIR"
mkdir -p "$WORKDIR"

# Start the web server in the background
echo "--- Starting Web Server on port 8080 ---"
python3 /app/server.py >/app/webserver.log 2>&1 &
SERVER_PID=$!

# Construct arguments for md_workflow.py
# --no-docker is used because we ARE already inside docker
CMD_ARGS="--config $CONFIG_FILE --outdir $OUTDIR --workdir $WORKDIR --no-docker"

if [ "$USE_GPU" = "true" ]; then
  CMD_ARGS="$CMD_ARGS --gpu"
else
  CMD_ARGS="$CMD_ARGS --no-gpu"
fi

if [ "$AUTO_CPUS" = "true" ]; then
  # Logic is handled inside the python scripts (min(os.cpu_count(), 16))
  echo "CPU Auto-scaling enabled."
fi

if [ "$UPLOAD_RESULTS" = "true" ]; then
  CMD_ARGS="$CMD_ARGS --upload"
fi

if [ "$RESUME" = "1" ] || [ "$RESUME" = "true" ]; then
  CMD_ARGS="$CMD_ARGS --resume --skip-prep"
  echo "Resume mode enabled."
fi

if [ -n "$NSTEPS" ]; then
  echo "Production MD steps: $NSTEPS"
  CMD_ARGS="$CMD_ARGS --nsteps $NSTEPS"
fi

if [ -n "$EXTRA_ARGS" ]; then
  CMD_ARGS="$CMD_ARGS $EXTRA_ARGS"
  echo "Found extra arguments.: $EXTRA_ARGS"
fi

if [ "$PREFLIGHT_CHECK" = "true" ]; then
  # Run the smoke test to ensure everything is perfect before main workflow
  echo "--- Running Pipeline Smoke Test ---"
  /bin/bash /app/run_smoke_test.sh
else
  echo "Skipping smoke test (PREFLIGHT_CHECK=false)"
  echo "Only skip if you sure about the environment!"
fi

# Main execution
echo "--- Starting Main MD Workflow ---"
python3 /app/md_workflow.py $CMD_ARGS

echo "--- Starting Post-MD Analysis ---"
POST_ARGS="--outdir $OUTDIR --workdir $WORKDIR --config $CONFIG_FILE --no-docker"
if [ "$UPLOAD_RESULTS" = "true" ]; then
  POST_ARGS="$POST_ARGS --upload"
fi
python3 /app/post_md.py $POST_ARGS

echo "--- MD Workflow Completed ---"
echo "Results are available in: $OUTDIR"
