from flask import Flask, render_template, request, jsonify
import os
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import yt_dlp

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_ROOT = BASE_DIR / "downloads"
DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)

jobs = {}
jobs_lock = threading.Lock()

VIDEO_QUALITIES = {"best", "2160", "1440", "1080", "720", "480", "360"}
AUDIO_QUALITIES = {"320", "256", "192", "128"}
BROWSERS = {"none", "chrome", "chromium", "firefox", "brave", "edge"}


def set_job(job_id, **values):
    with jobs_lock:
        jobs.setdefault(job_id, {}).update(values)


def get_job(job_id):
    with jobs_lock:
        return dict(jobs.get(job_id, {}))


def find_program(name):
    found = shutil.which(name)
    if found:
        return found

    candidates = {
        "deno": [Path.home() / ".deno/bin/deno", Path("/usr/bin/deno"), Path("/usr/local/bin/deno")],
        "ffmpeg": [Path("/usr/bin/ffmpeg"), Path("/usr/local/bin/ffmpeg"), Path.home() / ".local/bin/ffmpeg"],
        "kdialog": [Path("/usr/bin/kdialog")],
        "zenity": [Path("/usr/bin/zenity")],
    }
    for path in candidates.get(name, []):
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
    return None


def resolve_destination(value):
    """
    Define onde os arquivos serão salvos.

    No Render:
    - Cada usuário usa uma pasta temporária própria.
    - O usuário NÃO pode escolher uma pasta do computador dele.
    - O arquivo será disponibilizado para download pelo navegador.

    Localmente:
    - Continua permitindo escolher uma pasta normalmente.
    """

    # Render = ambiente hospedado
    if os.environ.get("RENDER"):
        path = DOWNLOAD_ROOT / uuid.uuid4().hex
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    # Execução local
    value = (value or "").strip()

    if not value:
        raise ValueError("Escolha uma pasta de destino.")

    path = Path(
        os.path.expandvars(
            os.path.expanduser(value)
        )
    )

    if not path.is_absolute():
        path = DOWNLOAD_ROOT / path

    path.mkdir(parents=True, exist_ok=True)

    return path.resolve()

def choose_folder_native(initial=""):
    """Abre um seletor de pasta no Linux. Não usa upload de arquivos pelo navegador."""
    initial = str(Path(initial).expanduser()) if initial else str(Path.home())

    # KDE: melhor integração no Bazzite/KDE.
    kdialog = find_program("kdialog")
    if kdialog:
        try:
            result = subprocess.run(
                [kdialog, "--getexistingdirectory", initial, "Escolha a pasta de destino"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            return None
        except Exception:
            pass

    # GNOME/GTK e outras instalações.
    zenity = find_program("zenity")
    if zenity:
        try:
            result = subprocess.run(
                [zenity, "--file-selection", "--directory", "--title=Escolha a pasta de destino"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            return None
        except Exception:
            pass

    # Último recurso: Tkinter.
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(initialdir=initial, title="Escolha a pasta de destino")
        root.destroy()
        return selected or None
    except Exception:
        return None


def progress_hook(job_id):
    def hook(data):
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            done = data.get("downloaded_bytes", 0)
            percent = (done / total * 100) if total else 0
            speed = data.get("speed")
            eta = data.get("eta")
            set_job(
                job_id,
                status="downloading",
                percent=round(percent, 1),
                speed=yt_dlp.utils.format_bytes(speed) + "/s" if speed else "--",
                eta=f"{eta}s" if eta is not None else "--",
                filename=os.path.basename(data.get("filename", "")),
            )
        elif status == "finished":
            set_job(
                job_id,
                status="processing",
                percent=100,
                speed="--",
                eta="--",
                filename=os.path.basename(data.get("filename", "")),
                message="Download recebido. Finalizando arquivo...",
            )

    return hook


def format_selector(media, quality):
    """
    Monta o seletor de formatos respeitando a qualidade escolhida.

    Para vídeo, prioriza vídeo separado + áudio separado, permitindo
    que o yt-dlp escolha a maior resolução disponível até o limite pedido.
    """
    if media == "audio":
        return "bestaudio/best"

    if quality == "best":
        return (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[ext=mp4]+bestaudio/"
            "bestvideo+bestaudio/"
            "best"
        )

    h = int(quality)

    # Ex.: 1080 -> escolhe a melhor disponível até 1080p.
    # 720 -> até 720p, 480 -> até 480p, etc.
    return (
        f"bestvideo[ext=mp4][height<={h}]+bestaudio[ext=m4a]/"
        f"bestvideo[ext=mp4][height<={h}]+bestaudio/"
        f"bestvideo[height<={h}]+bestaudio/"
        f"best[ext=mp4][height<={h}]/"
        f"best[height<={h}]/"
        "best"
    )


def normalize_url(url, mode):
    """Remove list/mix/radio quando o usuário pediu somente o vídeo."""
    url = (url or "").strip()
    if mode != "single":
        return url

    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)

    if "v" in query and query["v"]:
        video_id = query["v"][0]
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params,
                           urlencode({"v": video_id}), ""))

    if "youtu.be" in parsed.netloc and parsed.path.strip("/"):
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, "", ""))

    if "list" in query and "v" not in query:
        raise ValueError(
            "Você escolheu 'Somente este vídeo', mas a URL não identifica um vídeo. "
            "Envie o link direto do vídeo."
        )

    return url


