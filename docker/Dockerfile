# DeepInfer + autumn PD image, built by Volcengine CP.
#
# Modeled on the autumn-rs pipeline (same workspace, same buildkit-cr component).
# Every workaround below is here because it was MEASURED on the 950PR host, not
# because it seemed prudent:
#
#   * The CANN 9.2 / 950 images ship Python 3.11 + gcc 11.4, while DeepInfer
#     requires Python 3.12 and GCC >= 13. No CANN 9.2 image on ubuntu24.04
#     (which would carry both natively) exists in quay or swr -- 10 tags probed.
#     jammy itself has neither package, so both come from PPAs. This exact
#     sequence was verified in a container on the target host: gcc 13.4.0 and
#     Python 3.12.15.
#   * DEBIAN_FRONTEND is mandatory: python3.12 pulls tzdata, whose postinst
#     prompts for a geographic area and hangs the build forever with no error.
#   * gnupg + dirmngr are RECOMMENDS of software-properties-common, not
#     depends. Without them add-apt-repository dies importing the PPA key
#     ("gpg ... --import returned non-zero exit status 2").
ARG BASE_IMAGE=quay.nju.edu.cn/ascend/cann:9.2.0-beta.1-950-ubuntu22.04-py3.11-devel
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Optional Ubuntu mirror for the apt steps, as the autumn-rs pipeline passes:
#   --build-arg APT_MIRROR=https://mirrors.ivolces.com
# The PPAs stay on launchpad and are unaffected.
ARG APT_MIRROR=
RUN if [ -n "$APT_MIRROR" ]; then \
      m="${APT_MIRROR%/}"; \
      sed -i -E "s#https?://[a-z.]*archive\.ubuntu\.com#${m}#g; s#https?://security\.ubuntu\.com#${m}#g" \
        /etc/apt/sources.list /etc/apt/sources.list.d/*.list 2>/dev/null || true; \
      echo "apt via ${m}"; \
    fi

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        software-properties-common ca-certificates gnupg dirmngr \
        curl git pkg-config make cmake ninja-build \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && add-apt-repository -y ppa:ubuntu-toolchain-r/test \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.12 python3.12-dev python3.12-venv gcc-13 g++-13 \
    && update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-13 130 \
        --slave /usr/bin/g++ g++ /usr/bin/g++-13 \
    && rm -rf /var/lib/apt/lists/* \
    && gcc --version | head -1 && python3.12 -V

# DeepInfer runs from this venv, so a bad install cannot brick the CANN
# toolkit's own interpreter (/usr/local/python3.11.16).
ENV VIRTUAL_ENV=/opt/di-venv
RUN python3.12 -m venv "$VIRTUAL_ENV" && "$VIRTUAL_ENV/bin/pip" install -U pip wheel setuptools
ENV PATH=$VIRTUAL_ENV/bin:$PATH
ENV DEEPINFER_ACCELERATOR=ascend

# mirrors.ivolces.com cannot build this project: its index stops at einops
# 0.8.1 while requirements-ascend.txt pins 0.8.2, so the resolve fails outright
# (measured on the target host). Anything pointing there is replaced with pypi.
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN case "$PIP_INDEX_URL" in \
      *mirrors.ivolces.com*) echo "PIP_INDEX_URL=$PIP_INDEX_URL cannot resolve einops 0.8.2; using pypi.org" \
        && echo "https://pypi.org/simple" > /opt/pip-index ;; \
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

RUN cd /opt/DeepInfer && PIP_INDEX_URL="$(cat /opt/pip-index)" bash ./build.sh

WORKDIR /opt/DeepInfer
