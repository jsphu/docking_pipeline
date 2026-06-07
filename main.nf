#!/usr/bin/env nextflow
nextflow.enable.dsl=2

params.help           = false

// --- Help Message ---
def helpMessage() {
    log.info"""
    Usage:
      nextflow run main.nf [options]

    Main Options:
      --receptor           [path]  Path to the receptor file (PDB, PDBQT, etc.). Default: ${params.receptor}
      --ligands            [path]  Path to ligand file(s) (SMILES, SDF, PDB, PDBQT). Supports globs.
      --outdir             [path]  The output directory where results will be saved. Default: ${params.outdir}

    Input Handling:
      --skip_download      [bool]  Skip downloading from ZINC and use local files. Default: ${params.skip_download}
      --smiles_file        [path]  Local SMILES file (deprecated, use --ligands).
      --pdbqt_file         [path]  Local PDBQT file (deprecated, use --ligands).
      --sdf_file           [path]  Local SDF file (deprecated, use --ligands).
      --one_pdbqt          [bool]  Set to true if input is a single-ligand PDBQT (no splitting). Default: ${params.one_pdbqt}
      --chunk_size         [int]   Number of lines per chunk when splitting SMILES/SDF. Default: ${params.chunk_size}

    Docking Configuration:
      --use_gpu            [bool]  Use QuickVina-GPU for docking. Default: ${params.use_gpu}
      --exhaustiveness     [int]   Vina exhaustiveness parameter. Default: ${params.exhaustiveness}
      --center_x/y/z       [float] Coordinates of the grid box center.
      --size_x/y/z         [float] Dimensions of the grid box.
      --num_modes          [int]   Maximum number of binding modes to generate. Default: ${params.num_modes}
      --energy_range       [float] Maximum energy difference between the best and worst modes (kcal/mol). Default: ${params.energy_range}

    Filtering & Analysis:
      --prefilter          [bool]  Run pre-docking filtering (Rules + PAINS). Default: ${params.prefilter}
      --run_filtering      [bool]  Run post-docking analysis (PAINS, Properties, BOILED-Egg). Default: ${params.run_filtering}
      --rules_file         [path]  TOML file containing filtering rules. Default: ${params.rules_file}

    GPU Specifics:
      --collate_size       [int]   Number of ligands to batch per GPU task. Default: ${params.collate_size}
      --thread_size        [int]   Thread size for GPU docking. Default: ${params.thread_size}

    Other:
      --override           [bool]  Overwrite existing results in the output directory. Default: ${params.override}
      --help                       Show this message.
    """.stripIndent()
}

if (params.help) {
    helpMessage()
    exit 0
}

include { DOCKING }                     from './src/docking/vina.nf'
include { DOCKING_GPU }                 from './src/docking/quickvina-gpu.nf'
include { DOWNLOAD_SMILES }             from './src/downloader/downloadSmiles.nf'
include { DOWNLOAD_PDBQT_AND_UNZIP }    from './src/downloader/downloadPdbqtAndUnzip.nf'
include { PREPARE_PROTEIN }             from './src/preparation/protein.nf'
include { PREPARE_LIGANDS }             from './src/preparation/ligand.nf'
include { SPLIT_INPUT }                 from './src/preparation/split.nf'
include { COLLECT_RESULTS; EXTRACT_SMILES; FILTER_LIGANDS; PAINS_FILTER; BOILED_EGG; PREFILTER_SMILES } from './src/filtering/filtering.nf'

