from flask import Flask, render_template, request, jsonify, send_file
import os
import shutil
import subprocess
import threading
import uuid
import base64
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import yt_dlp


# ============================================================
# FLASK
# ============================================================

app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates"
)

app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024


# ============================================================
# DIRETÓRIOS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DOWNLOAD_ROOT = Path(
    os.environ.get(
        "DOWNLOAD_DIR",
        "/tmp/belfort-downloader"
        if os.environ.get("RENDER")
        else str(BASE_DIR / "downloads")
    )
)

DOWNLOAD_ROOT.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# CONTROLE DOS DOWNLOADS
# ============================================================

jobs = {}
jobs_lock = threading.Lock()


# ============================================================
# CONFIGURAÇÕES
# ============================================================

VIDEO_QUALITIES = {
    "best",
    "2160",
    "1440",
    "1080",
    "720",
    "480",
    "360"
}

AUDIO_QUALITIES = {
    "320",
    "256",
    "192",
    "128"
}

BROWSERS = {
    "none",
    "chrome",
    "chromium",
    "firefox",
    "brave",
    "edge"
}


# ============================================================
# FUNÇÕES DE JOB
# ============================================================

def set_job(job_id, **values):
    with jobs_lock:
        jobs.setdefault(job_id, {}).update(values)


def get_job(job_id):
    with jobs_lock:
        return dict(jobs.get(job_id, {}))


# ============================================================
# LOCALIZA PROGRAMAS
# ============================================================

def find_program(name):

    found = shutil.which(name)

    if found:
        return found

    candidates = {

        "deno": [
            Path.home() / ".deno/bin/deno",
            Path("/usr/bin/deno"),
            Path("/usr/local/bin/deno"),
        ],

        "ffmpeg": [
            Path("/usr/bin/ffmpeg"),
            Path("/usr/local/bin/ffmpeg"),
            Path.home() / ".local/bin/ffmpeg",
        ],

        "kdialog": [
            Path("/usr/bin/kdialog")
        ],

        "zenity": [
            Path("/usr/bin/zenity")
        ],
    }

    for path in candidates.get(name, []):

        if path.exists() and os.access(path, os.X_OK):
            return str(path)

    return None


# ============================================================
# COOKIES DO YOUTUBE
# ============================================================

def prepare_cookies():

    """
    Permite fornecer cookies do YouTube pelo Render
    através da variável de ambiente:

        YOUTUBE_COOKIES

    A variável deve conter o conteúdo de um arquivo
    cookies.txt no formato Netscape.

    Também aceita:

        YOUTUBE_COOKIES_B64

    contendo o arquivo codificado em Base64.
    """

    cookies_path = Path("/tmp/youtube-cookies.txt")

    # --------------------------------------------------------
    # ARQUIVO JÁ EXISTENTE
    # --------------------------------------------------------

    if cookies_path.exists():

        return str(cookies_path)

    # --------------------------------------------------------
    # COOKIES EM TEXTO
    # --------------------------------------------------------

    cookies = os.environ.get(
        "YOUTUBE_COOKIES"
    )

    if cookies:

        cookies_path.write_text(
            cookies,
            encoding="utf-8"
        )

        return str(cookies_path)

    # --------------------------------------------------------
    # COOKIES EM BASE64
    # --------------------------------------------------------

    cookies_b64 = os.environ.get(
        "YOUTUBE_COOKIES_B64"
    )

    if cookies_b64:

        try:

            content = base64.b64decode(
                cookies_b64
            )

            cookies_path.write_bytes(
                content
            )

            return str(cookies_path)

        except Exception:

            return None

    return None


# ============================================================
# DESTINO
# ============================================================

def resolve_destination(value):

    # --------------------------------------------------------
    # RENDER
    # --------------------------------------------------------

    if os.environ.get("RENDER"):

        path = DOWNLOAD_ROOT / uuid.uuid4().hex

        path.mkdir(
            parents=True,
            exist_ok=True
        )

        return path.resolve()

    # --------------------------------------------------------
    # LOCAL
    # --------------------------------------------------------

    value = (value or "").strip()

    if not value:

        raise ValueError(
            "Escolha uma pasta de destino."
        )

    path = Path(
        os.path.expandvars(
            os.path.expanduser(value)
        )
    )

    if not path.is_absolute():

        path = DOWNLOAD_ROOT / path

    path.mkdir(
        parents=True,
        exist_ok=True
    )

    return path.resolve()


