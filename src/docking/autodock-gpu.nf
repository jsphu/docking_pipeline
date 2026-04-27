process DOCKING_GPU {
    container 'autodock-gpu:latest'
    containerOptions '--gpus all --env NVIDIA_DRIVER_CAPABILITIES=compute,utility --shm-size=2g'
    publishDir "${params.outdir}", mode: 'copy'

    input:
    path ligand_dir
    path receptor
    val config

    output:
    path "results/*.dlg", emit: docked_files

    script:
    """
    set -euo pipefail
    ulimit -s unlimited
    mkdir -p results

    # 1. Create a list of ligands for batch processing (autodock-gpu style)
    # The -ffile (flexible file) expects: receptor_name ligand_name
    ls ${ligand_dir}/*.pdbqt | xargs -n 1 basename > ligand_list.txt
    
    while read ligand; do
        echo "${receptor} ${ligand_dir}/\$ligand" >> docking.ffile
    done < ligand_list.txt


    cat <<EOF >receptor.gpf
npts ${params.size_x} ${params.size_y} ${params.size_x}
gridcenter ${params.center_x} ${params.center_y} ${params.center_z}
spacing 0.375               # Standard spacing (don't change)
receptor ${receptor}        # Your receptor file
gridfld protein.maps.fld    # Output filename
types C N O S H             # Atom types in your ligands
map protein.C.map           # Map filenames
map protein.N.map
map protein.O.map
map protein.S.map
map protein.H.map
elecmap protein.e.map       # Electrostatics
dsolvmap protein.d.map      # Desolvation
dielectric -0.1465          # Standard AD4 parameter
EOF


    # 2. Run AutoDock-GPU
    # Note: --nrun determines how many docking runs per ligand
    # --lsmet: Local search method (e.g., adanls)
    autodock-gpu \
        -ffile docking.ffile \
        -p receptor.gpf \
        -nrun ${config.nrun ?: 10} \
        -lsmet adanls \
        -rescut 10 \
        -xmloutput 0

    # 3. Move results to output directory
    mv *.dlg results/
    """
}
