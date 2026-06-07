# Molecular Docking & MD Pipeline

A high-performance, automated pipeline for large-scale virtual screening and molecular dynamics simulations. Built with **Nextflow**, it leverages **GPU-accelerated** docking engines and provides integrated post-docking analysis and MD workflows.

![Pipeline Flowchart](assets/Dag.png)

## Quick Start

The fastest way to get started is using the one-shot installer.

```bash
# Clone the repository
git clone https://github.com/jsphu/docking_pipeline.git
cd docking_pipeline

# Run the installer (Docker mode is recommended)
sudo ./install.sh --mode docker

# Run a sample docking session
nextflow run main.nf --smiles_file data/sample_ligands.smi --receptor data/receptor.pdbqt
```

## Key Features

- **GPU Acceleration:** Support for `AutoDock-GPU`, `Vina-GPU`, and `QuickVina-GPU` for ultra-fast screening.
- **Flexible Inputs:** Support for 2D (SMILES) and 3D (PDBQT) ligand inputs.
- **Automated Downloader:** Directly fetch ligands from ZINC or other URI links.
- **Containerized:** Full support for Docker and Singularity, ensuring reproducibility and easy deployment.
- **Post-Docking Suite:** Integrated scripts for filtering (Lipinski, PAINS), scoring, and lead collection.
- **Automated MD:** One-command Molecular Dynamics workflow using GROMACS (via `md_workflow/main.py`).

## Installation & Setup

### Prerequisites

- **Linux** (Ubuntu/Debian recommended) or **WSL2**.
- **NVIDIA GPU** with latest drivers (required for GPU acceleration).
- **Docker** or **Singularity/Apptainer** (optional but highly recommended).

### Using the Installer

The `install.sh` script automates the installation of Java, Nextflow, Docker, and the NVIDIA Container Toolkit.

| Mode | Description |
| :--- | :--- |
| `docker` | (Recommended) Installs Docker, NVIDIA toolkit, and pulls images from GHCR. |
| `wsl` | For WSL2 users with Docker Desktop on Windows. |
| `native` | Builds everything on the host (Nextflow, Java, QuickVina-GPU binaries). |

```bash
# Example: Install for Linux with Docker
sudo ./install.sh --mode docker
```

## Usage Guide

### 1. Basic Docking (CPU/Vina)

Run docking on a local SMILES file using standard AutoDock Vina.

```bash
nextflow run main.nf \
  --smiles_file data/ligands.smi \
  --receptor data/receptor.pdbqt \
  --outdir results
```

### 2. GPU Accelerated Docking (QuickVina-GPU)

Enable GPU acceleration and provide a specialized configuration.

```bash
nextflow run main.nf \
  --use_gpu \
  --smiles_file data/ligands.smi \
  --receptor data/receptor.pdbqt \
  -c config/5TBM-GPU-ACCELERATED.config
```

### 3. Downloading from ZINC

Specify a file containing download links (URIs) to fetch and dock ligands directly.

```bash
nextflow run main.nf --links_file data/ZINC-links.uri --use3d_downloader
```

### ⚙️ Main Parameters

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `--receptor` | `data/...` | Path to the receptor PDBQT file. |
| `--smiles_file` | `''` | Input SMILES file for local screening. |
| `--pdbqt_file` | `''` | Input PDBQT file for local screening. |
| `--use_gpu` | `false` | Enable GPU-accelerated docking. |
| `--center_x/y/z` | - | Coordinates of the docking box center. |
| `--size_x/y/z` | `20.0` | Dimensions of the docking box (Angstroms). |
| `--exhaustiveness`| `8` | Search exhaustiveness for Vina. |

## Post-Docking Analysis

After docking, use the provided Python suite to filter and organize your results.

1. **Filter Ligands:** Applies Lipinski rules (`scripts/rules.txt`) and PAINS filters to remove false positives.

    ```bash
    python3 scripts/filter_ligands.py
    python3 scripts/pains_filter.py
    ```

2. **Prepare SwissADME:** Standardize SMILES for online medicinal chemistry tools.

    ```bash
    python3 scripts/prepare_swissadme.py
    ```

3. **Collect Leads:** Organizes top-performing PDBQT poses into a single directory for visualization.

    ```bash
    python3 scripts/collect_leads.py
    ```

## Molecular Dynamics (MD)

Perform automated GROMACS simulations for your top lead compounds:

```bash
python3 md_workflow/main.py workflow \
  --protein protein.pdb \
  --ligand ligand.pdbqt \
  --config config.json \
  --docker
```

*For more details, see the [MD Workflow documentation](md_workflow/README.md).*

## License

This project is licensed under the [LICENSE](LICENSE) - see the file for details.
