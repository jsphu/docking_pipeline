# Use NVIDIA GROMACS as base for GPU acceleration
FROM nvcr.io/hpc/gromacs:2023.2

LABEL description="MD Workflow with GROMACS for Salad Cloud"

ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

# Set up application directory
WORKDIR /app

# Copy the workflow scripts and source code
COPY scripts/md_workflow/ /app/

# Make sure all scripts and entrypoint are executable
RUN chmod +x /app/run_native.sh

# Entrypoint
ENTRYPOINT ["/bin/bash", "/app/run_native.sh"]
