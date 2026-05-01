#!/usr/bin/env bash
# =============================================================================
#  One-shot installer — Molecular Docking GPU Pipeline
#  Modes: docker (default) | native | wsl
#
#  docker  — Docker Engine + NVIDIA Container Toolkit + pull/build images
#  native  — system deps + OpenBabel + clone & build QuickVina-GPU binary
#  wsl     — same as docker but skips Docker Engine install (Docker Desktop
#             provides it) and skips NVIDIA driver (Windows host provides it)
# =============================================================================
# set -euo pipefail

# ── Colour helpers ─────────────────────────────────────────────────────────────
error() {
  echo -e "\033[1;31mERROR:\033[0m $*" >&2
  exit 2
}
fail() {
  echo -e "\033[31mFAIL:\033[0m $*" >&2
  exit 1
}
warn() {
  echo -e "\033[33mWARNING:\033[0m $*" >&2
}
log() {
  printf "\033[34m[%(%H:%M:%S)T] LOG: \033[0m" >&2
  echo -e "$*" >&2
}
success() {
  printf "\033[32m[%(%H:%M:%S)T] OK:  \033[0m" >&2
  echo -e "$*\033[0m" >&2
}
finish() {
  printf "\033[32m[%(%H:%M:%S)T] DONE:\033[0m " >&2
  echo -e "$*\033[0m" >&2
  exit 0
}
step() {
  echo -e "\n\033[1;36m══ $* \033[0m" >&2
}

# ── Defaults ──────────────────────────────────────────────────────────────────
VERBOSE=false
SILENT=false
MODE=docker
BIN_DIR="${HOME}/.local/bin"
# pull | build | pull-or-build
IMAGE_STRATEGY=pull
GHCR_IMAGE="ghcr.io/jsphu/docking_pipeline/quickvina-gpu:latest"
DOWNLOADER_IMAGE="ghcr.io/jsphu/docking_pipeline/downloader:latest"
NXF_VER="24.04.4"

# ── Usage ──────────────────────────────────────────────────────────────────────
usage() {
  cat <<EOF

One-shot installer — Molecular Docking GPU Pipeline

Usage:
  $0 [OPTIONS]

Options:
  -b, --bin-dir  <PATH>   Directory for installed binaries
                            default: ~/.local/bin
  -m, --mode     <MODE>   Installation mode:
                            docker  — Docker Engine + NVIDIA toolkit + images
                                      [DEFAULT]
                            native  — build QuickVina-GPU and all deps on host
                            wsl     — Docker Desktop (already on Windows) +
                                      NVIDIA toolkit only (driver = Windows)
      --image-strategy <S>
                          How to get the Docker images (docker/wsl modes):
                            pull          — docker pull from ghcr.io  [DEFAULT]
                            build         — build locally from Dockerfiles
                            pull-or-build — try pull, fall back to build
                          For 'build' or 'pull-or-build', place Dockerfiles
                          next to this script:
                            Dockerfile.quickvina   — QuickVina-GPU image
                            Dockerfile.downloader  — downloader utility image
  -v, --verbose           Show all sub-command output
  -s, --silent            Suppress all output
  -h, --help              Show this help

Examples:
  # Fresh Linux machine — Docker mode, pull images from registry
  sudo $0 --mode docker

  # Windows user running inside WSL2
  $0 --mode wsl

  # Build everything locally (no registry, no Docker runtime)
  sudo $0 --mode native --bin-dir ~/.local/bin

  # Docker mode but build images locally instead of pulling
  sudo $0 --mode docker --image-strategy build

EOF
}

# ── Argument parser ────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
  --bin-dir | -b)
    [[ -z "${2-}" ]] && {
      usage
      fail "$1 requires a path argument"
    }
    BIN_DIR="$2"
    shift
    ;;
  --mode | -m)
    [[ -z "${2-}" ]] && {
      usage
      fail "$1 requires a mode argument"
    }
    case "$2" in
    wsl | docker | native) ;;
    *)
      usage
      fail "'$2' is not a valid mode — choose: docker | native | wsl"
      ;;
    esac
    MODE="$2"
    shift
    ;;
  --image-strategy)
    [[ -z "${2-}" ]] && {
      usage
      fail "$1 requires a strategy argument"
    }
    case "$2" in
    pull | build | pull-or-build) ;;
    *)
      usage
      fail "'$2' is not a valid strategy — choose: pull | build | pull-or-build"
      ;;
    esac
    IMAGE_STRATEGY="$2"
    shift
    ;;
  --verbose | -v) VERBOSE=true ;;
  --silent | -s)
    SILENT=true
    VERBOSE=false
    ;;
  --help | -h)
    usage
    exit 0
    ;;
  *)
    usage
    fail "Unknown argument: $1"
    ;;
  esac
  shift
