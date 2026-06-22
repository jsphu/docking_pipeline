// Nextflow processes for GROMACS Molecular Dynamics workflow

process SELECT_TOP_LIGANDS {
    label 'small'
    publishDir "${params.outdir}/md_selected_ligands", mode: 'copy'

    input:
    path "filtered.csv"
    path "scores.csv"
    path "docked_dir/*"
    val limit

    output:
    path "selected_*.pdbqt", emit: pdbqts
    path "selected_ligands.csv", emit: csv

    script:
    """
    export PYTHONPATH=${baseDir}:\${PYTHONPATH:-}
    python ${baseDir}/scripts/select_top_ligands.py \
        --filtered-csv filtered.csv \
        --scores-csv scores.csv \
        --docked-dir docked_dir/ \
        --output-dir . \
        --limit ${limit}
    """
}

process PREPARE_MD_SYSTEM {
    conda "${params.md_conda}"
    publishDir "${params.outdir}/md_preparation", mode: 'copy'
    cpus params.md_cpus

    input:
    path ligand_pdbqt
    path receptor
    path config_json

    output:
    tuple val(complex_name), path("prep_out/*"), emit: prep_dir

    script:
    complex_name = "${receptor.baseName}_${ligand_pdbqt.baseName}"
    """
    mkdir -p prep_out
    
    export PYTHONPATH=${baseDir}:\${PYTHONPATH:-}
    # Run python preparation in Conda environment (generates topologies, box setup, solvation, ionization)
    python -m src.md_workflow.workflow \
        --config ${config_json} \
        --protein ${receptor} \
        --ligand ${ligand_pdbqt} \
        --outdir prep_out/ \
        --workdir prep_out/ \
        --no-docker \
        --prep-only \
        --cpus ${task.cpus}
    """
}

process MD_SIMULATION {
    container "${params.md_container}"
    containerOptions '--gpus all --env NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics --shm-size=4g'
    conda "${params.md_conda}"
    publishDir "${params.outdir}/md_simulations", mode: 'copy'
    cpus params.md_cpus
    accelerator 1, type: 'gpu'

    input:
    tuple val(complex_name), path(prep_dir)

    output:
    tuple val(complex_name), path("results/${complex_name}_md.tpr"), path("results/${complex_name}_md.xtc"), emit: trajectory
    path "results/*", emit: all_files

    script:
    """
    mkdir -p results
    
    # Determine GROMACS GPU acceleration flags
    gpu_flags=""
    if [ "${params.md_use_gpu}" = "true" ]; then
        if gmx mdrun -version 2>&1 | grep -i "OpenCL" >/dev/null; then
            gpu_flags="-nb gpu -pme gpu -bonded cpu -update cpu"
        else
            gpu_flags="-nb gpu -pme gpu -bonded gpu -update gpu"
        fi
    fi


    # 1. Energy Minimization
    gpu_flags_em=\$(echo "\$gpu_flags" | sed 's/-pme gpu/-pme cpu/g' | sed 's/-bonded gpu/-bonded cpu/g' | sed 's/-update gpu/-update cpu/g')
    gmx grompp -f em.mdp -c ${complex_name}_final.gro -p ${complex_name}_prot.top -o results/${complex_name}_em.tpr -maxwarn 5
    gmx mdrun -v -deffnm results/${complex_name}_em -ntmpi 1 -ntomp ${task.cpus} -pin on \$gpu_flags_em

    # 2. NVT Equilibration
    gmx grompp -f nvt.mdp -c results/${complex_name}_em.gro -r results/${complex_name}_em.gro -p ${complex_name}_prot.top -o results/${complex_name}_nvt.tpr -maxwarn 5
    gmx mdrun -v -deffnm results/${complex_name}_nvt -ntmpi 1 -ntomp ${task.cpus} -pin on \$gpu_flags
    for f in results/${complex_name}_nvt.part0001.*; do
        if [ -f "\$f" ]; then
            mv "\$f" "\${f/.part0001/}"
        fi
    done

    # 3. NPT Equilibration
    gmx grompp -f npt.mdp -c results/${complex_name}_nvt.gro -r results/${complex_name}_nvt.gro -t results/${complex_name}_nvt.cpt -p ${complex_name}_prot.top -o results/${complex_name}_npt.tpr -maxwarn 5
    gmx mdrun -v -deffnm results/${complex_name}_npt -ntmpi 1 -ntomp ${task.cpus} -pin on -noappend \$gpu_flags
    for f in results/${complex_name}_npt.part0001.*; do
        if [ -f "\$f" ]; then
            mv "\$f" "\${f/.part0001/}"
        fi
    done

    # 4. Production Molecular Dynamics Simulation
    # Override nsteps parameter if params.md_steps is set
    if [ -n "${params.md_steps}" ] && [ "${params.md_steps}" -gt 0 ]; then
        sed -i "s/nsteps.*/nsteps = ${params.md_steps}/g" md.mdp
    fi

    gmx grompp -f md.mdp -c results/${complex_name}_npt.gro -t results/${complex_name}_npt.cpt -p ${complex_name}_prot.top -o results/${complex_name}_md.tpr -maxwarn 5
    gmx mdrun -v -deffnm results/${complex_name}_md -ntmpi 1 -ntomp ${task.cpus} -pin on -noappend \$gpu_flags
    for f in results/${complex_name}_md.part0001.*; do
        if [ -f "\$f" ]; then
            mv "\$f" "\${f/.part0001/}"
        fi
    done
    
    # Store parameters alongside GROMACS trajectories
    cp *.top *.gro *.itp results/ || true
    """
}

