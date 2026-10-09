#!/usr/bin/env bash
# Steam launch option: /absolute/Launch-Private.sh /absolute/private-root %command%
set -euo pipefail
fail() { printf '%s\n' "$*" >&2; exit 2; }
[[ $# -ge 2 ]] || fail 'Use Launch-Private.sh <private-root> <Steam command...>.'
root=$(realpath -e -- "$1") || fail 'The private root is absent.'
shift
game=$root/steamapps/common/BlackOps3
mode=${BO3_500K_MODE:-patch}
if [[ -z ${BO3_500K_MODE:-} && -f $root/mode ]]; then mode=$(cat -- "$root/mode"); fi
[[ $mode == patch || $mode == stock ]] || fail 'Private mode must be patch or stock.'
[[ -f $game/BlackOps3.exe && -d $game/players ]] || fail 'The private game or players directory is absent.'
if [[ $mode == patch ]]; then
    for name in BO3-500K-Zombies.exe Bo3EnhancedHelper.dll Bo3StartupGate.dll; do
        [[ -f $root/launcher/$name ]] || fail "The private launcher is missing $name."
    done
fi
args=()
matched=0
for arg in "$@"; do
    case $arg in
        */BlackOps3.exe)
            matched=$((matched + 1))
            if [[ $mode == patch ]]; then
                args+=("$root/launcher/BO3-500K-Zombies.exe" "Z:${game//\//\\}\\BlackOps3.exe")
            else
                args+=("$game/BlackOps3.exe")
            fi ;;
        *) args+=("$arg") ;;
    esac
done
[[ $matched == 1 ]] || fail 'Expected exactly one BlackOps3.exe in the Steam command.'
export STEAM_COMPAT_DATA_PATH=$root/compatdata
export STEAM_COMPAT_INSTALL_PATH=$game
if [[ -f $root/winedebug ]]; then export WINEDEBUG=$(cat -- "$root/winedebug"); fi
mkdir -p -- "$root/logs"
exec >>"$root/logs/steam-launch-$(date +%Y%m%d-%H%M%S)-$mode.log" 2>&1
printf 'mode=%s\ngame=%s\n' "$mode" "$game"
cd -- "$game"
exec "${args[@]}"
