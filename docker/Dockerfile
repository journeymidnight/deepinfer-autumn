# DeepInfer + autumn PD image, built by Volcengine CP.
#
# FROM the deps image, which its OWN pipeline builds and pushes -- same split as
# build-lerobot-deps / build-lerobot in this account. The toolchain install is
# slow and intermittently 503s from the CN build pool (one run fetched 65 MB at
# ~70 kB/s and lost nine packages), so it belongs in a pipeline that runs rarely
# rather than in this one.
#
# The deps image is built AND pushed by CP, not from the Ascend host: buildkit-cr
# already holds registry credentials there, whereas pushing a ~14 GB image from
# the host filled its docker filesystem and died with ENOSPC (the CANN base
# layers are absent from the target registry, so nothing dedupes).
ARG BASE_IMAGE=dongmao-test-cn-beijing.cr.volces.com/dongmao-test/deepinfer-deps:cann9.2-py312-gcc13
FROM ${BASE_IMAGE}

# mirrors.ivolces.com cannot build this project: its index stops at einops
# 0.8.1 while requirements-ascend.txt pins 0.8.2, so the resolve fails outright
# (measured on the target host). Anything pointing there is replaced with pypi.
ARG PIP_INDEX_URL=https://repo.huaweicloud.com/repository/pypi/simple
RUN case "$PIP_INDEX_URL" in \
      *mirrors.ivolces.com*) echo "PIP_INDEX_URL=$PIP_INDEX_URL cannot resolve einops 0.8.2; using the huaweicloud mirror" \
        && echo "https://repo.huaweicloud.com/repository/pypi/simple" > /opt/pip-index ;; \
      *) echo "$PIP_INDEX_URL" > /opt/pip-index ;; \
    esac
ENV PIP_INDEX_URL=""

WORKDIR /opt
COPY patches /opt/patches
COPY autumn_pd /opt/autumn_pd
COPY DEEPINFER_REV /opt/DEEPINFER_REV

# Upstream DeepInfer is fetched here rather than vendored, so this repo stays a
# delta and never a fork. The pinned SHA comes from DEEPINFER_REV.
#
# GITHUB_MIRROR exists because the CN build pool cannot reach github.com
# reliably -- the autumn-rs Dockerfile documents the same problem for cargo and
# defaults to the same proxy. Set it empty to go direct:
#   --build-arg GITHUB_MIRROR=
# The proxy must serve git-upload-pack anonymously; ghproxy.net began answering
# 401 on the POST while GET info/refs still returned 200, so probes passed and
# every real fetch died. ghfast.top answers both (measured 2026-10-21).
ARG GITHUB_MIRROR=https://ghfast.top/https://github.com/
RUN set -eux; \
    sha="$(cut -d= -f2 /opt/DEEPINFER_REV)"; \
    base="${GITHUB_MIRROR:-https://github.com/}"; \
    mkdir -p /opt/DeepInfer && cd /opt/DeepInfer && git init -q; \
    git remote add origin "${base}deepseek-ai/DeepInfer.git"; \
    git fetch --depth 1 origin "$sha"; \
    git checkout -q FETCH_HEAD; \
    git -c url."${base}".insteadOf=https://github.com/ submodule update --init --depth 1; \
    du -sh vendor/* | tail -6

RUN cd /opt/DeepInfer \
    && git apply --verbose /opt/patches/deepinfer-pd-native.patch \
    && cp -r /opt/autumn_pd deepinfer/autumn_pd \
    && git diff --stat | tail -4

# TORCH_DEVICE_BACKEND_AUTOLOAD=0 is required to build here at all. The vendor
# setup.py files import torch, torch then auto-loads the torch_npu backend, and
# torch_npu needs libascend_hal.so -- which belongs to the Ascend DRIVER, bind
# mounted from the host, not to the CANN toolkit. A CP build agent has no NPU
# and no driver, so the import dies with "cannot open shared object file" before
# a single kernel is compiled. Compiling needs the toolkit, which IS in the
# image; only the runtime needs the driver. torch itself still imports fine.
#
# Two more things the build needs to be told, both measured on the 950PR:
#
#   DEEPINFER_ACCELERATOR -- scripts/build.sh reads it as
#   PLATFORM_TAG="${DEEPINFER_ACCELERATOR:-nvidia}-$(uname -m)", so unset it
#   builds and installs the extension under nvidia-x86_64 and an Ascend host
#   then finds no _so/ascend-x86_64 to import.
#
#   DEEP_SELECT_BUILD_TARGET_PLATFORM -- vendor/DeepSelect/setup.py detects the
#   platform by importing torch_npu. With the autoload above disabled it falls
#   back to Platform.CUDA and dies on "PyTorch must be compiled with CUDA
#   support"; the env var (uppercase ASCEND) overrides the detection.
#
# Its ascend branch then imports torch_npu explicitly, which still wants
# libascend_hal.so. The CANN toolkit ships a link stub of it under
# x86_64-linux/devlib/linux/x86_64 -- that is in the image, unlike the driver --
# and that stub is enough: the run that added it got as far as
# "Building DeepSelect (ASCEND)".
#
# lspci is a real build dependency, not a convenience. DeepSelect imports
# tests.kernelkit, whose build.py calls get_current_platform() at import time,
# and that falls through to `lspci` when /dev/davinci_manager is absent -- as it
# is on a CP agent. With it installed the detection returns CPU_ONLY, which is
# the branch that avoids importing CUDA machinery, and the env var above still
# decides what actually gets built.
RUN apt-get update \
    && apt-get install -y --no-install-recommends pciutils \
    && rm -rf /var/lib/apt/lists/*

# build.sh updates DeepSelect's submodules, and those carry their own
# github.com URLs, so GITHUB_MIRROR above does not cover them: cloning
# NVIDIA/cutlass direct took 90s to fail on "GnuTLS recv error (-110)" twice,
# and the run before that happened to succeed. A url.insteadOf rewrite sends
# every github.com clone through the mirror, submodules included.
RUN git config --global url."${GITHUB_MIRROR}".insteadOf "https://github.com/"

RUN cd /opt/DeepInfer \
    && TORCH_DEVICE_BACKEND_AUTOLOAD=0 \
       DEEPINFER_ACCELERATOR=ascend \
       DEEP_SELECT_BUILD_TARGET_PLATFORM=ASCEND \
       LD_LIBRARY_PATH="${ASCEND_HOME_PATH:-/usr/local/Ascend/ascend-toolkit/latest}/x86_64-linux/devlib/linux/x86_64:${LD_LIBRARY_PATH:-}" \
       PIP_INDEX_URL="$(cat /opt/pip-index)" bash ./build.sh

WORKDIR /opt/DeepInfer
