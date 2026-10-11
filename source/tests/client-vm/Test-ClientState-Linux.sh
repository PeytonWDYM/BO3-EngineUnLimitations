#!/usr/bin/env bash
# Exercise the shared codec with owned callbacks. This does not run BO3 or Proton.
set -euo pipefail
fail() { printf '%s\n' "$*" >&2; exit 2; }
[[ $# == 1 ]] || fail 'Use Test-ClientState-Linux.sh <new-output-folder>.'
repo=$(realpath -e -- "$(dirname -- "${BASH_SOURCE[0]}")/../../..")
output=$(realpath -m -- "$1")
[[ $output != "$repo" && $output != "$repo/"* && ! -e $output ]] || fail 'Use a new output folder outside the repository.'
mkdir -p -- "$output"
compiler=${CXX:-g++}
"$compiler" --version > "$output/compiler.txt"
"$compiler" -std=c++20 -O2 -Wall -Wextra -Werror \
    "$repo/source/tests/client-vm/ClientStateFixture.cpp" \
    "$repo/source/patches/vm_pool/StateAdapter.cpp" \
    -o "$output/ClientStateFixture" 2>&1 | tee "$output/build.txt"
"$output/ClientStateFixture" | tee "$output/trace.txt"
python3 - "$repo" "$output" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
repo, output = map(Path, sys.argv[1:])
files = [repo / 'source/tests/client-vm/ClientStateFixture.cpp',
         repo / 'source/patches/vm_pool/StateAdapter.cpp',
         repo / 'source/patches/vm_pool/StateAdapter.h',
         output / 'ClientStateFixture', output / 'trace.txt', output / 'compiler.txt']
receipt = {'passed': True, 'scope': 'Owned codec callbacks on Linux. No native BO3, DLL, Wine, or Proton validation.',
           'files': [{'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in files]}
(output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
PY