# ============================================================
# SELETOR DE PASTA LOCAL
# ============================================================

def choose_folder_native(initial=""):

    initial = (
        str(Path(initial).expanduser())
        if initial
        else str(Path.home())
    )

    # --------------------------------------------------------
    # KDE
    # --------------------------------------------------------

    kdialog = find_program("kdialog")

    if kdialog:

        try:

            result = subprocess.run(
                [
                    kdialog,
                    "--getexistingdirectory",
                    initial,
                    "Escolha a pasta de destino"
                ],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:

                selected = result.stdout.strip()

                if selected:
                    return selected

        except Exception:
            pass

    # --------------------------------------------------------
    # ZENITY
    # --------------------------------------------------------

    zenity = find_program("zenity")

    if zenity:

        try:

            result = subprocess.run(
                [
                    zenity,
                    "--file-selection",
                    "--directory",
                    "--title=Escolha a pasta de destino"
                ],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:

                selected = result.stdout.strip()

                if selected:
                    return selected

        except Exception:
            pass

    # --------------------------------------------------------
    # TKINTER
    # --------------------------------------------------------

    try:

        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()

        root.withdraw()

        root.attributes(
            "-topmost",
            True
        )

        selected = filedialog.askdirectory(
            initialdir=initial,
            title="Escolha a pasta de destino"
        )

        root.destroy()

        return selected or None

    except Exception:

        return None


# ============================================================
# PROGRESSO
# ============================================================

def progress_hook(job_id):

    def hook(data):

        status = data.get("status")

        if status == "downloading":

            total = (
                data.get("total_bytes")
                or data.get("total_bytes_estimate")
                or 0
            )

            done = data.get(
                "downloaded_bytes",
                0
            )

            percent = (
                done / total * 100
                if total
                else 0
            )

            speed = data.get("speed")

            eta = data.get("eta")

            filename = os.path.basename(
                data.get(
                    "filename",
                    ""
                )
            )

            set_job(

                job_id,

                status="downloading",

                percent=round(
                    percent,
                    1
                ),

                speed=(
                    yt_dlp.utils.format_bytes(speed)
                    + "/s"
                    if speed
                    else "--"
                ),

                eta=(
                    f"{eta}s"
                    if eta is not None
                    else "--"
                ),

                filename=filename
            )

        elif status == "finished":

            filename = os.path.basename(
                data.get(
                    "filename",
                    ""
                )
            )

            set_job(

                job_id,

                status="processing",

                percent=100,

                speed="--",

                eta="--",

                filename=filename,

                message=(
                    "Download recebido. "
                    "Finalizando arquivo..."
                )
            )

    return hook


# ============================================================
# SELETOR DE FORMATO
# ============================================================

def format_selector(media, quality):

    if media == "audio":

        return "bestaudio/best"

    if quality == "best":

        return (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[ext=mp4]+bestaudio/"
            "bestvideo+bestaudio/"
            "best"
        )

    height = int(quality)

    return (
        f"bestvideo[ext=mp4][height<={height}]+"
        f"bestaudio[ext=m4a]/"

        f"bestvideo[ext=mp4][height<={height}]+"
        f"bestaudio/"

        f"bestvideo[height<={height}]+"
        f"bestaudio/"

        f"best[ext=mp4][height<={height}]/"

        f"best[height<={height}]/"

        "best"
    )


# ============================================================
# NORMALIZA URL
# ============================================================

def normalize_url(url, mode):

    url = (url or "").strip()

    if mode != "single":
        return url

    parsed = urlparse(url)

    query = parse_qs(
        parsed.query,
        keep_blank_values=True
    )

    if "v" in query and query["v"]:

        video_id = query["v"][0]

        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                urlencode(
                    {"v": video_id}
                ),
                ""
            )
        )

    if (
        "youtu.be" in parsed.netloc
        and parsed.path.strip("/")
    ):

        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                "",
                ""
            )
        )

    if (
        "list" in query
        and "v" not in query
    ):

        raise ValueError(
            "Você escolheu 'Somente este vídeo', "
            "mas a URL não identifica um vídeo. "
            "Envie o link direto do vídeo."
        )

    return url


# ============================================================
# CLIENTES YOUTUBE
# ============================================================

def client_plan(browser):

    """
    Ordem pensada para execução no servidor.

    Clientes como tv e android_vr não dependem
    de cookies do navegador local.

    web_embedded é usado como alternativa para
    vídeos que permitem reprodução incorporada.
    """

    return [
        "tv",
        "android_vr",
        "web_embedded"
    ]


