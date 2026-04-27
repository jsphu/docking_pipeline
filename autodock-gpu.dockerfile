FROM nvidia/cuda:12.2.0-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Added csh to the dependencies
RUN apt-get update && apt-get install -y \
    git build-essential autoconf automake csh \
    && rm -rf /var/lib/apt/lists/*

# --- Build AutoGrid4 ---
WORKDIR /opt
RUN git clone https://github.com/ccsb-scripps/autogrid.git
WORKDIR /opt/autogrid

# Generate the Makefile and build
RUN autoreconf -fi && \
    ./configure && \
    make -j "$(nproc)" && \
    cp autogrid4 /usr/local/bin/

# --- Build AutoDock-GPU ---
WORKDIR /opt
RUN git clone https://github.com/ccsb-scripps/autodock-gpu.git
WORKDIR /opt/autodock-gpu

ENV CUDA_PATH=/usr/local/cuda
ENV GPU_INCLUDE_PATH=/usr/local/cuda/include
ENV GPU_LIBRARY_PATH=/usr/local/cuda/lib64

RUN make DEVICE=GPU \
    GPU_INCLUDE_PATH=$GPU_INCLUDE_PATH \
    GPU_LIBRARY_PATH=$GPU_LIBRARY_PATH \
    OVERRIDE_ARCH="75" \
    -j "$(nproc)"

# Using the 128wi binary confirmed by your previous logs
RUN cp bin/autodock_gpu_128wi /usr/local/bin/autodock-gpu

WORKDIR /data