
process PREPARE_PROTEIN {
    tag "${receptor.baseName}"
    container 'quay.io/biocontainers/openbabel:3.1.1--2'

    input:
    path receptor

    output:
    path "prepared_receptor.pdbqt"

    script:
    def ext = receptor.extension
    if (ext == 'pdbqt')
        """
        cp ${receptor} prepared_receptor.pdbqt
        """
    else if (ext == 'pdb')
        """
        obabel -ipdb ${receptor} -opdbqt -O prepared_receptor.pdbqt -xr
        """
    else
        """
        obabel -i${ext} ${receptor} -opdbqt -O prepared_receptor.pdbqt -xr
        """
}
