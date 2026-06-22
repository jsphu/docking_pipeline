# Use NVIDIA GROMACS as base for GPU acceleration
FROM nvcr.io/hpc/gromacs:2023.2

LABEL description="Master Docking, Filtering, and MD Pipeline Container with Nextflow and FastAPI monitoring."

# Force root user for setup
USER root

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Set environment variables for Micromamba and Python
ENV MAMBA_ROOT_PREFIX=/root/micromamba
ENV CONDA_PREFIX="/root/micromamba/envs/md_env"
ENV PATH="/root/micromamba/envs/md_env/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# GPU-related GROMACS/Vina options
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics
ENV GMX_ENABLE_DIRECT_GPU_COMM=1
ENV GMX_GPU_PME_PP_COMMS=1
ENV GMX_GPU_DD_COMMS=1
ENV GMX_FORCE_UPDATE_DEFAULT_GPU=1

# Install system dependencies (including openjdk for Nextflow, git/build-essential for Vina-GPU, openbabel for parsing)
RUN apt-get update && apt-get install -y --no-install-recommends \
  wget \
  curl \
  bzip2 \
  ca-certificates \
  git \
  build-essential \
  libboost-all-dev \
  opencl-headers \
  ocl-icd-opencl-dev \
  clinfo \
  ocl-icd-libopencl1 \
  libxml2 \
  openbabel \
  libgomp1 \
  openjdk-17-jre-headless \
  && rm -rf /var/lib/apt/lists/*

# Install Micromamba
RUN mkdir -p /tmp/mamba && cd /tmp/mamba \
  && wget -qO- https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj bin/micromamba \
  && mv bin/micromamba /usr/local/bin/ \
  && cd / && rm -rf /tmp/mamba

# Create the conda environment with all dependencies for filtering, rdkit, and MD prep
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
  tomli \
  requests \
  fastapi \
  uvicorn \
  && micromamba clean -afy

# Install acpype and parmed via pip
RUN micromamba run -p /root/micromamba/envs/md_env pip install --no-cache-dir acpype parmed

# Link the most optimized GROMACS binary
RUN if [ -d "/usr/local/gromacs/avx2_256/bin" ]; then \
  ln -sf /usr/local/gromacs/avx2_256/bin/gmx /usr/local/bin/gmx; \
  elif [ -d "/usr/local/gromacs/avx_512/bin" ]; then \
  ln -sf /usr/local/gromacs/avx_512/bin/gmx /usr/local/bin/gmx; \
  else \
  GMX_PATH=$(find /usr/local/gromacs -name gmx -type f -executable | head -n 1) && \
  ln -sf $GMX_PATH /usr/local/bin/gmx; \
  fi

# --- Download and Install AutoDock Vina ---
RUN wget -q https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/v1.2.5/vina_1.2.5_linux_x86_64 -O /usr/local/bin/vina && \
    chmod +x /usr/local/bin/vina

# --- Clone and Compile QuickVina-GPU ---
WORKDIR /opt
RUN git clone https://github.com/DeltaGroupNJUPT/Vina-GPU-2.1.git
WORKDIR /opt/Vina-GPU-2.1/QuickVina-W-GPU-2.1
RUN sed -i 's|^BOOST_LIB_PATH=.*|BOOST_LIB_PATH=/usr/include|' Makefile && \
  sed -i 's|^VINA_GPU_INC_PATH=.*|VINA_GPU_INC_PATH=-I./lib -I./OpenCL/inc|' Makefile && \
  sed -i 's|^LIB_PATH=.*|LIB_PATH=-L/usr/lib/x86_x64-linux-gnu -L/usr/local/cuda/lib64|' Makefile && \
  sed -i 's|$(BOOST_LIB_PATH)/libs/thread/src/pthread/thread.cpp||' Makefile && \
  sed -i 's|$(BOOST_LIB_PATH)/libs/thread/src/pthread/once.cpp||' Makefile && \
  sed -i 's|LIB1=.*|LIB1=-lboost_program_options -lboost_system -lboost_filesystem -lboost_thread -lOpenCL -no-pie|' Makefile && \
  sed -i 's|OPENCL_VERSION=.*|OPENCL_VERSION=-DOPENCL_3_0|' Makefile && \
  sed -i 's/if (thread < 1000)/if (thread < 16)/g' main/main.cpp && \
  sed -i 's|MACRO=.*|MACRO=$(OPENCL_VERSION) $(GPU_PLATFORM) $(DOCKING_BOX_SIZE) -DBOOST_TIMER_ENABLE_DEPRECATED -DCL_TARGET_OPENCL_VERSION=300 -fPIC|' Makefile
RUN make source -j "$(nproc)"
RUN cp QuickVina-W-GPU-2-1 /usr/local/bin/QuickVina-W-GPU-2-1.bin && \
    cp -r OpenCL /usr/local/bin/
RUN mkdir -p /etc/OpenCL/vendors && \
    echo "libnvidia-opencl.so.1" > /etc/OpenCL/vendors/nvidia.icd

# Create wrapper script for QuickVina-GPU OpenCL directory resolution
RUN echo '#!/bin/bash\n\
if [ ! -d "./OpenCL" ]; then\n\
  ln -s /usr/local/bin/OpenCL ./OpenCL\n\
fi\n\
exec QuickVina-W-GPU-2-1.bin "$@"' > /usr/local/bin/QuickVina-W-GPU-2-1 && \
    chmod +x /usr/local/bin/QuickVina-W-GPU-2-1

# --- Install Nextflow ---
WORKDIR /usr/local/bin
RUN curl -s https://get.nextflow.io | bash && \
    chmod +x nextflow

# Set up application workspace
WORKDIR /app

# Copy the entire workspace project directory
COPY . /app

# Ensure entrypoint and scripts are executable
RUN chmod +x /app/scripts/master_entrypoint.sh /app/scripts/select_top_ligands.py

# Expose web server monitoring port
EXPOSE 8080

# Run entrypoint
ENTRYPOINT ["/bin/bash", "/app/scripts/master_entrypoint.sh"]