done

# ── Silence / verbosity overrides ─────────────────────────────────────────────
if $SILENT; then
  warn() { :; }
  log() { :; }
  success() { :; }
  step() { :; }
  finish() { exit 0; }
  error() { exit 2; }
  fail() { exit 1; }
elif ! $VERBOSE; then
  log() { :; }
  success() { :; }
fi

# Run a command, suppress output unless --verbose
run() {
  if $VERBOSE; then
    "$@"
  else
    "$@" >/dev/null 2>&1
  fi
}

# ── Privilege helper ───────────────────────────────────────────────────────────
SUDO=""
check_root() {
  if [[ $EUID -ne 0 ]]; then
    if command -v sudo &>/dev/null; then
      SUDO="sudo"
      warn "Not running as root — sudo will be used where needed."
    else
      fail "Not root and sudo not found. Re-run as root or install sudo."
    fi
  fi
}

# ── Distro detection ───────────────────────────────────────────────────────────
PKG_MGR=""
detect_distro() {
  if [[ ! -f /etc/os-release ]]; then
    warn "Cannot detect distro (/etc/os-release missing). Assuming apt."
    PKG_MGR="apt"
    return
  fi
  # shellcheck source=/dev/null
  source /etc/os-release
  local id="${ID:-unknown}" like="${ID_LIKE:-}"
  if [[ "$id $like" =~ ubuntu|debian|linuxmint|pop|elementary|zorin ]]; then
    PKG_MGR="apt"
  else
    warn "Distro '$id' is not an officially supported Debian/Ubuntu derivative."
    warn "Proceeding with apt anyway — manual fixes may be required."
    PKG_MGR="apt"
  fi
}

detect_wsl() {
  IS_WSL=false
  grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null && IS_WSL=true || true
}

check_arch() {
  local arch
  arch="$(uname -m)"
  [[ "$arch" != "x86_64" ]] &&
    warn "Architecture '$arch' detected. QuickVina-GPU targets x86_64 only."
}

# ── apt helpers ────────────────────────────────────────────────────────────────
_apt_updated=false
apt_update() {
  if ! $_apt_updated; then
    log "apt-get update"
    run $SUDO apt-get update
    _apt_updated=true
  fi
}

apt_install() {
  log "apt-get install $*"
  run $SUDO apt-get install -y --no-install-recommends "$@"
}

# ── curl bootstrap ─────────────────────────────────────────────────────────────
ensure_curl() {
  command -v curl &>/dev/null && return
  step "Installing curl (bootstrap dependency)"
  apt_update
  apt_install curl ca-certificates
}

# ── Java ───────────────────────────────────────────────────────────────────────
install_java() {
  if command -v java &>/dev/null; then
    local ver
    ver="$(java -version 2>&1 | awk -F'"' '/version/{print $2}' | cut -d. -f1)"
    if [[ "${ver:-0}" -ge 17 ]]; then
      success "Java ${ver} already installed"
      return
    fi
    warn "Java ${ver} is too old (need >= 17). Upgrading."
  fi

  step "Installing Java 21 (Eclipse Temurin)"
  ensure_curl
  apt_update
  apt_install wget gpg software-properties-common

  wget -qO - https://packages.adoptium.net/artifactory/api/gpg/key/public |
    $SUDO gpg --dearmor -o /usr/share/keyrings/adoptium.gpg

  # Resolve the Ubuntu codename even on derivatives (Mint ships its own codename)
  local codename
  codename="$(
    . /etc/os-release
    echo "${UBUNTU_CODENAME:-${VERSION_CODENAME:-jammy}}"
  )"

  echo "deb [signed-by=/usr/share/keyrings/adoptium.gpg] \
https://packages.adoptium.net/artifactory/deb ${codename} main" |
    $SUDO tee /etc/apt/sources.list.d/adoptium.list >/dev/null
  _apt_updated=false # force re-update after adding new repo
  apt_update
  apt_install temurin-21-jdk
  success "Java 21 installed"
}

