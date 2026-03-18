process DOWNLOAD_SMILES {
    container 'ubuntu:20.04'
    errorStrategy 'retry'
    maxRetries 5

    input:
    val link

    output:
    path "raw_*", optional: true

    script:
    """
    id=\$(echo "${link}" | md5sum | cut -d' ' -f1)
    curl -sL --retry 5 "${link}" | awk 'NR > 1 {print \$1, \$2}' > unk_raw_\${id}
    [ -s "unk_raw_\${id}" ] && mv "unk_raw_\${id}" "raw_\${id}"
    """
}