
process PREPARE_LIGANDS {
    tag "${dir_name}"
    container 'quay.io/biocontainers/openbabel:3.1.1--2'
    cpus 1
    containerOptions "--env OMP_NUM_THREADS=1"

    input:
    tuple val(dir_name), path(ligand)

    output:
    tuple val(dir_name), path("ligands/*.pdbqt")

    script:
    def ext = ligand.extension
    // Normalize extension
    def format = ext
    if (ext == 'smiles' || ext == 'txt' || ext == "") format = 'smi'
    
    if (format == 'pdbqt')
        """
        mkdir -p raw_ligands
        # Split multi-model pdbqt or just copy single one
        obabel -ipdbqt ${ligand} -opdbqt -O raw_ligands/lig_.pdbqt -m

        mkdir -p ligands
        for f in raw_ligands/*.pdbqt; do
            # Check for non-zero coordinates
            if grep -q "ATOM" "\$f"; then
                x_coords=\$(grep "^ATOM" "\$f" | awk '{print \$6}' | sort -u)
                if [ "\$x_coords" != "0.000" ]; then
                    # Keep only first molecule for Vina-GPU compatibility
                    sed '/TORSDOF/q' "\$f" > "ligands/\$(basename \$f)"
                fi
            fi
        done
        """
    else
        """
        mkdir -p raw_ligands
        # -m generates lig_1.pdbqt, lig_2.pdbqt, etc.
        # -p 7.4 for pH-aware protonation
        # --gen3d for 3D coordinate generation
        obabel -i${format} ${ligand} -opdbqt -O raw_ligands/lig_.pdbqt -m -p 7.4 --gen3d
        
        mkdir -p ligands
        for f in raw_ligands/*.pdbqt; do
            # Check for non-zero coordinates
            if grep -q "ATOM" "\$f"; then
                x_coords=\$(grep "^ATOM" "\$f" | awk '{print \$6}' | sort -u)
                if [ "\$x_coords" != "0.000" ]; then
                    # Keep only first molecule for Vina-GPU compatibility
                    sed '/TORSDOF/q' "\$f" > "ligands/\$(basename \$f)"
                fi
            fi
        done
        """
}