# ============================================================
# OPÇÕES DO YT-DLP
# ============================================================

def build_options(
    job_id,
    media,
    quality,
    destination,
    browser="none",
    client=None,
    playlist=False
):

    options = {

        "outtmpl": str(
            destination
            / "%(title).180B [%(id)s].%(ext)s"
        ),

        "noplaylist": not playlist,

        "progress_hooks": [
            progress_hook(job_id)
        ],

        "quiet": True,

        "no_warnings": False,

        "retries": 3,

        "fragment_retries": 3,

        "file_access_retries": 3,

        "extractor_retries": 3,

        "continuedl": True,

        "overwrites": False,

        "ignoreerrors": False,

        "windowsfilenames": False,

        "restrictfilenames": False,

        "socket_timeout": 30,

        "concurrent_fragment_downloads": 1,

        "sleep_interval_requests": 1,

        "max_sleep_interval_requests": 3,

        "sleep_interval": 1,

        "max_sleep_interval": 3,

        "format": format_selector(
            media,
            quality
        ),

        "http_headers": {

            "User-Agent": (
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/151.0.0.0 "
                "Safari/537.36"
            ),

            "Accept-Language":
                "pt-BR,pt;q=0.9,en;q=0.8"
        }
    }

    # ========================================================
    # DENO / EJS
    # ========================================================

    deno = find_program("deno")

    if deno:

        options["js_runtimes"] = {
            "deno": {
                "path": deno
            }
        }

    # ========================================================
    # FFMPEG
    # ========================================================

    ffmpeg = find_program("ffmpeg")

    if ffmpeg:

        options["ffmpeg_location"] = str(
            Path(ffmpeg).parent
        )

    # ========================================================
    # CLIENTE YOUTUBE
    # ========================================================

    if client:

        options["extractor_args"] = {

            "youtube": {

                "player_client": [
                    client
                ]
            }
        }

    # ========================================================
    # COOKIES
    # ========================================================

    cookies_file = prepare_cookies()

    if cookies_file:

        options["cookiefile"] = cookies_file

    # ========================================================
    # COOKIES DO NAVEGADOR - SOMENTE LOCAL
    # ========================================================

    if (
        browser != "none"
        and not os.environ.get("RENDER")
    ):

        options["cookiesfrombrowser"] = (
            browser,
        )

    # ========================================================
    # ÁUDIO
    # ========================================================

    if media == "audio":

        options["postprocessors"] = [

            {
                "key":
                    "FFmpegExtractAudio",

                "preferredcodec":
                    "mp3",

                "preferredquality":
                    quality
            }

        ]

        options["addmetadata"] = True

    # ========================================================
    # VÍDEO
    # ========================================================

    else:

        options["merge_output_format"] = "mp4"

        options["postprocessor_args"] = {

            "Merger": [

                "-movflags",
                "+faststart"
            ]
        }

    return options


# ============================================================
# WORKER
# ============================================================

