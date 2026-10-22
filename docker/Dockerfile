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
# Its ascend branch then imports torch_npu explicitly, so that import has to
# work here even though nothing on this machine will ever run a kernel; see the
# LD_LIBRARY_PATH note below for what that takes.
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

# Two fixes to vendor/DeepSelect, both measured against the real failing
# compile on a 950PR. They are applied here, after the submodules are checked
# out and before build_vendor.sh runs: its own `submodule update --init` has no
# --force and the recorded SHAs already match, so it leaves these edits alone.
#
# 1. setup.py hardcodes "aarch64-linux" in the include and link paths. This host
#    is x86_64, where that directory does not exist, so __has_include
#    ("kernel_operator.h") failed, kerutils never defined
#    KERUTILS_IS_BUILD_ON_ASCEND, and api.cpp died on six undeclared
#    KU_CHECK_DEVICE plus common.h's "Neither ... is defined!" #error.
#    $(uname -m) keeps it correct on an aarch64 host too.
#
# 2. bisheng compiling the device kernel cannot parse GCC 13's <utility>: it
#    reports "class member cannot be redeclared" in stl_pair.h:416. DeepInfer
#    needs GCC >= 13 for its own extension, so both toolchains are installed
#    and clang picks the newest it finds. Retrying the exact failing command:
#
#      as-is                         FAIL stl_pair.h:416
#      -nostdinc++ + GCC 11 headers   OK
#      -std=c++17                    FAIL (kernel.h errors instead)
#      --gcc-toolchain=/usr          FAIL (still picks 13)
#
#    so the kernel is pointed at the base image's own older libstdc++ headers.
#    Only DeepSelect's flags change; DeepInfer still builds against GCC 13.
# Only DeepSelect, and not --recursive: a full recursive init walks into
# vendor/DeepEP -- the CUDA variant, which build_vendor.sh does not build on
# Ascend -- whose nested DeepJIT is recorded with an ssh URL
# (git@github.com:...). There is no ssh client in the image, so that clone
# fails and takes the whole step with it. build_vendor.sh does its own
# recursive init inside each package it actually builds.
RUN set -eu; \
    cd /opt/DeepInfer; \
    git submodule update --init vendor/DeepSelect; \
    m="$(uname -m)"; \
    cxx_old="$(ls /usr/include/c++ | sort -V | head -1)"; \
    sed -i "s|\"aarch64-linux\"|\"${m}-linux\"|g" vendor/DeepSelect/setup.py; \
    sed -i "s|f\"--npu-arch={arch}\",|f\"--npu-arch={arch}\", \"-nostdinc++\", \"-isystem\", \"/usr/include/c++/${cxx_old}\", \"-isystem\", \"/usr/include/${m}-linux-gnu/c++/${cxx_old}\",|" \
        vendor/DeepSelect/setup.py; \
    grep -c "${m}-linux" vendor/DeepSelect/setup.py; \
    grep -n "nostdinc" vendor/DeepSelect/setup.py

# set_env.sh is what makes the toolkit usable, and no layer had ever sourced
# it: the base image sets the Ascend environment from /root/.bashrc, which a
# login shell picks up and a Dockerfile RUN does not. `set -eu` so a missing
# set_env.sh fails here rather than ten lines later.
#
# It also adds /usr/local/Ascend/driver/lib64{,/common,/driver}, which is where
# libascend_hal.so lives -- on an NPU host. A CP agent has no driver directory
# at all, so the stub the toolkit ships under x86_64-linux/devlib is APPENDED to
# cover that one gap. Appended, not prepended: measured on a 950PR, sourcing
# set_env.sh alone imports torch_npu fine, appending the stub dir keeps it fine,
# and *prepending* it breaks the import with "undefined symbol:
# _ZN12ErrorManager19ATCReportErrMessage..." -- devlib holds device-side builds
# of liberror_manager and libruntime_common, and in front of the path they
# shadow the host-side ones.
RUN set -eu; \
    cd /opt/DeepInfer; \
    . /usr/local/Ascend/ascend-toolkit/set_env.sh; \
    export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:$ASCEND_HOME_PATH/x86_64-linux/devlib/linux/x86_64"; \
    export TORCH_DEVICE_BACKEND_AUTOLOAD=0 \
           DEEPINFER_ACCELERATOR=ascend \
           DEEP_SELECT_BUILD_TARGET_PLATFORM=ASCEND; \
    export PIP_INDEX_URL="$(cat /opt/pip-index)"; \
    bash ./build.sh

WORKDIR /opt/DeepInfer
