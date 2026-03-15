## Docking pipeline
Run `nextflow run main.nf` to start pipeline.


### Configurations
Change configurations on `nextflow.config`
```groovy
params {
    links_file          // (string) main downloader file
    outdir              // (string) results directory
    use3d_downloader    // (boolean) download mode
    receptor            // (string) receptor file
    // ...
}
```

### flowchart 2D MODE
![flowchart_2D](./flowchart_2D.png)
### flowchart 3D MODE
![flowchart_3D](./flowchart_3D.png)