process POST_MD_ANALYSIS {
    container "${params.md_container}"
    containerOptions '--gpus all --env NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics --shm-size=4g'
    conda "${params.md_conda}"
    publishDir "${params.outdir}/md_analysis_data", mode: 'copy'
    cpus params.md_cpus

    input:
    tuple val(complex_name), path(tpr), path(xtc)
    path get_ligand_group_py

    output:
    tuple val(complex_name), path("analysis_${complex_name}/*"), emit: analysis_data

    script:
    """
    mkdir -p analysis_${complex_name}
    
    # Extract GROMACS ligand group name dynamically
    LIG_GROUP=\$(python3 get_ligand_group.py ${tpr} ${complex_name})
    echo "Detected Ligand Group: \$LIG_GROUP"
    
    # Create temporary index
    echo "q" | gmx make_ndx -f ${tpr} -o ${complex_name}.ndx
    
    # 1. Fix PBC
    echo "Protein" "System" | gmx trjconv -pbc mol -center -f ${xtc} -s ${tpr} -o ${complex_name}_noPBC.xtc
    
    # 2. Fit Trajectory
    echo "Backbone" "System" | gmx trjconv -fit rot+trans -f ${complex_name}_noPBC.xtc -s ${tpr} -o ${complex_name}_fitted.xtc
    
    # 3. RMSD Protein
    echo "Backbone" "Backbone" | gmx rms -s ${tpr} -f ${complex_name}_fitted.xtc -o analysis_${complex_name}/rmsd_protein.xvg -tu ns
    
    # 4. RMSD Ligand
    echo "Backbone" "\$LIG_GROUP" | gmx rms -s ${tpr} -f ${complex_name}_fitted.xtc -o analysis_${complex_name}/rmsd_ligand.xvg -tu ns
    
    # 5. RMSF Protein
    echo "C-alpha" | gmx rmsf -s ${tpr} -f ${complex_name}_fitted.xtc -o analysis_${complex_name}/rmsf_protein.xvg -res
    
    # 6. Radius of Gyration
    echo "Backbone" | gmx gyrate -s ${tpr} -f ${complex_name}_fitted.xtc -o analysis_${complex_name}/rg_protein.xvg
    
    # 7. Hydrogen Bonds
    echo "Protein" "\$LIG_GROUP" | gmx hbond -s ${tpr} -f ${complex_name}_fitted.xtc -num analysis_${complex_name}/hbonds.xvg
    """
}

process PLOT_AND_REPORT {
    conda "${params.md_conda}"
    publishDir "${params.outdir}/md_analysis_reports", mode: 'copy'
    cpus params.md_cpus

    input:
    tuple val(complex_name), path("analysis_in/*")
    path config_json

    output:
    path "analysis_${complex_name}", emit: report_dir
    path "analysis_${complex_name}/*.html", emit: html_report

    script:
    """
    mkdir -p analysis_${complex_name} work
    cp analysis_in/* analysis_${complex_name}/
    
    export PYTHONPATH=${baseDir}:\${PYTHONPATH:-}
    # Generate reports and graphs inside Conda environment (no docker run of gromacs needed)
    python -m src.md_workflow.post_md \
        --config ${config_json} \
        --select ${complex_name} \
        --outdir . \
        --workdir work \
        --no-docker \
        --report-only
    """
}

process GENERATE_MASTER_REPORT {
    conda "${params.md_conda}"
    publishDir "${params.outdir}/md_summary", mode: 'copy'
    
    input:
    path "analysis_dirs/*"
    path config_json

    output:
    path "master_analysis_report.html", emit: master_report

    script:
    """
    mkdir -p results_merged work_merged
    cp -r analysis_dirs/* results_merged/
    
    export PYTHONPATH=${baseDir}:\${PYTHONPATH:-}
    python -m src.md_workflow.post_md \
        --config ${config_json} \
        --outdir results_merged/ \
        --workdir work_merged/ \
        --no-docker \
        --master-only \
        --master-output master_analysis_report.html
        
    mv results_merged/master_analysis_report.html .
    """
}
