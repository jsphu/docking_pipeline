#!/usr/bin/env nextflow
nextflow.enable.dsl=2

params.outdir = 'results'
params.links_file = 'data/ZINC-downloader-2D-txt.uri'

// --- 2D (SMILES) options ---
params.chunk_size = 200

// --- 3D (PDBQT) options ---
params.use3d_downloader = false

// Downloader Option
params.skip_download = false
params.smiles_file = ''
params.pdbqt_file = ''

// Docking Options
params.receptor = 'data/hif2a_temiz.pdbqt'
params.override = false // overwrites if same file docked before otherwise skips.
params.exhaustiveness = 8
params.center_x = -13.02726936340332
params.center_y = -22.765233993530273
params.center_z = 21.719926834106445
params.size_x = 20.0
params.size_y = 20.0
params.size_z = 20.0
params.num_modes = 9
params.energy_range = 3.0


process DOWNLOAD_SMILES_AND_CHUNK {
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

process DOWNLOAD_PDBQT_AND_UNZIP {
    errorStrategy 'retry'
    maxRetries 5

    input:
    val link

    output:
    path "*.pdbqt", optional: true

    script:
    """
    mkdir -p ligands
    id=\$(echo "${link}" | md5sum | cut -d' ' -f1)
    curl -sL --retry 5 "${link}" --output "\${id}.pdbqt.gz"
    [ -s "\${id}.pdbqt.gz" ] && gunzip "\${id}.pdbqt.gz"
    """
}

process SPLIT_PDBQT {
    input:
    path pdbqt

    output:
    path "ligands/*.pdbqt"

    script:
    """
    vina_split --input "${pdbqt}" --ligand ligands/lig_
    """
}

process OBABEL_CONVERT_SMILES {
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
    obabel -ismi ${chunk} -opdbqt -O ligands/lig_.pdbqt -m --gen3d -p 7.4
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
center_x = ${params.center_x}
center_y = ${params.center_y}
center_z = ${params.center_z}
size_x = ${params.size_x}
size_y = ${params.size_y}
size_z = ${params.size_z}

# PARAMETERS
exhaustiveness = ${params.exhaustiveness}
num_modes = ${params.num_modes}
energy_range = ${params.energy_range}
EOF
    x_coords=\$(grep "^ATOM" ${ligand} | awk '{print \$6}' | sort -u)
    name=\$(grep "Name" ${ligand}| awk '{print \$4}' | head -1)
    results_path="${workflow.launchDir}/results"
    old_file="\${results_path}/result_\${name}.pdbqt"
    empty_file="\${results_path}/empty_\${name}.pdbqt"
    if [ "\$x_coords" == "0.000" ]; then
        echo "WARNING: '${ligand}' is a bad ligand, skipped."
        ln -s "${ligand}" "empty_\${name}.pdbqt"
    elif [ -f "\${old_file}" ] && ! ${params.override}; then
        echo "NOTE: Old file not overridden, skipped."
        ln -s "\${old_file}" "result_\${name}.pdbqt"
    else
        if [ -f "\${empty_file}" ]; then
            echo "NOTE: Empty docking result will be replaced."
            rm -f "\${empty_file}"
        fi

        vina --config config.txt \\
            --ligand ${ligand} \\
            --receptor ${receptor} \\
            --out result_\${name}.pdbqt \\
            --cpu ${task.cpus}
    fi
    """
}

workflow {
    receptor_file = file(params.receptor)

    if (params.skip_download) {
        if (params.smiles_file) {
            smiles_file = file(params.smiles_file)

            ligands_ch = OBABEL_CONVERT_SMILES(smiles_file)
                .flatten()
        } else if (params.pdbqt_file) {
            pdbqt_file = file(params.pdbqt_file)

            ligands_ch = SPLIT_PDBQT(pdbqt_ch)
                .flatten()
        } else {
            error("Please give any input files, smiles_file? or pdbqt_file?")
        }

    } else {
        links_ch = Channel.fromPath(params.links_file)
            .splitText()
            .map{ it.trim() }
            .filter{ it != "" }

        if (params.use3d_downloader) {
            pdbqt_ch = DOWNLOAD_PDBQT_AND_UNZIP(links_ch)
                .flatten()

            ligands_ch = SPLIT_PDBQT(pdbqt_ch)
                .flatten()

        } else {
            chunks_ch = DOWNLOAD_SMILES_AND_CHUNK(links_ch)
                .flatten()
            // This ensures DOCKING starts as soon as the first PDBQT of a chunk is written
            ligands_ch = OBABEL_CONVERT_SMILES(chunks_ch)
                .flatten()
        }
    }

    DOCKING(ligands_ch, receptor_file)
}