workflow {
    def docking_config = [ center_x: params.center_x, center_y: params.center_y, center_z: params.center_z, size_x: params.size_x, size_y: params.size_y, size_z: params.size_z, exhaustiveness: params.exhaustiveness, num_modes: params.num_modes, energy_range: params.energy_range, thread_size: params.thread_size ]

    receptor_file_ch = PREPARE_PROTEIN(channel.fromPath(params.receptor))

    links_ch = channel.fromPath(params.links_file)

    main_ch = params.ligands 
        ? channel.fromPath(params.ligands)
        : params.use3d_downloader
            ? DOWNLOAD_PDBQT_AND_UNZIP(links_ch).flatten() 
            : DOWNLOAD_SMILES(links_ch).flatten() 

    // Validation for filtering
    if (params.prefilter || params.run_filtering) {
        if (!params.rules_file || !file(params.rules_file).exists()) {
            error "Parameter --rules_file is required and must exist when --prefilter or --run_filtering is enabled. Current value: ${params.rules_file}"
        }
    }

    // Optional pre-filtering for SMILES
    if (params.prefilter) {
        main_ch = main_ch.branch {
            smi: it.extension == 'smi' || it.extension == 'smiles' || it.extension == 'txt'
            other: true
        }

        prefiltered_smi_ch = PREFILTER_SMILES(main_ch.smi.collect(), file(params.rules_file))
        main_ch = prefiltered_smi_ch.smi.mix(main_ch.other)
    }

    // We branch based on whether the data is 3D (PDBQT) or 2D (SMILES) or only one pdbqt
    if (params.one_pdbqt) {
        ligands_ch = main_ch
            | flatten
            | map { f -> [f.baseName.replaceAll('_', '-').toUpperCase(), f] }
    } else {
        raw_ligands_ch = main_ch
            | map { f -> [f.baseName.replaceAll('_', '-').toUpperCase(), f] }
            | branch {
                splitable: it[1].extension == 'smi' || it[1].extension == 'smiles' || it[1].extension == 'txt' || it[1].extension == 'sdf'
                other: true
            }

        split_ch = SPLIT_INPUT(raw_ligands_ch.splitable) | transpose
        
        ligands_ch = split_ch.mix(raw_ligands_ch.other)
            | PREPARE_LIGANDS
            | transpose
    } 

    if (params.use_gpu) {
        ligands_ch
            .groupTuple()
            .flatMap { dir_name, ligands -> 
                ligands.collate(params.collate_size).collect { batch -> [dir_name, batch] }
            }
            .set { gpu_batches_ch }

        docking_output_ch = DOCKING_GPU(
            gpu_batches_ch,
            receptor_file_ch,
            docking_config
        ).docked_files
      } else {
          docking_output_ch = DOCKING(
              ligands_ch,
              receptor_file_ch,
              docking_config,
              params.override
          )
      }

    // Always collect scores regardless of filtering
    scores_csv_ch = COLLECT_RESULTS(docking_output_ch.collect())

    if (params.run_filtering) {
        // Extract SMILES from the prepared ligands for property calculation
        smiles_csv_ch = EXTRACT_SMILES(ligands_ch.map{it[1]}.collect())

        rules_toml = file(params.rules_file)

        filtered_ch = FILTER_LIGANDS(smiles_csv_ch, scores_csv_ch, rules_toml)
        pains_free_ch = PAINS_FILTER(filtered_ch.csv)
        BOILED_EGG(pains_free_ch.csv)
    }
}

def get_links_channel() {
    if (params.skip_download) return channel.empty()
    return channel.fromPath(params.links_file)
        .splitText()
        .map { x -> x.trim() }
        .filter { x -> x != "" }
}
// --- Helper Function ---
def get_local_channel() {
    if (params.ligands)     return channel.fromPath(params.ligands)
    if (params.smiles_file) return channel.fromPath(params.smiles_file)
    if (params.pdbqt_file)  return channel.fromPath(params.pdbqt_file)
    if (params.sdf_file)    return channel.fromPath(params.sdf_file)
    error "Missing input: Please provide --ligands, --smiles_file, --pdbqt_file, or --sdf_file when using --skip_download"
}

// --- Default Parameters ---
params.outdir           = 'results'
params.links_file       = 'data/ZINC-downloader-2D-txt.uri'
params.chunk_size       = 200
params.use3d_downloader = false
params.skip_download    = false
params.ligands          = ''
params.smiles_file      = ''
params.pdbqt_file       = ''
params.sdf_file         = ''
params.one_pdbqt        = false
params.prefilter        = false
params.run_filtering    = false
params.rules_file       = 'scripts/rules.toml'
params.use_gpu          = false
params.thread_size      = 8000
params.collate_size     = 100
params.receptor         = 'data/hif2a_temiz.pdbqt'
params.override         = false
params.exhaustiveness   = 8
params.center_x         = -13.02726936340332
params.center_y         = -22.765233993530273
params.center_z         = 21.719926834106445
params.size_x           = 20.0
params.size_y           = 20.0
params.size_z           = 20.0
params.num_modes        = 9
params.energy_range     = 3.0
