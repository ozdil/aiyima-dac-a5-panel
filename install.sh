#!/usr/bin/env bash
# Kullanıcı dizinine kurar (sudo gerekmez). Kaldırmak için: ./install.sh --uninstall
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
bin="$HOME/.local/bin/aiyima-dac-panel"
desk="$HOME/.local/share/applications/dev.ozdil.AiyimaDacPanel.desktop"
if [[ "${1:-}" == "--uninstall" ]]; then
  rm -f "$bin" "$desk"
  echo "Kaldırıldı."
  exit 0
fi
mkdir -p "$(dirname "$bin")" "$(dirname "$desk")"
ln -sf "$here/bin/aiyima-dac-panel" "$bin"
cp "$here/dev.ozdil.AiyimaDacPanel.desktop" "$desk"
command -v update-desktop-database >/dev/null && update-desktop-database "$(dirname "$desk")" || true
echo "Kuruldu: $bin"