def worker(
    job_id,
    url,
    mode,
    media,
    quality,
    destination,
    browser
):

    try:

        deno = find_program("deno")

        ffmpeg = find_program("ffmpeg")

        cookies = prepare_cookies()

        set_job(

            job_id,

            status="starting",

            percent=0,

            speed="--",

            eta="--",

            message="Preparando download...",

            deno=bool(deno),

            ffmpeg=bool(ffmpeg),

            cookies=bool(cookies),

            yt_dlp=yt_dlp.version.__version__,

            browser=browser
        )

        # ----------------------------------------------------
        # FFMPEG
        # ----------------------------------------------------

        if not ffmpeg:

            raise RuntimeError(
                "FFmpeg não foi encontrado no servidor."
            )

        # ----------------------------------------------------
        # URL
        # ----------------------------------------------------

        clean_url = normalize_url(
            url,
            mode
        )

        # ----------------------------------------------------
        # CLIENTES
        # ----------------------------------------------------

        plans = client_plan(
            browser
        )

        errors = []

        # ----------------------------------------------------
        # TENTATIVAS
        # ----------------------------------------------------

        for index, client in enumerate(
            plans,
            start=1
        ):

            set_job(

                job_id,

                status="starting",

                percent=0,

                message=(
                    f"Tentativa {index}/"
                    f"{len(plans)} — "
                    f"cliente YouTube: {client} — "
                    f"qualidade: {quality}"
                )
            )

            try:

                options = build_options(

                    job_id,

                    media,

                    quality,

                    destination,

                    browser,

                    client,

                    playlist=(
                        mode == "playlist"
                    )
                )

                with yt_dlp.YoutubeDL(
                    options
                ) as ydl:

                    result = ydl.download(
                        [clean_url]
                    )

                # ------------------------------------------------
                # RESULTADO
                # ------------------------------------------------

                if result in (None, 0):

                    files = [

                        path

                        for path
                        in destination.iterdir()

                        if (
                            path.is_file()
                            and not path.name.endswith(
                                (
                                    ".part",
                                    ".ytdl"
                                )
                            )
                        )
                    ]

                    if not files:

                        raise RuntimeError(
                            "O download terminou, "
                            "mas o arquivo final "
                            "não foi encontrado."
                        )

                    final_file = max(

                        files,

                        key=lambda path:
                            path.stat().st_mtime
                    )

                    set_job(

                        job_id,

                        status="completed",

                        percent=100,

                        speed="--",

                        eta="0s",

                        filename=final_file.name,

                        file_path=str(
                            final_file
                        ),

                        message="Download concluído!",

                        client=client
                    )

                    return

                errors.append(
                    f"{client}: código {result}"
                )

            except Exception as exc:

                errors.append(
                    f"{client}: {str(exc)}"
                )

                continue

        # ========================================================
        # ERRO FINAL
        # ========================================================

        detail = (

            errors[-1]

            if errors

            else
            "Nenhuma estratégia conseguiu "
            "concluir o download."
        )

        detail_lower = detail.lower()

        if (
            "429" in detail
            or
            "too many requests" in detail_lower
        ):

            detail = (

                "O YouTube limitou temporariamente "
                "as requisições deste servidor (HTTP 429). "
                "O Render está sendo identificado como "
                "tráfego automatizado. "
                "Se o problema persistir, configure "
                "YOUTUBE_COOKIES ou YOUTUBE_COOKIES_B64 "
                "nas variáveis de ambiente do serviço."
            )

        elif (
            "sign in to confirm" in detail_lower
            or
            "not a bot" in detail_lower
        ):

            detail = (

                "O YouTube solicitou autenticação "
                "ou verificação anti-bot. "
                "Configure os cookies do YouTube "
                "no ambiente do Render."
            )

        elif "403" in detail:

            detail = (

                "O YouTube recusou o arquivo "
                "com HTTP 403. "
                "O aplicativo tentou clientes "
                "alternativos."
            )

        elif (
            "cookies" in detail_lower
            and browser != "none"
        ):

            detail = (

                "Não foi possível ler os cookies "
                "do navegador local."
            )

        set_job(

            job_id,

            status="error",

            percent=0,

            speed="--",

            eta="--",

            error=detail
        )

    except Exception as exc:

        set_job(

            job_id,

            status="error",

            percent=0,

            speed="--",

            eta="--",

            error=str(exc)
        )


# ============================================================
# PÁGINA PRINCIPAL
# ============================================================

@app.get("/")
def index():

    return render_template(
        "index.html"
    )


# ============================================================
# PASTA PADRÃO
# ============================================================

@app.get("/api/default-folder")
def default_folder():

    if os.environ.get("RENDER"):

        return jsonify(

            video="/tmp/Belfort Downloader",

            audio="/tmp/Belfort Downloader"

        )

    return jsonify(

        video=str(
            Path.home()
            / "Vídeos"
            / "Belfort Downloader"
        ),

        audio=str(
            Path.home()
            / "Músicas"
            / "Belfort Downloader"
        )
    )


# ============================================================
# ESCOLHER PASTA
# ============================================================

@app.post("/api/choose-folder")
def choose_folder():

    if os.environ.get("RENDER"):

        return jsonify(

            error=(
                "O seletor de pastas funciona "
                "somente na versão local. "
                "No Render, o arquivo será preparado "
                "temporariamente no servidor."
            )

        ), 400

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    initial = (
        data.get("initial")
        or str(Path.home())
    )

    selected = choose_folder_native(
        initial
    )

    if not selected:

        return jsonify(

            error=(
                "Nenhuma pasta foi escolhida."
            )

        ), 400

    return jsonify(

        path=str(
            Path(selected)
            .expanduser()
            .resolve()
        )
    )


# ============================================================
# INICIAR DOWNLOAD
# ============================================================

