## Docking pipeline

Run `nextflow run main.nf` to start pipeline.

### Configurations

Use or create new configurations on `config/`

```sh
config/5TBM-GPU-ACCELERATED.config <= Using quickvina-gpu
config/5TBM.config <= Using vina
...
```

### Packages

If you want to execute this pipeline, i suggest you to use container images;

```bash
# QuickVina-GPU, access with QuickVina-W-GPU-2-1 on commandline
docker pull ghcr.io/jsphu/docking_pipeline/quickvina-gpu:latest
# Downloader used for downloading from links
docker pull ghcr.io/jsphu/docking_pipeline/downloader:latest
```

![flowchart](assets/Dag.png)

## Post-Docking Analysis & Filtering

After running the pipeline, you can filter the results and prepare them for the next phase (e.g., SwissADME, MD Simulations).

### 1. Filter Best Ligands
Filter ligands based on `scripts/rules.txt` (MW < 400, LogP <= 5, LE >= 0.3, PSA < 60, etc.) and apply **PAINS** filters to remove false positives.
```bash
python3 scripts/filter_ligands.py
python3 scripts/pains_filter.py
```
*Output: `data/filtered_ligands.csv`*

### 2. Prepare for SwissADME
Standardize SMILES strings (fix radical issues and valency) for compatibility with medicinal chemistry tools.
```bash
python3 scripts/prepare_swissadme.py
```
*Output: `data/filtered_ligands.smi` (Ready to upload to SwissADME)*

### 3. Organize Lead PDBQTs
Collect the docking pose files of the filtered leads into a single directory for visualization.
```bash
python3 scripts/collect_leads.py
```
*Output: `data/best_leads_pdbqt/`*

### 4. Generate Summary Report
View a ranked list of the top candidates by combined efficiency.
```bash
python3 scripts/summary_report.py
```
