FROM nvidia/cuda:12.2.0-devel-ubuntu22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
  git build-essential libboost-all-dev \
  opencl-headers ocl-icd-opencl-dev \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN git clone https://github.com/DeltaGroupNJUPT/Vina-GPU-2.1.git
WORKDIR /build/Vina-GPU-2.1/AutoDock-Vina-GPU-2.1

RUN sed -i 's|^BOOST_LIB_PATH=.*|BOOST_LIB_PATH=/usr/include|' Makefile && \
  sed -i 's|^VINA_GPU_INC_PATH=.*|VINA_GPU_INC_PATH=-I./lib -I./OpenCL/inc|' Makefile && \
  sed -i 's|^LIB_PATH=.*|LIB_PATH=-L/usr/lib/x86_64-linux-gnu -L/usr/local/cuda/lib64|' Makefile && \
  sed -i 's|$(BOOST_LIB_PATH)/libs/thread/src/pthread/thread.cpp||' Makefile && \
  sed -i 's|$(BOOST_LIB_PATH)/libs/thread/src/pthread/once.cpp||' Makefile && \
  sed -i 's|LIB1=.*|LIB1=-lboost_program_options -lboost_system -lboost_filesystem -lboost_thread -lOpenCL -no-pie|' Makefile && \
  sed -i 's|GPU_PLATFORM=-DAMD_PLATFORM|GPU_PLATFORM=-DNVIDIA_PLATFORM|' Makefile && \
  # sed -i 's|-DLARGE_BOX|-DSMALL_BOX|' Makefile && \
  sed -i 's|MACRO=.*|MACRO=$(OPENCL_VERSION) $(GPU_PLATFORM) $(DOCKING_BOX_SIZE) -DBOOST_TIMER_ENABLE_DEPRECATED -DCL_TARGET_OPENCL_VERSION=200 -fPIC|' Makefile

RUN make source -j "$(nproc)"

WORKDIR /build
RUN git clone https://github.com/ccsb-scripps/AutoDock-Vina.git vina_official
WORKDIR /build/vina_official/build/linux/release
RUN sed -i 's|^BOOST_INCLUDE =.*|BOOST_INCLUDE = /usr/include|' Makefile && \
  sed -i 's|^BOOST_LIB =.*|BOOST_LIB = /usr/lib/x86_64-linux-gnu|' Makefile && \
  make vina_split -j "$(nproc)"

FROM nvidia/cuda:12.2.0-base-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
  libboost-program-options1.74.0 \
  libboost-system1.74.0 \
  libboost-filesystem1.74.0 \
  libboost-thread1.74.0 \
  ocl-icd-libopencl1 \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/Vina-GPU-2.1/AutoDock-Vina-GPU-2.1/AutoDock-Vina-GPU-2-1 /usr/local/bin/
COPY --from=builder /build/Vina-GPU-2.1/AutoDock-Vina-GPU-2.1/OpenCL /usr/local/bin/OpenCL
COPY --from=builder /build/vina_official/build/linux/release/vina_split /usr/local/bin/

RUN mkdir -p /etc/OpenCL/vendors && \
  echo "libnvidia-opencl.so.1" > /etc/OpenCL/vendors/nvidia.icd \
  cp -r /build/Vina-GPU-2.1/AutoDock-Vina-GPU-2.1/OpenCL .

ENTRYPOINT ["AutoDock-Vina-GPU-2-1"]
