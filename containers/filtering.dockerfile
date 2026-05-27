FROM continuumio/miniconda3:latest

RUN conda install -c conda-forge -y \
    python=3.11 \
    rdkit \
    pandas \
    shapely \
    matplotlib \
    tomli \
    && conda clean -afy

WORKDIR /app
