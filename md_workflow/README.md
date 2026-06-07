# Automated Molecular Dynamics & Analysis Pipeline

A professional-grade, fully automated suite for Protein-Ligand Molecular Dynamics (MD) simulations and post-simulation analysis using GROMACS, Docker, and Python.

---

## Core Features

- **End-to-End Automation:** From raw PDB/SDF files to polished HTML comparison reports.
- **Adaptive Chunked Upload:** Automatically splits massive results into 512MB/128MB/64MB parts for 100% transfer reliability.
- **Smart Progress Monitor:** Real-time progress updates (ns) sent via **Email (Gmail)** or **Telegram**.
- **Master Manifests:** Uses **GitHub Gists** to provide a single, professional link for multi-part downloads.
- **Resilient Execution:** Smart resume from checkpoints, GPU/CPU auto-fallback, and preparation skipping.

---

## Usage: Running MD (`main.py workflow`)

### 1. Basic Run

Processes all protein-ligand pairs defined in your configuration or provided via CLI.

```bash
python3 main.py workflow --protein prot.pdb --ligand lig_dir/ --outdir results
```

### 2. Skipping Preparation

If you have already prepared your protein/ligand topologies and just want to run simulations:

```bash
python3 main.py workflow --skip-prep --outdir results
```

### 3. Smart Resume

If a simulation was interrupted (e.g., cluster timeout), the system detects `.cpt` files and resumes automatically.

```bash
python3 main.py workflow --resume --outdir results
```

### 4. Real-Time Notifications

Monitor your simulation progress (in nanoseconds) at a specific interval.

```bash
# Notify every 30 minutes (1800 seconds)
python3 main.py workflow --notify-interval 1800
```

*Note: See `NOTIFY_SYSTEM.md` for Email/Telegram setup.*

---

## Usage: Post-MD Analysis (`main.py post-md`)

### 1. Full Analysis

Performs PBC correction, trajectory fitting, RMSD, RMSF, Rg, and Hydrogen Bond analysis for every completed complex.

```bash
python3 main.py post-md --outdir results
```

### 2. Selecting Specific Complexes

Analyze only a subset of your results:

```bash
python3 main.py post-md --outdir results --select 6NJS_LIG1 6NJS_LIG2
```

### 3. Master Output Handling

Generate a comparison report comparing all analyzed ligands without re-running GROMACS analysis:

```bash
python3 main.py post-md --outdir results --master-only --master-output final_comparison.html
```

---

## Data Management & Uploads

### 1. High-Reliability Uploads

When the `--upload` flag is used, the system performs an **Adaptive Chunked Upload**:

1. Archives the results directory.
2. If the file is large, it splits it into chunks.
3. Uploads chunks to cloud storage (Transfer.sh / BashUpload).
4. Creates a **GitHub Gist** containing the download links for all parts.

### 2. Enabling GitHub Gists

Export your token before running:

```bash
export GITHUB_TOKEN="your_token"
python3 main.py post-md --upload
```

---

## Configuration & Environment

### Key Command-Line Flags

| Flag | Description |
| :--- | :--- |
| `--resume` | Resume from Production MD checkpoint if it exists. |
| `--skip-prep` | Skip ligand/protein preparation; use existing topologies. |
| `--upload` | Archive and upload results (uses Chunking + Gist). |
| `--notify-interval` | Interval in seconds for progress updates. |
| `--select` | (Post-MD) List specific complexes to process. |
| `--master-only` | (Post-MD) Skip GROMACS tools; just build the comparison report. |

### Required Environment Variables

- `GITHUB_TOKEN`: For Master Manifest (Gist) uploads.
- `SMTP_PASSWORD`: Gmail App Password for email notifications.
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`: For Telegram notifications.

---

## Documentation

- **`docs/NOTIFY_SYSTEM.md`**: Detailed setup for Email, Telegram, and GitHub integration.
- **`config.json`**: Fine-tune GROMACS parameters (Temperature, Pressure, Nsteps, etc).
