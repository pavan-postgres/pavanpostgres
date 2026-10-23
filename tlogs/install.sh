#!/usr/bin/env bash
# install.sh - installs tlogs for the current user (no sudo needed).
#   bash install.sh            -> ~/.local/bin/tlogs
#   PREFIX=/usr/local bash install.sh   (needs write access there)
# Never overwrites silently: an existing different tlogs is kept as tlogs.bak.<timestamp>.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
src="$here/tlogs"
[ -f "$src" ] || { echo "run this from the tlogs folder (tlogs script not found next to install.sh)"; exit 1; }
bin="${PREFIX:-$HOME/.local}/bin"
mkdir -p "$bin"
if [ -e "$bin/tlogs" ] && ! cmp -s "$src" "$bin/tlogs"; then
  bak="$bin/tlogs.bak.$(date +%Y%m%d%H%M%S)"; cp -p "$bin/tlogs" "$bak"; echo "kept previous version: $bak"
fi
cp "$src" "$bin/tlogs.new" && chmod 755 "$bin/tlogs.new" && mv "$bin/tlogs.new" "$bin/tlogs"
echo "installed: $bin/tlogs ($("$bin/tlogs" version))"
# checks, no changes
command -v tmux >/dev/null 2>&1 && echo "tmux: $(tmux -V)" || echo "tmux: NOT FOUND - install it (see README: Install tmux)"
case ":$PATH:" in *":$bin:"*) ;; *) echo "note: $bin is not on your PATH. Add this to ~/.bashrc or ~/.zshrc:"; echo "  export PATH=\"$bin:\$PATH\"" ;; esac
"$bin/tlogs" init
echo "done. try: cd /path/to/logs && tlogs -l"
