#!/usr/bin/env nextflow
nextflow.enable.dsl=2

include { DOCKING }                     from './src/docking/vina.nf'
include { DOWNLOAD_SMILES }             from './src/downloader/downloadSmiles.nf'
include { SPLIT_SMILES }                from './src/converter/splitSmiles.nf'
include { DOWNLOAD_PDBQT_AND_UNZIP }    from './src/downloader/downloadPdbqtAndUnzip.nf'
include { SPLIT_PDBQT }                 from './src/converter/splitPdbqt.nf'
include { OBABEL_CONVERT_SMILES }       from './src/converter/obabelConvertSmiles.nf'

workflow {
    def docking_config = [ center_x: params.center_x, center_y: params.center_y, center_z: params.center_z, size_x: params.size_x, size_y: params.size_y, size_z: params.size_z, exhaustiveness: params.exhaustiveness, num_modes: params.num_modes, energy_range: params.energy_range ]

    receptor_file = file(params.receptor)

    links_ch = get_links_channel()

    main_ch = params.skip_download ? get_local_channel() 
        : params.use3d_downloader
            ? DOWNLOAD_PDBQT_AND_UNZIP(links_ch).flatten() 
            : DOWNLOAD_SMILES(links_ch).flatten() 

    // We branch based on whether the data is 3D (PDBQT) or 2D (SMILES)
    if (params.use3d_downloader || params.pdbqt_file) {
        ligands_ch = main_ch
            | SPLIT_PDBQT 
            | flatten
    } else {
        ligands_ch = main_ch
            | SPLIT_SMILES 
            | flatten 
            | OBABEL_CONVERT_SMILES 
            | flatten
    }

    DOCKING(
        ligands_ch,
        receptor_file,
        params.outdir,
        docking_config,
        params.override
    )
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
    if (params.smiles_file) return channel.fromPath(params.smiles_file)
    if (params.pdbqt_file)  return channel.fromPath(params.pdbqt_file)
    error "Missing input: Please provide --smiles_file or --pdbqt_file when using --skip_download"
}

// --- Default Parameters ---
params.outdir           = 'results'
params.links_file       = 'data/ZINC-downloader-2D-txt.uri'
params.chunk_size       = 200
params.use3d_downloader = false
params.skip_download    = false
params.smiles_file      = ''
params.pdbqt_file       = ''
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