# ── Nextflow ───────────────────────────────────────────────────────────────────
install_nextflow() {
  if command -v nextflow &>/dev/null; then
    success "Nextflow already in PATH ($(nextflow -v 2>/dev/null | head -1))"
    return
  fi
  if [[ -x "${BIN_DIR}/nextflow" ]]; then
    success "Nextflow already at ${BIN_DIR}/nextflow"
    return
  fi

  step "Installing Nextflow ${NXF_VER}"
  mkdir -p "$BIN_DIR"
  curl -fsSL \
    "https://github.com/nextflow-io/nextflow/releases/download/v${NXF_VER}/nextflow" \
    -o "${BIN_DIR}/nextflow"
  chmod +x "${BIN_DIR}/nextflow"
  # Bootstrap the Nextflow runtime / pull itself
  run bash -c "PATH=${BIN_DIR}:${PATH} ${BIN_DIR}/nextflow self-update" || true
  success "Nextflow installed -> ${BIN_DIR}/nextflow"
  _warn_path
}

_warn_path() {
  if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
    warn "${BIN_DIR} is not in your \$PATH."
    warn "Add this to ~/.bashrc or ~/.zshrc:"
    warn "  export PATH=\"${BIN_DIR}:\$PATH\""
  fi
}

# ── Docker Engine ──────────────────────────────────────────────────────────────
install_docker() {
  if command -v docker &>/dev/null; then
    success "Docker already installed ($(docker --version))"
    return
  fi
  step "Installing Docker Engine (official convenience script)"
  ensure_curl
  curl -fsSL https://get.docker.com | $SUDO sh
  $SUDO usermod -aG docker "${USER}" || true
  warn "Docker group membership takes effect after you log out and back in."
  success "Docker Engine installed"
}

# ── NVIDIA Container Toolkit ───────────────────────────────────────────────────
install_nvidia_container_toolkit() {
  if dpkg -s nvidia-container-toolkit &>/dev/null 2>&1; then
    success "nvidia-container-toolkit already installed"
    return
  fi
  step "Installing NVIDIA Container Toolkit"
  ensure_curl

  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey |
    $SUDO gpg --dearmor \
      -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

  curl -fsSL \
    "https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list" |
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' |
    $SUDO tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null

  _apt_updated=false
  apt_update
  apt_install nvidia-container-toolkit

  $SUDO nvidia-ctk runtime configure --runtime=docker 2>/dev/null || true

  # Restart Docker daemon if it is already running
  if $SUDO systemctl is-active --quiet docker 2>/dev/null; then
    $SUDO systemctl restart docker
  fi

  success "NVIDIA Container Toolkit installed"
}

# ── GPU smoke-test ─────────────────────────────────────────────────────────────
check_gpu() {
  step "Checking GPU / NVIDIA driver"
  if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
    success "nvidia-smi OK — $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
  else
    warn "nvidia-smi not found or failed."
    if [[ "$MODE" == "wsl" ]]; then
      warn "(WSL2) The NVIDIA driver lives on the Windows host."
      warn "Install the NVIDIA Game-Ready or Studio driver (>=527.x) on Windows."
      warn "No separate Linux driver is needed inside WSL2."
    else
      warn "Install the NVIDIA driver for your GPU before running the pipeline."
    fi
  fi
}

# ── Docker images ──────────────────────────────────────────────────────────────
_pull_image() {
  local img="$1" label="${2:-}"
  log "Pulling ${label:-$img}"
  if run docker pull "$img"; then
    success "Pulled: ${img}"
    return 0
  else
    warn "docker pull failed for: ${img}"
    return 1
  fi
}

_build_image() {
  local tag="$1" dockerfile="$2"
  local ctx
  ctx="$(dirname "$dockerfile")"
  if [[ ! -f "$dockerfile" ]]; then
    fail "Dockerfile not found: ${dockerfile}"
  fi
  step "Building image ${tag} from ${dockerfile}"
  run docker build -t "$tag" -f "$dockerfile" "$ctx"
  success "Built image: ${tag}"
}

_resolve_dockerfile() {
  local name="$1"
  local script_dir
  script_dir="$(cd "$(dirname "$0")" && pwd)"
  for candidate in \
    "${script_dir}/Dockerfile.${name}" \
    "${script_dir}/docker/Dockerfile.${name}" \
    "${script_dir}/Dockerfile"; do
    [[ -f "$candidate" ]] && {
      echo "$candidate"
      return
    }
  done
  fail "Cannot find Dockerfile for '${name}'. Expected: ${script_dir}/Dockerfile.${name}"
}

