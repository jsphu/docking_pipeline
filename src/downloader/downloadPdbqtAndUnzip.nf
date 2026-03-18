
process DOWNLOAD_PDBQT_AND_UNZIP {
    container 'ubuntu:20.04'
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