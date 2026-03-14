#!/usr/bin/env nextflow
nextflow.enable.dsl=2

params.links_file = 'data/ZINC-downloader-2D-txt.uri'
params.receptor = 'data/hif2a_temiz.pdbqt'
params.outdir = 'results'
params.chunk_size = 200

process DOWNLOAD_AND_CHUNK {
    errorStrategy 'retry'
    maxRetries 5

    input:
    val link

    output:
    path "chunk_*", optional: true

    script:
    """
    id=\$(echo "${link}" | md5sum | cut -d' ' -f1)
    curl -sL --retry 5 "${link}" | awk 'NR > 1 {print \$1, \$2}' > raw_\${id}
    [ -s raw_\${id} ] && split -l ${params.chunk_size} raw_\${id} chunk_\${id}_ || true
    """
}

process CONVERT_SMILES {
    cpus 1
    containerOptions "--env OMP_NUM_THREADS=1"

    input:
    path chunk

    output:
    path "ligands/*.pdbqt"

    script:
    """
    mkdir -p ligands
    # -m generates lig_1.pdbqt, lig_2.pdbqt, etc.
    obabel -ismi ${chunk} -opdbqt -O ligands/lig_.pdbqt -m --gen3d -p 7.4 || true

    for f in ligands/*.pdbqt; do
        if grep -qE "0\\.000\\s+0\\.000\\s+0\\.000" \$f; then
            rm -f \$f
        fi
    done
    """
}

process DOCKING {
    publishDir "${params.outdir}", mode: 'copy'
    cpus 1 // Since we are running per-ligand, 1 CPU per task is most efficient

    input:
    path ligand
    path receptor

    output:
    path "*.pdbqt"

    script:
    """
    cat > config.txt <<EOF
# Grid Box
center_x = -13.02726936340332
center_y = -22.765233993530273
center_z = 21.719926834106445
size_x = 20.0
size_y = 20.0
size_z = 20.0

# PARAMETERS
exhaustiveness = 8
num_modes = 9
energy_range = 3.0
EOF
    x_coords=\$(grep "^ATOM" ${ligand} | awk '{print \$6}' | sort -u)
    if [ "\$x_coords" == "0.000" ]; then
        echo "WARNING: '${ligand}' is a bad ligand, skipped."
        exit 0
    fi

    name=\$(grep "Name" ${ligand}| awk '{print \$4}' | head -1)
    vina --config config.txt \\
         --ligand ${ligand} \\
         --receptor ${receptor} \\
         --out zinc_\${name}.pdbqt \\
         --cpu ${task.cpus}
    """
}

workflow {
    receptor_file = file(params.receptor)

    links_ch = Channel.fromPath(params.links_file)
        .splitText()
        .map{ it.trim() }
        .filter{ it != "" }

    // First flatten: Chunk level
    chunks_ch = DOWNLOAD_AND_CHUNK(links_ch).flatten()

    // Second flatten: Ligand level
    // This ensures DOCKING starts as soon as the first PDBQT of a chunk is written
    ligands_ch = CONVERT_SMILES(chunks_ch).flatten()

    DOCKING(ligands_ch, receptor_file)
}