manage_images() {
  step "Docker images (strategy: ${IMAGE_STRATEGY})"

  case "$IMAGE_STRATEGY" in

  pull)
    _pull_image "$GHCR_IMAGE" "QuickVina-GPU image"
    _pull_image "$DOWNLOADER_IMAGE" "Downloader image" ||
      warn "Downloader image pull failed — non-fatal if you won't use the downloader."
    ;;

  build)
    _build_image "$GHCR_IMAGE" "$(_resolve_dockerfile quickvina)"
    _build_image "$DOWNLOADER_IMAGE" "$(_resolve_dockerfile downloader)"
    ;;

  pull-or-build)
    _pull_image "$GHCR_IMAGE" "QuickVina-GPU image" ||
      _build_image "$GHCR_IMAGE" "$(_resolve_dockerfile quickvina)"
    _pull_image "$DOWNLOADER_IMAGE" "Downloader image" ||
      { _build_image "$DOWNLOADER_IMAGE" "$(_resolve_dockerfile downloader)" ||
        warn "Downloader image unavailable — non-fatal."; }
    ;;

  esac
}

# ── WSL2: verify Docker Desktop integration ────────────────────────────────────
check_wsl_docker() {
  step "WSL2: verifying Docker Desktop integration"
  if ! command -v docker &>/dev/null; then
    warn "docker not found inside WSL2."
    warn "In Docker Desktop -> Settings -> General:"
    warn "  enable 'Use WSL2 based engine'"
    warn "In Docker Desktop -> Settings -> Resources -> WSL Integration:"
    warn "  enable integration for this distro, then re-run this installer."
    fail "Docker not accessible from WSL2. See warnings above."
  fi
  success "Docker Desktop integration active"
}

# ── Native build deps ──────────────────────────────────────────────────────────
install_native_build_deps() {
  step "Installing native build dependencies (Boost, OpenCL, OpenBabel...)"
  apt_update
  apt_install \
    git build-essential \
    libboost-all-dev \
    opencl-headers ocl-icd-opencl-dev clinfo ocl-icd-libopencl1 \
    openbabel rename wget
  success "Build dependencies installed"
}

# ── Clone & build QuickVina-GPU ────────────────────────────────────────────────
build_quickvina_native() {
  if [[ -x "${BIN_DIR}/QuickVina-W-GPU-2-1" ]]; then
    success "QuickVina-W-GPU-2-1 already at ${BIN_DIR}"
    return
  fi
  if command -v QuickVina-W-GPU-2-1 &>/dev/null; then
    success "QuickVina-W-GPU-2-1 already in PATH"
    return
  fi

  step "Cloning Vina-GPU-2.1 and building QuickVina-W-GPU-2-1"
  local build_dir="/tmp/Vina-GPU-2.1-$$"
  # Clean up on exit (whether success or failure)
  trap 'rm -rf "$build_dir"' EXIT

  run git clone --depth=1 \
    https://github.com/DeltaGroupNJUPT/Vina-GPU-2.1.git "$build_dir"

  pushd "${build_dir}/QuickVina-W-GPU-2.1" >/dev/null

  # ── Makefile patches — same as in your Dockerfile ──────────────────────────
  sed -i 's|^BOOST_LIB_PATH=.*|BOOST_LIB_PATH=/usr/include|' Makefile
  sed -i 's|^VINA_GPU_INC_PATH=.*|VINA_GPU_INC_PATH=-I./lib -I./OpenCL/inc|' Makefile
  sed -i 's|^LIB_PATH=.*|LIB_PATH=-L/usr/lib/x86_64-linux-gnu -L/usr/local/cuda/lib64|' Makefile
  sed -i 's|$(BOOST_LIB_PATH)/libs/thread/src/pthread/thread.cpp||' Makefile
  sed -i 's|$(BOOST_LIB_PATH)/libs/thread/src/pthread/once.cpp||' Makefile
  sed -i 's|LIB1=.*|LIB1=-lboost_program_options -lboost_system -lboost_filesystem -lboost_thread -lOpenCL -no-pie|' Makefile
  sed -i 's|OPENCL_VERSION=.*|OPENCL_VERSION=-DOPENCL_3_0|' Makefile
  sed -i 's/if (thread < 1000)/if (thread < 16)/g' main/main.cpp
  sed -i 's|MACRO=.*|MACRO=$(OPENCL_VERSION) $(GPU_PLATFORM) $(DOCKING_BOX_SIZE) -DBOOST_TIMER_ENABLE_DEPRECATED -DCL_TARGET_OPENCL_VERSION=300 -fPIC|' Makefile

  run make source -j "$(nproc)"

  mkdir -p "$BIN_DIR"
  cp QuickVina-W-GPU-2-1 "${BIN_DIR}/"
  cp -r OpenCL "${BIN_DIR}/" # kernel binaries live next to the exe

  popd >/dev/null
  success "QuickVina-W-GPU-2-1 -> ${BIN_DIR}/"
  warn "OpenCL kernels are at ${BIN_DIR}/OpenCL."
  warn "Either copy that directory to each run's working directory, or add"
  warn "  --opencl_binary_path ${BIN_DIR}"
  warn "to the QuickVina call in your Nextflow DOCKING_GPU process."
  _warn_path
}

