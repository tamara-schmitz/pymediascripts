# pymediascripts
A collection of Python scripts for converting and batch processing certain media files

These scripts were written for my own use first, and are made available second. If you have any suggestions on how to improve these scripts, feel free to open up a new **Issue** or even a **Pull Request**. Thank you, your input is appreciated.

## Run as a container

A GitHub CI regularly builds container images based on openSUSE Tumbleweed. To use them you need a working installation of either **docker** or **podman**.

### Use the manga converter

```bash
docker run --rm -it -v ./input_directory:/in:ro -v ./output_directory:/out:Z ghcr.io/tamara-schmitz/pymediascripts-manga /in /out/manga.pdf
```

### Use the music converter

```bash
docker run --rm -it -v ./input_directory:/in:ro -v ./output_directory:/out:Z ghcr.io/tamara-schmitz/pymediascripts-music -p smaller /in /out
```

### Use the picture converter

```bash
docker run --rm -it -v ./input_directory:/in:ro -v ./output_directory:/out:Z ghcr.io/tamara-schmitz/pymediascripts-picture -p smaller /in /out
```
