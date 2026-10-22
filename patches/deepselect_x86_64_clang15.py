#!/usr/bin/env python3
"""Make vendor/DeepSelect build on an x86_64 host with CANN 9.2.0's bisheng.

Run from the DeepInfer checkout, after vendor/DeepSelect is checked out and
before scripts/build_vendor.sh. Every edit asserts its target text is present,
so an upstream change breaks the build here with a clear message instead of
silently producing an image whose kernels were never patched.

Three edits, each measured against the real failing compile on a 950PR:

1. setup.py hardcodes "aarch64-linux" in the include and link paths. On x86_64
   that directory does not exist, so __has_include("kernel_operator.h") failed,
   kerutils never defined KERUTILS_IS_BUILD_ON_ASCEND, and api.cpp died on six
   undeclared KU_CHECK_DEVICE plus common.h's "Neither ... is defined!".

2. bisheng is clang 15.0.5, which cannot parse GCC 13's <utility>: compiling
   the device kernel reports "class member cannot be redeclared" in
   stl_pair.h:416. DeepInfer itself needs GCC >= 13, so both toolchains are
   installed and clang picks the newest it finds. Retrying the exact command
   ninja ran: as-is FAIL, -nostdinc++ with the older headers OK, -std=c++17
   FAIL, --gcc-toolchain=/usr FAIL (still picks 13).

3. Those older headers have no <format>, and api.cpp uses std::format once, to
   build a TORCH_CHECK message. TORCH_CHECK is variadic and concatenates its
   arguments, so the same message needs no <format> at all. This is what makes
   one flag set work for both sources; per-source flags would otherwise mean
   turning ninja off and hooking the compiler.
"""

import os
import pathlib
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "vendor/DeepSelect")
MACHINE = os.uname().machine


def edit(path, old, new, *, count=1):
    p = ROOT / path
    text = p.read_text()
    found = text.count(old)
    if found != count:
        sys.exit(f"{p}: expected {count} occurrence(s) of:\n{old}\nfound {found}")
    p.write_text(text.replace(old, new))
    print(f"  patched {p} ({count}x)")


# 1. architecture-specific CANN paths
edit("setup.py", '"aarch64-linux"', f'"{MACHINE}-linux"', count=2)

# 2. the device kernel compiles against the oldest libstdc++ in the image,
#    which is the one the base image shipped and clang 15 can parse.
cxx = sorted(
    (d.name for d in pathlib.Path("/usr/include/c++").iterdir() if d.name.isdigit()),
    key=int,
)
if not cxx:
    sys.exit("no libstdc++ headers found under /usr/include/c++")
old_headers = cxx[0]
print(f"  libstdc++ versions present: {', '.join(cxx)}; kernel will use {old_headers}")
edit(
    "setup.py",
    'f"--npu-arch={arch}",',
    'f"--npu-arch={arch}",\n'
    '                    "-nostdinc++",\n'
    f'                    "-isystem", "/usr/include/c++/{old_headers}",\n'
    f'                    "-isystem", "/usr/include/{MACHINE}-linux-gnu/c++/{old_headers}",',
)

# 3. the one std::format call, rewritten in TORCH_CHECK's own variadic form
edit(
    "csrc/api.cpp",
    '            std::format("{}.stride(0) (currently {} numbers) must be a multiple of {} Bytes ({} numbers)",\n'
    "                tensor_name, cur_stride,\n"
    "                alignment_requirement_bytes, alignment_requirement_bytes / itemsize\n"
    "            )\n",
    '            tensor_name, ".stride(0) (currently ", cur_stride,\n'
    '            " numbers) must be a multiple of ", alignment_requirement_bytes,\n'
    '            " Bytes (", alignment_requirement_bytes / itemsize, " numbers)"\n',
)

print("DeepSelect patched for", MACHINE)
