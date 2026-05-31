# Use NVIDIA GROMACS as base for GPU acceleration
FROM nvcr.io/hpc/gromacs:2023.2

LABEL description="Full MD Workflow with GROMACS, ACPYPE, and RDKit optimized for RTX 30+, 40+, 50+"

# Force root user for setup
USER root

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Set environment variables for Micromamba and Python
ENV MAMBA_ROOT_PREFIX=/root/micromamba
ENV CONDA_PREFIX="/root/micromamba/envs/md_env"
ENV PATH="/root/micromamba/envs/md_env/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# GPU related environment variables for RTX 30/40/50
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV GMX_ENABLE_DIRECT_GPU_COMM=1
ENV GMX_GPU_PME_PP_COMMS=1
ENV GMX_GPU_DD_COMMS=1
ENV GMX_FORCE_UPDATE_DEFAULT_GPU=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
  wget \
  bzip2 \
  ca-certificates \
  git \
  libxml2 \
  openbabel \
  libgomp1 \
  && rm -rf /var/lib/apt/lists/*

# Install Micromamba
RUN mkdir -p /tmp/mamba && cd /tmp/mamba \
  && wget -qO- https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj bin/micromamba \
  && mv bin/micromamba /usr/local/bin/ \
  && cd / && rm -rf /tmp/mamba

# Create the conda environment
# Note: gromacs is NOT installed here to avoid shadowing the NVIDIA-optimized version
RUN micromamba create -y -p /root/micromamba/envs/md_env -c conda-forge \
  python=3.10 \
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

# Install acpype and parmed via pip
RUN micromamba run -p /root/micromamba/envs/md_env pip install --no-cache-dir acpype parmed

# Link the most optimized GROMACS binary for modern CPUs (AVX2 is standard for RTX 30+ era CPUs)
RUN if [ -d "/usr/local/gromacs/avx2_256/bin" ]; then \
      ln -sf /usr/local/gromacs/avx2_256/bin/gmx /usr/local/bin/gmx; \
    elif [ -d "/usr/local/gromacs/avx_512/bin" ]; then \
      ln -sf /usr/local/gromacs/avx_512/bin/gmx /usr/local/bin/gmx; \
    else \
      GMX_PATH=$(find /usr/local/gromacs -name gmx -type f -executable | head -n 1) && \
      ln -sf $GMX_PATH /usr/local/bin/gmx; \
    fi

# Set up application directory
WORKDIR /app

# Copy the workflow scripts and source code
COPY scripts/md_workflow/ /app/

# Make sure all scripts and entrypoint are executable
RUN chmod +x /app/md_workflow.py /app/post_md.py /app/entrypoint.sh /app/run_smoke_test.sh

# Default Environment Variables for Runtime
ENV DATADIR=/app/data
ENV CONFIG_FILE=/app/data/6NJS.json
ENV OUTDIR=/results
ENV WORKDIR=/work
ENV USE_GPU=true

# Create necessary directories
RUN mkdir -p /results /work /app/data

# Entrypoint
ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
