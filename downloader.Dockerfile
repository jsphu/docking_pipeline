# Use the slim version of Ubuntu to save space
FROM ubuntu:22.04

# Avoid prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Update and install tools
# gzip and awk come pre-installed, but curl and coreutils are added for completeness
RUN apt-get update && apt-get install -y --no-install-recommends \
  curl \
  gzip \
  gawk \
  coreutils \
  ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /data

CMD ["/bin/bash"]