# ── Verification ───────────────────────────────────────────────────────────────
verify() {
  step "Verification"
  local all_ok=true

  _chk() {
    local label="$1"
    shift
    if "$@" &>/dev/null; then
      success "  + ${label}"
    else
      warn "  - ${label} (check failed)"
      all_ok=false
    fi
  }

  _chk "java (>=17)" java -version
  _chk "nextflow" bash -c "PATH=${BIN_DIR}:${PATH} nextflow -v"

  case "$MODE" in
  docker | wsl)
    _chk "docker daemon" docker info
    _chk "QuickVina image" docker image inspect "$GHCR_IMAGE"

    # Live GPU pass-through test — only if the nvidia runtime is wired up
    if docker info 2>/dev/null | grep -qi nvidia; then
      _chk "GPU in container" \
        docker run --rm --gpus all \
        nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi
    else
      warn "  ~ GPU container test skipped (nvidia runtime not yet active)."
      warn "    Re-run after logging out/in or restarting the Docker daemon."
    fi
    ;;
  native)
    _chk "QuickVina-W-GPU-2-1" bash -c "PATH=${BIN_DIR}:${PATH} QuickVina-W-GPU-2-1 --help"
    _chk "obabel" obabel --version
    ;;
  esac

  $all_ok ||
    warn "Some checks failed — review the warnings above before running the pipeline."
}

# ── Summary ────────────────────────────────────────────────────────────────────
print_summary() {
  echo -e "\n\033[1;32m╔══════════════════════════════════════════════════════════╗" >&2
  echo -e "║      Installation complete — quick reference             ║" >&2
  echo -e "╚══════════════════════════════════════════════════════════╝\033[0m" >&2
  cat >&2 <<EOF

  Mode            : ${MODE}
  BIN_DIR         : ${BIN_DIR}
  Nextflow binary : ${BIN_DIR}/nextflow
  Image strategy  : ${IMAGE_STRATEGY:-n/a (native mode)}

  Make sure ${BIN_DIR} is in your PATH:
    export PATH="${BIN_DIR}:\$PATH"

EOF

  if [[ "$MODE" == "native" ]]; then
    cat >&2 <<EOF
  For native runs, copy ${BIN_DIR}/OpenCL to each working directory, or add
  --opencl_binary_path ${BIN_DIR} in your DOCKING_GPU process script.

EOF
  fi

  if [[ "$MODE" == "docker" ]]; then
    warn "Docker group changes need a logout/login to take effect."
    warn "Until then, prefix docker commands with: sudo"
  fi
}

# =============================================================================
#  MAIN
# =============================================================================
main() {
  check_root
  detect_distro
  detect_wsl
  check_arch
  ensure_curl

  # Friendly nudge if mode doesn't match the detected environment
  if $IS_WSL && [[ "$MODE" == "docker" ]]; then
    warn "WSL2 detected but --mode docker was selected."
    warn "If you are using Docker Desktop on Windows, --mode wsl is more appropriate."
  fi

  # Java + Nextflow are required in every mode
  install_java
  install_nextflow

  case "$MODE" in

  docker)
    install_docker
    install_nvidia_container_toolkit
    check_gpu
    manage_images
    ;;

  wsl)
    # Docker daemon lives on Windows (Docker Desktop).
    # Only validate the integration and install the container toolkit.
    check_wsl_docker
    install_nvidia_container_toolkit
    check_gpu
    manage_images
    ;;

  native)
    install_native_build_deps
    build_quickvina_native
    check_gpu
    ;;

  esac

  verify
  print_summary
  finish "mode='${MODE}' — all done."
}

main "$@"
