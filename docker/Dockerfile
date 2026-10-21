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

# Optional pip index (the lerobot-npu pipeline uses mirrors.ivolces.com/pypi/).
ARG PIP_INDEX_URL=
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /opt
# Both trees arrive as CP sources, so neither is cloned here: the CN build pool
# cannot reach github.com reliably (the autumn-rs Dockerfile documents the same
# problem for cargo), while CP's own clone goes through its service connection.
COPY DeepInfer /opt/DeepInfer
COPY autumn_pd /opt/DeepInfer/deepinfer/autumn_pd
COPY patches /opt/patches

RUN cd /opt/DeepInfer \
    && git apply --verbose /opt/patches/deepinfer-pd-native.patch \
    && git diff --stat | tail -3

RUN cd /opt/DeepInfer && bash ./build.sh

WORKDIR /opt/DeepInfer