@app.post("/api/download")
def start_download():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    url = (
        data.get("url")
        or ""
    ).strip()

    mode = data.get(
        "mode",
        "single"
    )

    media = data.get(
        "media",
        "video"
    )

    quality = str(
        data.get(
            "quality",
            "best"
        )
    )

    destination = (
        data.get("destination")
        or ""
    ).strip()

    browser = str(
        data.get(
            "browser",
            "none"
        )
    ).lower()

    # --------------------------------------------------------
    # VALIDAÇÕES
    # --------------------------------------------------------

    if not url:

        return jsonify(
            error="Cole uma URL do YouTube."
        ), 400

    if mode not in {
        "single",
        "playlist"
    }:

        return jsonify(
            error="Tipo de conteúdo inválido."
        ), 400

    if media not in {
        "video",
        "audio"
    }:

        return jsonify(
            error="Formato inválido."
        ), 400

    if (
        media == "video"
        and quality not in VIDEO_QUALITIES
    ):

        return jsonify(
            error="Qualidade de vídeo inválida."
        ), 400

    if (
        media == "audio"
        and quality not in AUDIO_QUALITIES
    ):

        return jsonify(
            error="Qualidade de áudio inválida."
        ), 400

    if browser not in BROWSERS:

        return jsonify(
            error="Navegador inválido."
        ), 400

    # --------------------------------------------------------
    # RENDER
    # --------------------------------------------------------

    if os.environ.get("RENDER"):

        browser = "none"

    # --------------------------------------------------------
    # DESTINO
    # --------------------------------------------------------

    try:

        destination_path = resolve_destination(
            destination
        )

    except Exception as exc:

        return jsonify(
            error=f"Destino inválido: {exc}"
        ), 400

    # --------------------------------------------------------
    # JOB
    # --------------------------------------------------------

    job_id = uuid.uuid4().hex

    set_job(

        job_id,

        status="queued",

        percent=0,

        speed="--",

        eta="--",

        filename="",

        destination=str(
            destination_path
        ),

        error=None
    )

    # --------------------------------------------------------
    # THREAD
    # --------------------------------------------------------

    threading.Thread(

        target=worker,

        args=(

            job_id,
            url,
            mode,
            media,
            quality,
            destination_path,
            browser

        ),

        daemon=True

    ).start()

    return jsonify(
        job_id=job_id
    )


# ============================================================
# PROGRESSO
# ============================================================

@app.get("/api/progress/<job_id>")
def progress(job_id):

    job = get_job(
        job_id
    )

    if job:

        return jsonify(
            job
        )

    return jsonify(
        error="Download não encontrado."
    ), 404


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/api/health")
def health():

    deno = find_program(
        "deno"
    )

    ffmpeg = find_program(
        "ffmpeg"
    )

    cookies = prepare_cookies()

    return jsonify(

        ok=True,

        service="Belfort Downloader",

        yt_dlp=(
            yt_dlp.version.__version__
        ),

        deno=deno,

        ffmpeg=ffmpeg,

        cookies=bool(cookies),

        deno_ok=bool(deno),

        ffmpeg_ok=bool(ffmpeg),

        render=bool(
            os.environ.get("RENDER")
        )
    )


# ============================================================
# ENTREGAR ARQUIVO
# ============================================================

@app.get("/api/download-file/<job_id>")
def download_file(job_id):

    job = get_job(
        job_id
    )

    if not job:

        return jsonify(
            error="Download não encontrado."
        ), 404

    if job.get("status") != "completed":

        return jsonify(
            error="O download ainda não terminou."
        ), 400

    file_path = job.get(
        "file_path"
    )

    if not file_path:

        return jsonify(
            error="Arquivo final não encontrado."
        ), 404

    path = Path(
        file_path
    )

    if (
        not path.exists()
        or not path.is_file()
    ):

        return jsonify(
            error="O arquivo não está mais disponível."
        ), 404

    return send_file(

        path,

        as_attachment=True,

        download_name=path.name
    )


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    print()
    print("=" * 60)
    print("                 BELFORT DOWNLOADER")
    print("=" * 60)

    print(
        "yt-dlp :",
        yt_dlp.version.__version__
    )

    print(
        "Deno   :",
        find_program("deno")
        or "NÃO ENCONTRADO"
    )

    print(
        "FFmpeg :",
        find_program("ffmpeg")
        or "NÃO ENCONTRADO"
    )

    print(
        "Cookies:",
        "CONFIGURADOS"
        if prepare_cookies()
        else "NÃO CONFIGURADOS"
    )

    print(
        "Porta  :",
        port
    )

    print("=" * 60)
    print()

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        threaded=True
    )