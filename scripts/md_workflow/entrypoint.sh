#!/bin/bash
set -e

# FORCE TERMINAL TO USE THE MICROMAMBA ENVIRONMENT PATHS EXPANSION
export MAMBA_ROOT_PREFIX=/root/micromamba
export PATH="/root/micromamba/envs/md_env/bin:$PATH"
export CONDA_PREFIX="/root/micromamba/envs/md_env"

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

# omitted since config file already includes protein and ligand files.
# if [ -n "$PROTEIN_PATH" ]; then
#   CMD_ARGS="$CMD_ARGS --protein $PROTEIN_PATH"
# else
#   echo "Warning: PROTEIN_PATH not set. Ensure protein is defined in config.json or provided via volume."
# fi
#
# if [ -n "$LIGAND_PATH" ]; then
#   CMD_ARGS="$CMD_ARGS --ligand $LIGAND_PATH"
# else
#   echo "Warning: LIGAND_PATH not set. Ensure ligand is defined in config.json or provided via volume."
# fi

# Run the simulation workflow (Fixed: Explicitly calling our conda-enviroment python)
echo "Running md_workflow.py with args: $CMD_ARGS"
/root/micromamba/envs/md_env/bin/python3 /app/md_workflow.py $CMD_ARGS

# Run the post-analysis
echo "Running post_md.py for analysis..."
/root/micromamba/envs/md_env/bin/python3 /app/post_md.py --outdir $OUTDIR --no-docker

echo "--- MD Workflow Container Completed Successfully ---"
echo "Results are available in: $OUTDIR"
