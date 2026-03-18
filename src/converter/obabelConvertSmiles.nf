
process OBABEL_CONVERT_SMILES {
    container 'quay.io/biocontainers/openbabel:3.1.1--2'
    cpus 1
    containerOptions "--env OMP_NUM_THREADS=1"

    input:
    path smi

    output:
    path "ligands/*.pdbqt"

    script:
    """
    mkdir -p ligands
    # -m generates lig_1.pdbqt, lig_2.pdbqt, etc.
    obabel -ismi ${smi} -opdbqt -O ligands/lig_.pdbqt -m --gen3d -p 7.4
    """
}