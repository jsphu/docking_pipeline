#!/bin/bash
set -euo pipefail

OPENCL_BIN_DIR="${OPENCL_BIN_DIR:-/tmp/vina_kernels}"
WARMUP_DIR="/opt/vina-warmup"
WARMUP_OUT="${OPENCL_BIN_DIR}/warmup_out"

mkdir -p "$OPENCL_BIN_DIR" "$WARMUP_OUT"

# ── 1. Find the nvidia opencl .so ────────────────────────────────────────────
NVIDIA_OCL=$(ldconfig -p | grep libnvidia-opencl | awk '{print $NF}' | head -1)
if [ -z "$NVIDIA_OCL" ]; then
    NVIDIA_OCL=$(find /lib /usr/lib /usr/local/lib -name "libnvidia-opencl.so*" \
        ! -type l 2>/dev/null | head -1)   # ! -type l = skip dangling symlinks
fi
if [ -z "$NVIDIA_OCL" ]; then
    echo "ERROR: libnvidia-opencl.so not found."
    exit 1
fi

# Resolve symlink to real path
NVIDIA_OCL=$(readlink -f "$NVIDIA_OCL")
echo "Resolved OpenCL lib: $NVIDIA_OCL"

if [ ! -f "$NVIDIA_OCL" ]; then
    echo "ERROR: $NVIDIA_OCL is a broken symlink or does not exist."
    echo "All nvidia opencl entries in ldconfig:"
    ldconfig -p | grep nvidia-opencl || echo "(none)"
    echo "Files in /lib/x86_64-linux-gnu/ matching opencl:"
    find /lib /usr/lib -name "*opencl*" -o -name "*OpenCL*" 2>/dev/null
    exit 1
fi

# ── 2. Write ICD with resolved real path ─────────────────────────────────────
mkdir -p /etc/OpenCL/vendors
echo "$NVIDIA_OCL" > /etc/OpenCL/vendors/nvidia.icd
export OCL_ICD_VENDORS=/etc/OpenCL/vendors
export OPENCL_VENDOR_PATH=/etc/OpenCL/vendors

echo "ICD contents: $(cat /etc/OpenCL/vendors/nvidia.icd)"

# ── 3. Debug ICD loader ───────────────────────────────────────────────────────
echo ""
echo "=== OCL_ICD_DEBUG output ==="
OCL_ICD_DEBUG=15 clinfo 2>&1 | head -80

echo ""
echo "=== clinfo platform list ==="
clinfo -l || true

PLATFORM_COUNT=$(clinfo -l 2>/dev/null | grep -c "Platform" || true)
if [ "$PLATFORM_COUNT" -eq 0 ]; then
    echo ""
    echo "ERROR: clinfo sees no platforms. ICD loader cannot open the .so."
    echo "Trying direct LD_PRELOAD as fallback..."

    # Some nvidia-container-toolkit versions need explicit preload
    export LD_PRELOAD="$NVIDIA_OCL"
    clinfo -l || true
    PLATFORM_COUNT=$(clinfo -l 2>/dev/null | grep -c "Platform" || true)

    if [ "$PLATFORM_COUNT" -eq 0 ]; then
        echo "FATAL: OpenCL platform not found even with LD_PRELOAD."
        echo "Verify nvidia-container-toolkit is installed on the HOST:"
        echo "  dpkg -l | grep nvidia-container-toolkit"
        exit 1
    fi
    echo "LD_PRELOAD workaround worked — adding to environment."
fi

# ── 4. Warmup docking to compile kernels ─────────────────────────────────────
echo ""
echo "Compiling kernels into $OPENCL_BIN_DIR ..."

set +e
AutoDock-Vina-GPU-2-1 \
    --receptor         "$WARMUP_DIR/receptor.pdbqt" \
    --ligand_directory "$WARMUP_DIR/ligands" \
    --output_directory "$WARMUP_OUT" \
    --opencl_binary_path "$OPENCL_BIN_DIR" \
    --thread 1000 \
    --search_depth 1 \
    --center_x 1.0 --center_y 1.0 --center_z 1.0 \
    --size_x 5.0   --size_y 5.0   --size_z 5.0
EXIT_CODE=$?
set -e

echo "Vina exit code: $EXIT_CODE"

BIN_COUNT=$(find "$OPENCL_BIN_DIR" -name "*.bin" 2>/dev/null | wc -l)
if [ "$BIN_COUNT" -gt 0 ]; then
    echo "SUCCESS: $BIN_COUNT .bin file(s) compiled:"
    ls -lh "$OPENCL_BIN_DIR"/*.bin
else
    echo "FAILED: No .bin files produced. Vina output above has the reason."
    exit 1
fi