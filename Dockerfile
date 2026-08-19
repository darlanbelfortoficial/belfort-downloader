FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PORT=10000

# ============================================================

# DEPENDÊNCIAS DO SISTEMA

# ============================================================

RUN apt-get update && 
apt-get install -y --no-install-recommends 
ffmpeg 
curl 
ca-certificates 
unzip 
&& rm -rf /var/lib/apt/lists/*

# ============================================================

# DENO

# ============================================================

# O Deno é utilizado pelo yt-dlp para executar JavaScript

# necessário aos extractors do YouTube.

RUN curl -fsSL https://deno.land/install.sh | sh

ENV DENO_DIR=/root/.cache/deno
ENV PATH="/root/.deno/bin:${PATH}"

# ============================================================

# DIRETÓRIO DA APLICAÇÃO

# ============================================================

WORKDIR /app

# ============================================================

# DEPENDÊNCIAS PYTHON

# ============================================================

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && 
pip install --no-cache-dir -r requirements.txt

# ============================================================

# CÓDIGO DA APLICAÇÃO

# ============================================================

COPY . .

# ============================================================

# DIRETÓRIO DE DOWNLOADS

# ============================================================

RUN mkdir -p /app/downloads

# ============================================================

# PORTA

# ============================================================

EXPOSE 10000

# ============================================================

# GUNICORN

# ============================================================

CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "1", "--threads", "4", "--timeout", "900", "app:app"]
