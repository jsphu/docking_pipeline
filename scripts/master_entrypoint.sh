#!/bin/bash
set -e

# Cleanup function to kill background server on exit
cleanup() {
  echo "--- Stopping FastAPI Monitoring Server (PID: $SERVER_PID) ---"
  kill $SERVER_PID || true
}
trap cleanup EXIT

# Expose Mamaba environment variables inside the script
export MAMBA_ROOT_PREFIX=/root/micromamba
export CONDA_PREFIX="/root/micromamba/envs/md_env"
export PATH="/root/micromamba/envs/md_env/bin:/usr/local/bin:$PATH"
export PYTHONUNBUFFERED=1

# GPU-related GROMACS/Vina options
export GMX_ENABLE_DIRECT_GPU_COMM=0
export GMX_GPU_PME_PP_COMMS=0
export GMX_GPU_DD_COMMS=0
export NVIDIA_VISIBLE_DEVICES=all
export NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics

# Define default paths for the monitor server
export OUTDIR="${OUTDIR:-results}"
export WORKDIR="${WORKDIR:-work}"
export CONFIG_FILE="${CONFIG_FILE:-md_workflow/config.json}"
export WEB_PORT="${WEB_PORT:-8080}"

echo "--- Master Entrypoint Started ---"
echo "FastAPI Port: $WEB_PORT"
echo "Output Dir  : $OUTDIR"
echo "Work Dir    : $WORKDIR"
echo "MD Config   : $CONFIG_FILE"

# Ensure workspaces are created
mkdir -p "$OUTDIR"
mkdir -p "$WORKDIR"

# 1. Start the FastAPI Web Server in the background
echo "--- Starting FastAPI Web Server ---"
python3 -m src.md_workflow.server > /app/webserver.log 2>&1 &
SERVER_PID=$!

# Wait a moment to ensure server has started
sleep 2
if kill -0 $SERVER_PID 2>/dev/null; then
  echo "FastAPI Server successfully started with PID: $SERVER_PID"
else
  echo "WARNING: FastAPI Server failed to start. Check /app/webserver.log"
fi

# 2. Build Nextflow args dynamically from environment variables
NEXTFLOW_ARGS=""
if [ -n "$RECEPTOR" ]; then
  NEXTFLOW_ARGS="$NEXTFLOW_ARGS --receptor $RECEPTOR"
fi
if [ -n "$LIGANDS" ]; then
  NEXTFLOW_ARGS="$NEXTFLOW_ARGS --ligands '$LIGANDS'"
fi
if [ "$RUN_MD" = "true" ]; then
  NEXTFLOW_ARGS="$NEXTFLOW_ARGS --run_md true"
fi
if [ -n "$TOTAL_LIGANDS" ]; then
  NEXTFLOW_ARGS="$NEXTFLOW_ARGS --total_ligands $TOTAL_LIGANDS"
fi
if [ "$RUN_FILTERING" = "true" ]; then
  NEXTFLOW_ARGS="$NEXTFLOW_ARGS --run_filtering true"
fi
if [ "$PREFILTER" = "true" ]; then
  NEXTFLOW_ARGS="$NEXTFLOW_ARGS --prefilter true"
fi
if [ "$USE_GPU" = "true" ]; then
  NEXTFLOW_ARGS="$NEXTFLOW_ARGS --use_gpu true"
fi
if [ -n "$MD_STEPS" ]; then
  NEXTFLOW_ARGS="$NEXTFLOW_ARGS --md_steps $MD_STEPS"
fi
if [ -n "$OUTDIR" ]; then
  NEXTFLOW_ARGS="$NEXTFLOW_ARGS --outdir $OUTDIR"
fi
if [ "$SKIP_DOWNLOAD" = "true" ]; then
  NEXTFLOW_ARGS="$NEXTFLOW_ARGS --skip_download true"
fi

# 3. Running Nextflow
echo "--- Starting Nextflow Orchestrated Workflow (local profile) ---"
echo "Running: nextflow run main.nf -profile local $NEXTFLOW_ARGS $@"

# We eval the command to support quotes and spacing in arguments properly
eval "nextflow run main.nf -profile local $NEXTFLOW_ARGS $@"

echo "--- Nextflow Pipeline Completed successfully ---"

# Keep the container alive briefly or wait for the user to terminate if they want to check logs
# Comment out if you want the container to exit immediately upon completion
echo "Pipeline complete. Monitoring server is still active. Press Ctrl+C to terminate container."
wait $SERVER_PID
