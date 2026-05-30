# Use NVIDIA GROMACS as base for GPU acceleration
FROM nvcr.io/hpc/gromacs:2023.2

LABEL description="Full MD Workflow with GROMACS, ACPYPE, and RDKit for Salad Cloud"

# Force root user for setup
USER root

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Set environment variables for Micromamba and Python
# These must be set before running micromamba commands
ENV MAMBA_ROOT_PREFIX=/root/micromamba
ENV PATH="/root/micromamba/envs/md_env/bin:$PATH"
ENV CONDA_PREFIX="/root/micromamba/envs/md_env"
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    bzip2 \
    ca-certificates \
    git \
    libxml2 \
    openbabel \
    && rm -rf /var/lib/apt/lists/*

# Install Micromamba
RUN mkdir -p /tmp/mamba && cd /tmp/mamba \
    && wget -qO- https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj bin/micromamba \
    && mv bin/micromamba /usr/local/bin/ \
    && cd / && rm -rf /tmp/mamba

# Create the conda environment
# We install the core scientific tools. 
# acpype is installed via pip later to match the project's installation pattern.
RUN micromamba create -y -p /root/micromamba/envs/md_env -c conda-forge \
    python=3.10 \
    gromacs=2023.2 \
    openbabel \
    ambertools \
    rdkit \
    biopython \
    pandas \
    numpy \
    matplotlib \
    scipy \
    requests \
    && micromamba clean -afy

# Install acpype and parmed via pip as per project requirements
RUN micromamba run -p /root/micromamba/envs/md_env pip install --no-cache-dir acpype parmed

# Set up application directory
WORKDIR /app

# Copy the workflow scripts and source code
COPY scripts/md_workflow/ /app/

# Make sure all scripts and entrypoint are executable
RUN chmod +x /app/md_workflow.py /app/post_md.py /app/entrypoint.sh

# Default Environment Variables for SaladCloud / Runtime
ENV DATADIR=/app/data
ENV CONFIG_FILE=/app/data/6NJS.json
ENV OUTDIR=/results
ENV WORKDIR=/work
ENV USE_GPU=true

# Create necessary directories for volumes and execution
RUN mkdir -p /results /work /app/data

# Entrypoint
ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
