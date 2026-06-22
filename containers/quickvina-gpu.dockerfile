FROM nvidia/cuda:12.2.0-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
#
# This is the secret sauce: tell NVIDIA to expose everything to the container
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics

# Added csh to the dependencies
RUN apt-get update && apt-get install -y \
  git build-essential libboost-all-dev rename \
  opencl-headers ocl-icd-opencl-dev clinfo ocl-icd-libopencl1 \
  && rm -rf /var/lib/apt/lists/*

# --- Build AutoGrid4 ---
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
  #sed -i 's|-DLARGE_BOX|-DSMALL_BOX|' Makefile && \
  sed -i 's/if (thread < 1000)/if (thread < 16)/g' main/main.cpp && \
  sed -i 's|MACRO=.*|MACRO=$(OPENCL_VERSION) $(GPU_PLATFORM) $(DOCKING_BOX_SIZE) -DBOOST_TIMER_ENABLE_DEPRECATED -DCL_TARGET_OPENCL_VERSION=300 -fPIC|' Makefile

RUN make out -j "$(nproc)"

RUN cp QuickVina-W-GPU-2-1 /usr/local/bin/QuickVina-W-GPU-2-1.bin
RUN cp -r OpenCL /usr/local/bin/

RUN mkdir -p /etc/OpenCL/vendors && \
    echo "libnvidia-opencl.so.1" > /etc/OpenCL/vendors/nvidia.icd

# Create a wrapper to ensure OpenCL kernels and precompiled binaries are available in the current directory
RUN echo '#!/bin/bash\n\
if [ ! -d "./OpenCL" ]; then\n\
  ln -s /usr/local/bin/OpenCL ./OpenCL\n\
fi\n\
if [ ! -f "./Kernel1_Opt.bin" ]; then\n\
  cp /opt/Vina-GPU-2.1/QuickVina-W-GPU-2.1/*_Opt.bin ./\n\
fi\n\
exec QuickVina-W-GPU-2-1.bin "$@"' > /usr/local/bin/QuickVina-W-GPU-2-1 && \
    chmod +x /usr/local/bin/QuickVina-W-GPU-2-1

WORKDIR /data
CMD ["QuickVina-W-GPU-2-1"]
