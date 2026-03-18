process DOCKING {
    container 'quay.io/biocontainers/autodock-vina:1.1.2--2'
    publishDir "${params.outdir}", mode: 'copy'
    cpus 1 // Since we are running per-ligand, 1 CPU per task is most efficient

    input:
    path ligand
    path receptor
    val config
    val override

    output:
    path "*.pdbqt"

    script:
    """
    cat > config.txt <<EOF
# ligand
ligand = ${ligand}

# receptor
receptor = ${receptor}

# Grid Box
center_x = ${config.center_x}
center_y = ${config.center_y}
center_z = ${config.center_z}
size_x = ${config.size_x}
size_y = ${config.size_y}
size_z = ${config.size_z}

# PARAMETERS
exhaustiveness = ${config.exhaustiveness}
num_modes = ${config.num_modes}
energy_range = ${config.energy_range}
cpu = ${task.cpus}
EOF

    x_coords=\$(grep "^ATOM" ${ligand} | awk '{print \$6}' | sort -u)

    name=\$(grep "Name" ${ligand}| awk '{print \$4}' | head -1)
    
    results_path="${workflow.launchDir}/results"
    old_file="\${results_path}/result_\${name}.pdbqt"
    empty_file="\${results_path}/empty_\${name}.pdbqt"
    
    if [ "\$x_coords" == "0.000" ]; then
        echo "WARNING: '${ligand}' is a bad ligand, skipped."
        ln -s "${ligand}" "empty_\${name}.pdbqt"
    
    elif [ -f "\${old_file}" ] && ! ${override}; then
        echo "NOTE: Old file not overridden, skipped."
        ln -s "\${old_file}" "result_\${name}.pdbqt"
    
    else
    
        if [ -f "\${empty_file}" ]; then
            echo "NOTE: Empty docking result will be replaced."
            rm -f "\${empty_file}"
        fi

        vina --config config.txt --out result_\${name}.pdbqt
    fi
    """
}
