
process SPLIT_INPUT {
    tag "${dir_name}"
    container 'ubuntu:22.04'
    
    input:
    tuple val(dir_name), path(raw_file)

    output:
    tuple val(dir_name), path("chunk_*")

    script:
    def ext = raw_file.extension
    """
    # split might not support --additional-suffix in all versions, 
    # so we use a loop to rename if needed, but ubuntu 22.04 should support it.
    split -l ${params.chunk_size} ${raw_file} "chunk_${raw_file.baseName}_" --additional-suffix=.${ext}
    """
}
