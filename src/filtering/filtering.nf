
process COLLECT_RESULTS {
    conda "${baseDir}/environment.yml"
    publishDir "${params.outdir}/summary", mode: 'copy'

    input:
    path "docking_results/*"

    output:
    path "docking_scores.csv*", emit: csv

    script:
    def compress_arg = params.compress_results ? "--compress" : ""
    """
    python ${baseDir}/scripts/collect_results.py \
        --input docking_results/ \
        --output docking_scores.csv \
        ${compress_arg}
    """
}

process EXTRACT_SMILES {
    conda "${baseDir}/environment.yml"
    
    input:
    path "prepped_ligands/*"

    output:
    path "all_smiles.csv*", emit: csv

    script:
    def compress_arg = params.compress_results ? "--compress" : ""
    """
    python ${baseDir}/scripts/extract_smiles.py \
        --input prepped_ligands/ \
        --output all_smiles.csv \
        ${compress_arg}
    """
}

process PREFILTER_SMILES {
    conda "${baseDir}/environment.yml"
    publishDir "${params.outdir}/prefiltering", mode: 'copy'
    cpus params.filtering_cpus

    input:
    path "smiles_in/*"
    path rules_toml

    output:
    path "${params.prefix}_prefiltered.smi*", emit: smi

    script:
    def compress_arg = params.compress_results ? "--compress" : ""
    """
    python ${baseDir}/scripts/filter_ligands.py \
        --smiles smiles_in/* \
        --rules ${rules_toml} \
        --output ${params.prefix}_properties_filtered.csv \
        --smi-output ${params.prefix}_prefiltered.smi \
        --cpus ${task.cpus} \
        ${compress_arg}
    
    python ${baseDir}/scripts/pains_filter.py \
        --input ${params.prefix}_prefiltered.smi* \
        --output ${params.prefix}_prefiltered_pains_free.csv \
        --smi-output ${params.prefix}_prefiltered.smi \
        ${compress_arg}
    """
}

process FILTER_LIGANDS {
    conda "${baseDir}/environment.yml"
    publishDir "${params.outdir}/filtering", mode: 'copy'
    cpus params.filtering_cpus

    input:
    path smiles_csv
    path scores_csv
    path rules_toml

    output:
    path "${params.prefix}_filtered_ligands.csv*", emit: csv

    script:
    def compress_arg = params.compress_results ? "--compress" : ""
    """
    python ${baseDir}/scripts/filter_ligands.py \
        --smiles ${smiles_csv} \
        --scores ${scores_csv} \
        --rules ${rules_toml} \
        --output ${params.prefix}_filtered_ligands.csv \
        --cpus ${task.cpus} \
        ${compress_arg}
    """
}

process PAINS_FILTER {
    conda "${baseDir}/environment.yml"
    publishDir "${params.outdir}/filtering", mode: 'copy'
    cpus params.filtering_cpus

    input:
    path filtered_csv

    output:
    path "${params.prefix}_filtered_ligands_pains_free.csv*", emit: csv

    script:
    def compress_arg = params.compress_results ? "--compress" : ""
    """
    python ${baseDir}/scripts/pains_filter.py \
        --input ${filtered_csv} \
        --output ${params.prefix}_filtered_ligands_pains_free.csv \
        --cpus ${task.cpus} \
        ${compress_arg}
    """
}

process BOILED_EGG {
    conda "${baseDir}/environment.yml"
    publishDir "${params.outdir}/filtering", mode: 'copy'
    cpus params.filtering_cpus

    input:
    path pains_free_csv

    output:
    path "${params.prefix}_BOILED_Egg.csv*", emit: csv
    path "${params.prefix}_BOILED_Egg.pdf", emit: pdf

    script:
    def compress_arg = params.compress_results ? "--compress" : ""
    """
    python ${baseDir}/scripts/pyBOILEDegg.py \
        --prefix "${params.prefix}" \
        --input-type "csv" \
        --infile ${pains_free_csv} \
        --cpus ${task.cpus} \
        ${compress_arg}
    """
}