def build_options(job_id, media, quality, destination, browser="none", client=None):
    options = {
        "outtmpl": str(destination / "%(title).180B [%(id)s].%(ext)s"),
        "noplaylist": True,
        "progress_hooks": [progress_hook(job_id)],
        "quiet": True,
        "no_warnings": False,
        "retries": 3,
        "fragment_retries": 3,
        "file_access_retries": 3,
        "extractor_retries": 2,
        "continuedl": True,
        "overwrites": False,
        "ignoreerrors": False,
        "windowsfilenames": False,
        "restrictfilenames": False,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 1,
        "format": format_selector(media, quality),
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "Chrome/151.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        },
    }

    deno = find_program("deno")
    ffmpeg = find_program("ffmpeg")
    if deno:
        # yt-dlp API espera um dicionário: {runtime: {config}}.
        options["js_runtimes"] = {"deno": {"path": deno}}
    if ffmpeg:
        options["ffmpeg_location"] = str(Path(ffmpeg).parent)

    if client:
        options["extractor_args"] = {"youtube": {"player_client": [client]}}

    if browser != "none":
        # Cookies ficam somente no computador do usuário; não são enviados ao BELFORT.
        options["cookiesfrombrowser"] = (browser,)

    if media == "audio":
        options["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": quality,
        }]
        options["addmetadata"] = True
    else:
        options["merge_output_format"] = "mp4"
        options["postprocessor_args"] = {"Merger": ["-movflags", "+faststart"]}

    return options


def client_plan(browser):
    """Estratégia conservadora para o estado atual do YouTube.

    A ordem evita depender exclusivamente do android_vr, que pode gerar URLs 403.
    Se o usuário optou por cookies, testamos primeiro clientes que podem aproveitar a sessão.
    """
    if browser != "none":
        return ["tv", "web_embedded", "android_vr"]
    return ["web_embedded", "tv", "android_vr"]


