
process SPLIT_PDBQT {
    container 'quay.io/biocontainers/autodock-vina:1.1.2--2'

    input:
    tuple val(dir_name), path(pdbqt)

    output:
    tuple val(dir_name), path("ligands/*.pdbqt")

    script:
    """
    mkdir -p ligands
    vina_split --input "${pdbqt}" --ligand ligands/${pdbqt.baseName}_
    """
}