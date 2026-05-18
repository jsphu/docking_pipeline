# Molecular Dynamics & Analysis Workflow

A fully automated suite for Protein-Ligand Molecular Dynamics simulations and post-simulation analysis using GROMACS.

## Features

- **Automated Simulation (`md_workflow.py`)**: Handles protein/ligand preparation, box setup, solvation, ionization, and equilibration (EM, NVT, NPT) followed by production MD.
- **Advanced Post-Analysis (`post_md.py`)**: Automated trajectory processing (PBC correction, fitting) and standard MD analysis.
- **Visual Reports**: Generates standalone, self-contained HTML reports for every complex, including high-quality plots for RMSD, RMSF, Radius of Gyration, and Hydrogen Bonds.
- **Smart Resume**: Supports resuming simulations and skipping already processed complexes.
- **Docker Integration**: Runs GROMACS via Docker with GPU support for easy setup and high performance.

---

## Installation & Requirements

- Python 3.8+
- Docker (for GROMACS execution)
- Python Packages: `matplotlib`, `numpy`, `rdkit` (if preparing ligands from SMILES)

---

## Workflow Guide

### 1. Production MD Simulation

Run the main workflow to prepare and simulate your complexes. The script reads parameters from `config.json`.

```bash
python3 md_workflow.py -c config.json --outdir results --docker
```

### 2. Post-MD Analysis

Once the simulation is complete, run the analysis script to process trajectories and generate reports.

```bash
python3 post_md.py --outdir results --docker
```

This will:
1. Fix PBC (Periodic Boundary Conditions).
2. Fit the trajectory to the protein backbone.
3. Calculate RMSD (Protein & Ligand), RMSF (Protein), Radius of Gyration, and Hydrogen Bonds.
4. Generate an HTML report in `results/analysis_{complex_name}/`.

---

## Key Components

### Scripts
- `md_workflow.py`: The simulation automation engine.
- `post_md.py`: The analysis automation engine.
- `plotter.py`: A wrapper for plotting individual XVG files.

### Configuration (`config.json`)
Controls all simulation parameters:
- **Force Field & Water Model**: `amber99sb-ildn`, `tip3p`, etc.
- **Equilibration Steps**: Steps, time-steps, and coupling parameters for EM, NVT, and NPT.
- **Production MD**: Duration, output frequency (xtc, energy, log).
- **Environment**: Temperature, pressure, and box settings.

---

## Detailed Usage

### `md_workflow.py` Arguments
- `-c`, `--config`: Path to the JSON configuration file (default: `config.json`).
- `-o`, `--outdir`: Directory where production results (XTC, TPR, GRO) are saved.
- `-w`, `--workdir`: Directory for temporary simulation files.
- `-p`, `--protein`: Protein files (PDB/PDBQT) or directories.
- `-l`, `--ligand`: Ligand files (SMILES/PDBQT/MOL2) or directories.
- `--gpu / --no-gpu`: Enable/Disable GPU acceleration.
- `--docker / --no-docker`: Use Docker container for GROMACS.

### `post_md.py` Arguments
- `-o`, `--outdir`: Directory where simulation results are stored (reads `.xtc` and `.tpr` files).
- `-p`, `--protein` / `-l`, `--ligand`: (Optional) Specify specific IDs to analyze. If omitted, scans `outdir` automatically.
- `--docker / --no-docker`: Use Docker for GROMACS analysis tools.

---

## Analysis Reports

The `post_md.py` script generates a standalone HTML report for each complex located at:
`[outdir]/analysis_[complex_name]/report_[complex_name].html`

**Report Features:**
- **Self-Contained**: Plots are embedded as Base64 images; no external files needed.
- **Print to PDF**: Optimized for browser printing. Open the HTML file, press `Ctrl+P`, and "Save as PDF" for a professional report.
- **Metadata**: Includes force field information and simulation conditions used.