def worker(job_id, url, mode, media, quality, destination, browser):
    try:
        deno, ffmpeg = find_program("deno"), find_program("ffmpeg")
        set_job(
            job_id,
            status="starting", percent=0, speed="--", eta="--",
            message="Preparando download...", deno=bool(deno), ffmpeg=bool(ffmpeg),
            yt_dlp=yt_dlp.version.__version__, browser=browser,
        )

        if not ffmpeg:
            raise RuntimeError("FFmpeg não foi encontrado. Instale FFmpeg e tente novamente.")

        clean_url = normalize_url(url, mode)
        plans = client_plan(browser)
        errors = []

        for index, client in enumerate(plans, start=1):
            set_job(
                job_id,
                status="starting",
                percent=0,
                message=(
                    f"Tentativa {index}/{len(plans)} — cliente YouTube: {client} "
                    f"— qualidade: {quality}{' (áudio)' if media == 'audio' else 'p'}"
                ),
            )
            try:
                opts = build_options(job_id, media, quality, destination, browser, client)
                with yt_dlp.YoutubeDL(opts) as ydl:
                    result = ydl.download([clean_url])

                if result in (None, 0):
                    set_job(
                        job_id,
                        status="completed", percent=100, speed="--", eta="0s",
                        message=f"Download concluído. Arquivos salvos em: {destination}",
                        client=client,
                    )
                    return
                errors.append(f"{client}: código {result}")
            except Exception as exc:
                text = str(exc)
                errors.append(f"{client}: {text}")
                # Tentamos outro cliente apenas para erros de extração/download.
                continue

        detail = errors[-1] if errors else "Nenhuma estratégia conseguiu concluir o download."
        if "403" in detail:
            detail = (
                "O YouTube recusou o arquivo com HTTP 403. "
                "O aplicativo tentou clientes alternativos. "
                "Se continuar, ative 'Usar sessão do navegador' e escolha o navegador aberto no YouTube."
            )
        elif "cookies" in detail.lower() and browser != "none":
            detail = (
                "Não foi possível ler os cookies do navegador. "
                "Feche o navegador e tente novamente, ou desative a opção de sessão."
            )
        set_job(job_id, status="error", percent=0, speed="--", eta="--", error=detail)

    except Exception as exc:
        set_job(job_id, status="error", percent=0, speed="--", eta="--", error=str(exc))


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/default-folder")
def default_folder():
    return jsonify(
        video=str(Path.home() / "Vídeos" / "Belfort Downloader"),
        audio=str(Path.home() / "Músicas" / "Belfort Downloader"),
    )


@app.post("/api/choose-folder")
def choose_folder():
    data = request.get_json(silent=True) or {}
    initial = data.get("initial") or str(Path.home())
    selected = choose_folder_native(initial)
    if not selected:
        return jsonify(error=(
            "Nenhuma pasta foi escolhida. Se o seletor não abrir, instale kdialog ou zenity."
        )), 400
    return jsonify(path=str(Path(selected).expanduser().resolve()))


@app.post("/api/download")
def start_download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    mode = data.get("mode", "single")
    media = data.get("media", "video")
    quality = str(data.get("quality", "best"))
    destination = (data.get("destination") or "").strip()
    browser = str(data.get("browser", "none")).lower()

    if not url:
        return jsonify(error="Cole uma URL do YouTube."), 400
    if mode not in {"single", "playlist"}:
        return jsonify(error="Tipo de conteúdo inválido."), 400
    if media not in {"video", "audio"}:
        return jsonify(error="Formato inválido."), 400
    if media == "video" and quality not in VIDEO_QUALITIES:
        return jsonify(error="Qualidade de vídeo inválida."), 400
    if media == "audio" and quality not in AUDIO_QUALITIES:
        return jsonify(error="Qualidade de áudio inválida."), 400
    if browser not in BROWSERS:
        return jsonify(error="Navegador inválido."), 400

    try:
        destination_path = resolve_destination(destination)
    except Exception as exc:
        return jsonify(error=f"Destino inválido: {exc}"), 400

    job_id = uuid.uuid4().hex
    set_job(
        job_id, status="queued", percent=0, speed="--", eta="--", filename="",
        destination=str(destination_path), error=None,
    )
    threading.Thread(
        target=worker,
        args=(job_id, url, mode, media, quality, destination_path, browser),
        daemon=True,
    ).start()
    return jsonify(job_id=job_id)


@app.get("/api/progress/<job_id>")
def progress(job_id):
    job = get_job(job_id)
    return jsonify(job) if job else (jsonify(error="Download não encontrado."), 404)


@app.get("/api/health")
def health():
    deno, ffmpeg = find_program("deno"), find_program("ffmpeg")
    return jsonify(
        ok=True,
        yt_dlp=yt_dlp.version.__version__,
        deno=deno,
        ffmpeg=ffmpeg,
        deno_ok=bool(deno),
        ffmpeg_ok=bool(ffmpeg),
    )


if __name__ == "__main__":
    print("\n" + "=" * 58)
    print("                 BELFORT DOWNLOADER")
    print("=" * 58)
    print("yt-dlp :", yt_dlp.version.__version__)
    print("Deno   :", find_program("deno") or "NÃO ENCONTRADO")
    print("FFmpeg :", find_program("ffmpeg") or "NÃO ENCONTRADO")
    print("KDialog:", find_program("kdialog") or "não encontrado")
    print("Zenity :", find_program("zenity") or "não encontrado")
    print("=" * 58 + "\n")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
