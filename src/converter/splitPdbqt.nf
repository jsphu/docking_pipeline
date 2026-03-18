
process SPLIT_PDBQT {
    container 'quay.io/biocontainers/autodock-vina:1.1.2--2'

    input:
    path pdbqt

    output:
    path "ligands/*.pdbqt"

    script:
    """
    vina_split --input "${pdbqt}" --ligand ligands/lig_
    """
}