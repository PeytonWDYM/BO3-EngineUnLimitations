#!/usr/bin/env bash
# Copy beside the native files as BO3-500K/Launch-Steam.sh; retain Steam's command.
set -euo pipefail
fail() { printf '%s\n' "$*" >&2; exit 2; }
root=$(realpath -e -- "$(dirname -- "${BASH_SOURCE[0]}")")
game=$(dirname -- "$root")
for name in BO3-500K-Zombies.exe Bo3EnhancedHelper.dll Bo3StartupGate.dll; do
    [[ -f $root/$name ]] || fail "Missing launcher file: $name"
done
[[ -f $game/BlackOps3.exe ]] || fail 'BlackOps3.exe is absent.'
mode=stock
if [[ -f $root/intro-mode ]]; then mode=$(cat -- "$root/intro-mode"); fi
[[ $mode == stock || $mode == skip || $mode == custom ]] || fail 'Intro mode must be stock, skip or custom.'
if [[ $mode == custom ]]; then
    [[ -x $root/Use-IntroCodec.sh && -s $root/intro-codec.path ]] || fail 'The custom intro decoder configuration is absent.'
    codec=$(cat -- "$root/intro-codec.path")
fi
args=();matched=0
for arg in "$@"; do
    if [[ $arg == "$game/BlackOps3.exe" ]]; then
        matched=$((matched+1))
        args+=("$root/BO3-500K-Zombies.exe" "Z:${game//\//\\}\\BlackOps3.exe")
        if [[ $mode == skip ]]; then args+=(--skip-intro); fi
        if [[ $mode == custom ]]; then args+=(--custom-intro); fi
    elif [[ $arg != --skip-intro && $arg != --custom-intro ]]; then
        args+=("$arg")
    fi
done
[[ $matched == 1 ]] || fail 'Expected exactly one installed BlackOps3.exe in the Steam command.'
export STEAM_COMPAT_INSTALL_PATH=$game
mkdir -p -- "$root/logs"
exec >>"$root/logs/steam-launch-$(date +%Y%m%d-%H%M%S).log" 2>&1
printf 'game=%s\nintro=%s\n' "$game" "$mode"
cd -- "$game"
if [[ $mode == custom ]]; then exec "$root/Use-IntroCodec.sh" "$codec" "${args[@]}"; fi
exec "${args[@]}"
