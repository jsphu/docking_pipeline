process DOCKING_GPU {
    container 'quickvina-gpu:latest'
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
    #
    # Clean up ligands before running
    find gpu_docking_job -type f -size 0 -delete
    find gpu_docking_job -name "* *" -type f | rename 's/ /_/g' || true

    # ── OpenCL ICD Setup ──────────────────────────────────────────────────────
    mkdir -p /etc/OpenCL/vendors
    # Instead of searching, use the standard location provided by the NVIDIA runtime
    echo "libnvidia-opencl.so.1" > /etc/OpenCL/vendors/nvidia.icd

    # Verify OpenCL can actually see the GPU before starting
    clinfo | grep -i "Platform Name" || echo "WARNING: clinfo found no platforms"

    # ── Kernel cache ─────────────────────────────────────────────────────────
    # Use a local work directory for the cache to avoid permission issues
    # KERNEL_CACHE="\$(pwd)/kernel_cache"
    # mkdir -p "\$KERNEL_CACHE"

    cp -r /usr/local/bin/OpenCL ./OpenCL

    # ── Docking ──────────────────────────────────────────────────────────────
    QuickVina-W-GPU-2-1 \\
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
        --opencl_binary_path ./
    """
}
