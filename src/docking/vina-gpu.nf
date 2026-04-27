process DOCKING_GPU {
    container 'vina-gpu:latest'
    containerOptions '--gpus all --env NVIDIA_DRIVER_CAPABILITIES=compute,utility --shm-size=2g'
    publishDir "${params.outdir}", mode: 'copy'

    input:
    path ligand_dir
    path receptor
    val config

    output:
    path "results/*.pdbqt", emit: docked_files

    script:
    """
    set -euo pipefail
    ulimit -s unlimited
    mkdir -p results

    # ── OpenCL ICD: point to the NVIDIA runtime library ──────────────────────
    NVIDIA_OCL=\$(readlink -f \$(ldconfig -p | grep libnvidia-opencl | awk '{print \$NF}' | head -1))
    if [ -z "\$NVIDIA_OCL" ] || [ ! -f "\$NVIDIA_OCL" ]; then
        echo "FATAL: libnvidia-opencl.so not found. Is --gpus all set?"
        exit 1
    fi
    mkdir -p /etc/OpenCL/vendors
    echo "\$NVIDIA_OCL" > /etc/OpenCL/vendors/nvidia.icd
    export OCL_ICD_VENDORS=/etc/OpenCL/vendors
    export CUDA_VISIBLE_DEVICES=0

    # ── Kernel cache ─────────────────────────────────────────────────────────
    # Vina needs .cl sources present at --opencl_binary_path to JIT-compile.
    # It writes .bin files there after first compilation; subsequent runs reuse them.
    # We use the Nextflow work dir so each resumed run reuses compiled kernels.
    KERNEL_CACHE="\$(pwd)/kernel_cache"
    if [ ! -d "\$KERNEL_CACHE/OpenCL" ]; then
        mkdir -p "\$KERNEL_CACHE"
        cp -r /usr/local/bin/OpenCL "\$KERNEL_CACHE/"
    fi

    BIN_COUNT=\$(find "\$KERNEL_CACHE" -name "*.bin" 2>/dev/null | wc -l)
    echo "Kernel .bin files in cache: \$BIN_COUNT (0 = will JIT compile, ~60s)"

    # ── Docking ──────────────────────────────────────────────────────────────
    AutoDock-Vina-GPU-2-1 \\
        --receptor ${receptor} \\
        --ligand_directory ${ligand_dir} \\
        --output_directory results/ \\
        --thread ${config.thread_size} \\
        --search_depth ${config.exhaustiveness} \\
        --center_x ${config.center_x} \\
        --center_y ${config.center_y} \\
        --center_z ${config.center_z} \\
        --size_x ${config.size_x} \\
        --size_y ${config.size_y} \\
        --size_z ${config.size_z} \\
        --rilc_bfgs 0 \\
        --opencl_binary_path "\$KERNEL_CACHE"
    """
}