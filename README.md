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
| `docker/Dockerfile` | CANN 9.2 + Python 3.12 + GCC 13, then `build.sh` |
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

## Creating the pipeline

CP's API has no create-pipeline endpoint — only delete/list/run/cancel/webhook
— so the pipeline must be created once by hand in the console from
`docker/pipeline-spec.yaml`. After that `volc-cp run start` drives it.
