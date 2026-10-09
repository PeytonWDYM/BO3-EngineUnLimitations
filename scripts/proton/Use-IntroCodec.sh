#!/usr/bin/env bash
# Insert the decoder environment inside Steam's runtime, immediately before Proton.
set -euo pipefail
fail() { printf '%s\n' "$*" >&2; exit 2; }
[[ $# -ge 2 ]] || fail 'Use Use-IntroCodec.sh <codec-folder> <Steam command...>.'
codec=$(realpath -e -- "$1") || fail 'The intro decoder is absent.'
shift
[[ $codec != *[[:space:]:]* ]] || fail 'The decoder path must contain no whitespace or colon (LD_PRELOAD syntax).'
preload=
for name in libavutil.so.56 libswresample.so.3 libswscale.so.5 libavcodec.so.58 libavformat.so.58 libavfilter.so.7; do
    [[ -s $codec/lib/$name ]] || fail "Missing intro decoder library: $name"
    preload+=${preload:+:}$codec/lib/$name
done
[[ -s $codec/SHA256SUMS ]] || fail 'The intro decoder checksum record is absent.'
(cd -- "$codec" && sha256sum -c --status SHA256SUMS) || fail 'An intro decoder library differs from its checksum record.'
if [[ -n ${LD_PRELOAD:-} ]]; then preload+=:$LD_PRELOAD; fi
args=();matched=0
for arg in "$@"; do
    if [[ $arg == */proton ]]; then
        matched=$((matched+1))
        args+=(env "LD_PRELOAD=$preload")
    fi
    args+=("$arg")
done
[[ $matched == 1 ]] || fail 'Expected exactly one Proton executable in the Steam command.'
exec "${args[@]}"
