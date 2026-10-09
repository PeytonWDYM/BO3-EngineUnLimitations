#!/usr/bin/env bash
# Optional Linux prefix: Play-Intro.sh <local-video> <existing launch command...>
set -euo pipefail
[[ $# -ge 2 ]] || { printf '%s\n' 'Use Play-Intro.sh <local-video> <launch command...>.' >&2; exit 2; }
video=$1
shift
if [[ -f $video ]] && command -v ffplay >/dev/null 2>&1; then
    # Play through the desktop audio server before the Proton game starts.
    # Keep Steam's overlay preload out of this Linux media player only.
    if ! env -u LD_PRELOAD SDL_AUDIODRIVER=pulseaudio ffplay -hide_banner -loglevel error \
        -nostats -fs -autoexit -volume 100 -window_title 'BO3 startup video' -i "$video"; then
        printf '%s\n' 'Intro playback failed; continuing the game launch.' >&2
    fi
else
    printf '%s\n' 'Local intro video or ffplay is absent; continuing the game launch.' >&2
fi
exec "$@"
