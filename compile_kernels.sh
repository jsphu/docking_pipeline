#!/bin/bash
# compile_kernels.sh
# Forces Vina-GPU to recompile OpenCL kernels for the runtime GPU architecture.
# Must run INSIDE the container WITH GPU access (--gpus all).
# Output .bin files go to OPENCL_BIN_DIR (mounted or local).

set -e

OPENCL_BIN_DIR="${OPENCL_BIN_DIR:-/tmp/vina_kernels}"
KERNEL_SOURCE_DIR="${KERNEL_SOURCE_DIR:-/usr/local/share/vina-gpu/OpenCL}"

mkdir -p "$OPENCL_BIN_DIR"

# Discover OpenCL library injected by NVIDIA runtime
NVIDIA_OCL=$(ldconfig -p | grep libnvidia-opencl | awk '{print $NF}' | head -1)
if [ -z "$NVIDIA_OCL" ]; then
    NVIDIA_OCL=$(find /usr/lib /usr/local/lib -name "libnvidia-opencl.so*" 2>/dev/null | head -1)
fi

if [ -z "$NVIDIA_OCL" ]; then
    echo "ERROR: libnvidia-opencl.so not found. GPU not exposed to container."
    exit 1
fi

echo "Writing ICD: $NVIDIA_OCL"
mkdir -p /etc/OpenCL/vendors
echo "$NVIDIA_OCL" > /etc/OpenCL/vendors/nvidia.icd
export OCL_ICD_VENDORS=/etc/OpenCL/vendors

echo "GPU info:"
clinfo -l

echo ""
echo "Compiling kernels into $OPENCL_BIN_DIR ..."

# Run a minimal dry-dock to trigger kernel compilation and cache the .bin
# We use /dev/null-equivalent args — the compilation happens before docking starts
# The binary exits with Err after compile; that's expected and fine
AutoDock-Vina-GPU-2-1 \
    --opencl_binary_path "$OPENCL_BIN_DIR" \
    --thread 8 2>&1 | grep -E "Compiling|compiled|kernel|done|Err" || true

# Check if .bin files were produced
BIN_COUNT=$(find "$OPENCL_BIN_DIR" -name "*.bin" | wc -l)
if [ "$BIN_COUNT" -gt 0 ]; then
    echo "SUCCESS: $BIN_COUNT kernel .bin file(s) compiled to $OPENCL_BIN_DIR"
    ls -lh "$OPENCL_BIN_DIR"/*.bin
else
    echo "WARNING: No .bin files found. JIT compilation will occur per-run."
fi