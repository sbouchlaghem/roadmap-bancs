#!/usr/bin/env bash
# Lance l'application depuis les sources :  ./lancer.sh  [--port 9000]  [--sans-navigateur]
# Mêmes données que la version installée (~/.local/share/roadmap-bancs) ; autre dossier : ROADMAP_DATA=/chemin ./lancer.sh
set -euo pipefail
cd "$(dirname "$0")"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null || { echo "Python 3.10 ou plus requis"; exit 1; }
export ROADMAP_DATA="${ROADMAP_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/roadmap-bancs}"
exec python3 main.py "$@"
