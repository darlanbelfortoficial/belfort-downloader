#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ -d .venv ]]; then
  source .venv/bin/activate
else
  python3 -m venv .venv
  source .venv/bin/activate
fi

python -m pip install -U pip
python -m pip install -r requirements.txt

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "AVISO: FFmpeg não encontrado no sistema."
  echo "No Fedora/Bazzite, instale pelo sistema antes de baixar: sudo rpm-ostree install ffmpeg"
fi

if [[ -x "$HOME/.deno/bin/deno" ]]; then
  echo "Deno encontrado: $HOME/.deno/bin/deno"
elif command -v deno >/dev/null 2>&1; then
  echo "Deno encontrado: $(command -v deno)"
else
  echo "AVISO: Deno não encontrado. O yt-dlp pode ter menos formatos disponíveis."
fi

python - <<'PY'
import yt_dlp
print('yt-dlp:', yt_dlp.version.__version__)
try:
    import bgutil_ytdlp_pot_provider
    print('bgutil-ytdlp-pot-provider: instalado')
except Exception:
    print('bgutil-ytdlp-pot-provider: instalado como plugin (detecção pelo yt-dlp)')
PY

echo
echo "Instalação concluída."
echo "Execute: source .venv/bin/activate && python app.py"
echo "Abra: http://127.0.0.1:5000"
