#!/usr/bin/env bash
# Build the ABI-matched H.264 decoder used only for custom engine intro launches.
set -euo pipefail
[[ $# == 1 ]] || { printf '%s\n' 'Use Build-IntroCodec.sh <new-output-folder>.' >&2; exit 2; }
repo=$(realpath -- "$(dirname -- "${BASH_SOURCE[0]}")/../..")
output=$(realpath -m -- "$1")
[[ $output != "$repo" && $output != "$repo/"* && ! -e $output ]] || {
    printf '%s\n' 'Use a new output folder outside the repository.' >&2; exit 2;
}
mkdir -p -- "$output"
archive=$output/ffmpeg-4.3.7.tar.xz
curl -fL --proto '=https' https://ffmpeg.org/releases/ffmpeg-4.3.7.tar.xz -o "$archive"
printf '%s  %s\n' 177d074943251bec33e1f9bc5979378ff5771882482ba9b3aee2cb18dd400554 "$archive" | sha256sum -c -
tar -xf "$archive" -C "$output"
cd -- "$output/ffmpeg-4.3.7"
./configure --prefix="$output/codec" --disable-everything --disable-autodetect --disable-programs \
    --disable-doc --disable-x86asm --enable-shared --disable-static --enable-decoder=h264 --enable-parser=h264
make -j8
make install
cp COPYING.LGPLv2.1 "$output/codec/"
cd -- "$output/codec"
sha256sum lib/libavutil.so.56 lib/libswresample.so.3 lib/libswscale.so.5 lib/libavcodec.so.58 lib/libavformat.so.58 lib/libavfilter.so.7 > SHA256SUMS
printf '%s\n' 'FFmpeg 4.3.7, LGPL 2.1 or later. Source and build configuration are retained in the parent directory.' > "$output/codec/SOURCE.txt"
printf 'Private custom-intro decoder: %s\n' "$output/codec"
