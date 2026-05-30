# GROMACS image with CUDA support
FROM nvcr.io/hpc/gromacs:2023.2

LABEL description="Full MD Workflow with GROMACS, ACPYPE, and RDKit"

# FORCE ROOT USER TEMPORARILY TO CONSTRUCT THE PIPELINE
USER root

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
  wget \
  ca-certificates \
  git \
  libxml2 \
  openbabel \
  && rm -rf /var/lib/apt/lists/*

# Install Micromamba for fast dependency management
RUN wget -qO- https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj bin/micromamba \
  && mv bin/micromamba /usr/local/bin/ \
  && rm -rf bin

# Create the environment with all scientific tools
RUN micromamba create -n md_env -c conda-forge -y \
  python=3.10 \
  gromacs \
  acpype \
  ambertools \
  rdkit \
  biopython \
  pandas \
  matplotlib \
  scipy \
  requests \
  && micromamba clean -afy

# Set exact environment paths to hard-bind the python execution layers
ENV MAMBA_ROOT_PREFIX=/root/micromamba
ENV PATH="/root/micromamba/envs/md_env/bin:$PATH"
ENV CONDA_PREFIX="/root/micromamba/envs/md_env"
ENV PYTHONUNBUFFERED=1

# Set up application directory
WORKDIR /app

# Copy the workflow scripts and source code
COPY scripts/md_workflow/ /app/

# Ensure scripts are executable (Fixed: done right before defining entrypoint)
RUN chmod +x /app/md_workflow.py /app/post_md.py /app/entrypoint.sh

# Environment variables for SaladCloud/Runtime
ENV DATADIR=/app/data
ENV CONFIG_FILE=/app/data/6NJS.json
ENV OUTDIR=/results
ENV WORKDIR=/work
ENV USE_GPU=true

# Create necessary directories
RUN mkdir -p /results /work

# Entrypoint
ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
