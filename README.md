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
