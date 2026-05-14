# Molecular Dynamics Workflow

The workflow is fully automated via `md_workflow.py` and is controlled by an external `config.json` file.

## Technical Implementation

### Script: `md_workflow.py`

- **Dynamic Configuration**: All simulation parameters (integrators, cut-offs, coupling, etc.) are read from a JSON config file.
- **Library Repair**: Automatically detects and repairs internal `acpype` dependencies (`libmfhdf.so.0`, etc.) by setting correct symlinks and environment variables.
- **Robust Topology Handling**: Implements a custom topology merger that correctly extracts GAFF atomtypes and inserts them at the top of the GROMACS `.top` file to prevent syntax errors.
- **Path Isolation**: Uses absolute path resolution to ensure `gmxapi` can find all input files (protein, ligand, MDPs) within its managed execution subdirectories.

### Key Files

- `config.json`: Master configuration for production runs.
- `md_workflow.py`: The automation engine.
- `plotter.py`: A basic, graph tool for XVGs

## Usage Instructions

To perform the simulations, update your parameters in `config.json` and run:

```bash
python3 md_workflow.py -c config.json --outdir my_results
```

After MD analysis, you can see graphs -XVGs- via using `plotter.py`:

```bash
python3 plotter.py XVG-file.xvg
```

### Arguments

- `-c`, `--config`: Path to the JSON configuration file (default: `config.json`).
- `-o`, `--outdir`: Directory where all outputs (MDPs, GROs, TOPs, XTCs) will be saved (default: `results`).
- `-w`, `--workdir`: Directory where all internal-files used for MD (NVT, NPT, EM, CPT files) will be saved (default: `work`).
- `--protein`, `-p PROTEIN [PROTEIN ...]` Protein files (PDB/PDBQT) or directories
- `--ligand`, `-l LIGAND [LIGAND ...]` Ligand files (SMILES/PDBQT/MOL2) or directories
- `--gpu` Enable GPU acceleration
- `--no-gpu`
- `--docker` Run via Docker
- `--no-docker` Run from local build (e.g. /usr/local/bin/gmx)
- `--image IMAGE` Docker image (default: `nvcr.io/hpc/gromacs:2023.2` which you can access from `ngc.nvidia.com`)

#### Usage

```bash
$ python3 md_workflow.py --help
usage: md_workflow.py [-h] [--config CONFIG]
                      [--protein PROTEIN [PROTEIN ...]]
                      [--ligand LIGAND [LIGAND ...]] [--outdir OUTDIR]
                      [--workdir WORKDIR] [--gpu] [--no-gpu] [--docker]
                      [--no-docker] [--image IMAGE]

Automated MD Workflow for Protein-Ligand Complexes

options:
  -h, --help            show this help message and exit
  --config, -c CONFIG   Path to config file
  --protein, -p PROTEIN [PROTEIN ...]
                        Protein files (PDB/PDBQT) or directories
  --ligand, -l LIGAND [LIGAND ...]
                        Ligand files (SMILES/PDBQT/MOL2) or directories
  --outdir, -o OUTDIR   Output directory
  --workdir, -w WORKDIR
                        Working directory
  --gpu                 Enable GPU acceleration
  --no-gpu
  --docker              Run via Docker
  --no-docker
  --image IMAGE         Docker image
```
