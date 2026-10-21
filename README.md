# deepinfer-autumn

Builds the DeepInfer image carrying autumn-backed prefill/decode (PD)
disaggregation, through Volcengine CP.

DeepInfer itself is **not forked here**. `DEEPINFER_REV` pins the upstream
commit, CP clones `deepseek-ai/DeepInfer` as a second source, and this repo
carries only the delta:

| Path | What |
|---|---|
| `patches/deepinfer-pd-native.patch` | the `csrc/` scheduler methods PD needs (C++, so it must be compiled into the image) |
| `autumn_pd/` | the Python adapter, copied to `deepinfer/autumn_pd/` |
| `docker/Dockerfile` | fetches DeepInfer, applies the delta, runs `build.sh` (FROM the deps image) |
| `docker/Dockerfile.deps` | the toolchain base: CANN 9.2 + Python 3.12 + GCC 13 |
| `docker/pipeline-spec-deps.yaml` | the deps pipeline spec (build + push `deepinfer-deps`) |
| `scripts/toolchain.sh` | the same toolchain steps, as run on the host |
| `docker/pipeline-spec.yaml` | the CP pipeline spec, to paste in the console |

## Why the Dockerfile looks like that

Each step is there because it was measured on an Ascend 950PR host, not out of
caution:

- The CANN 9.2 / 950 images ship Python 3.11 and gcc 11.4; DeepInfer requires
  Python 3.12 and GCC >= 13. No CANN 9.2 image on ubuntu24.04 (which has both
  natively) exists in quay or swr — 10 tags probed. jammy carries neither
  package, so both come from PPAs. Verified in a container on the target host:
  gcc 13.4.0, Python 3.12.15.
- `DEBIAN_FRONTEND=noninteractive` is mandatory: `python3.12` pulls `tzdata`,
  whose postinst prompts for a geographic area and hangs the build with no
  error and no exit code.
- `gnupg` and `dirmngr` are *recommends* of `software-properties-common`, not
  depends. Without them `add-apt-repository` dies importing the PPA key.
- Nothing is cloned from github inside the build. The CN build pool cannot
  reach github reliably (autumn-rs's Dockerfile documents the same problem for
  cargo); CP's own clone goes through its service connection instead.

## Why the toolchain is a separate image

`ppa.launchpadcontent.net` serves the CN build pool at roughly 70 kB/s with
intermittent 503s — one CP run fetched 65 MB over 15m31s and still lost nine
packages, failing the build after 18 minutes. The same apt sequence installs
cleanly from the Ascend host. USTC's launchpad proxy does not fix it: it answers
200 on `Release` and 503 on the pool, so a build gets a healthy-looking index
and then fails fetching debs.

The toolchain therefore lives in its own image, `deepinfer-deps`, built and
pushed by its **own CP pipeline** — the same split as `build-lerobot-deps` /
`build-lerobot` in this account. `deepinfer-autumn` just does `FROM` it, so the
pipeline that runs often never repeats that install.

The deps image is built by CP rather than on the Ascend host. `buildkit-cr`
already has registry credentials there, while pushing the ~14 GB image from the
host exhausted its docker filesystem and died with ENOSPC — the CANN base layers
are not in the target registry, so nothing dedupes and the whole image uploads.

## Creating the pipeline

CP's API has no create-pipeline endpoint — only delete/list/run/cancel/webhook
— so each pipeline is created once by hand in the console. **Two** are needed:

| pipeline | dockerfile | tag | when it runs |
|---|---|---|---|
| `deepinfer-deps` | `docker/Dockerfile.deps` | `cann9.2-py312-gcc13` (fixed) | only when the toolchain changes |
| `deepinfer-autumn` | `docker/Dockerfile` | `${SCM_COMMIT_ID}` | every change here |

The deps tag is fixed on purpose: the main Dockerfile's `BASE_IMAGE` names it,
and the toolchain changes far less often than this repo. After both exist,
`volc-cp run start` drives them.
