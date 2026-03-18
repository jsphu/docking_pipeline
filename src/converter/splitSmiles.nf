
process SPLIT_SMILES {
    container 'custom-linux:latest'
    input:
    path raw_file

    output:
    path "chunk_*"

    script:
    """
    name="${raw_file}"
    name="\${name/raw_/}"
    split -l ${params.chunk_size} ${raw_file} "chunk_\${name}_"
    """
}