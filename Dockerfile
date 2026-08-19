FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PORT=10000

# ============================================================
# DEPENDÊNCIAS DO SISTEMA
# ============================================================

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        ca-certificates \
        unzip \
        git && \
    rm -rf /var/lib/apt/lists/*

# ============================================================
# DENO
# ============================================================

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

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ============================================================
# BGUTIL - PO TOKEN PROVIDER
# ============================================================

WORKDIR /opt

RUN git clone \
    --single-branch \
    --branch 1.3.1 \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git

WORKDIR /opt/bgutil-ytdlp-pot-provider/server

# Instala as dependências do servidor usando Deno
RUN deno install \
    --allow-scripts=npm:canvas \
    --frozen

# ============================================================
# APLICAÇÃO
# ============================================================

WORKDIR /app

COPY . .

# ============================================================
# DIRETÓRIO DE DOWNLOADS
# ============================================================

RUN mkdir -p /app/downloads

# ============================================================
# PORTAS
# ============================================================

EXPOSE 10000
EXPOSE 4416

# ============================================================
# START
# ============================================================

CMD ["bash", "-c", "deno run --allow-env --allow-net --allow-ffi=/opt/bgutil-ytdlp-pot-provider/server/node_modules --allow-read=/opt/bgutil-ytdlp-pot-provider/server/node_modules /opt/bgutil-ytdlp-pot-provider/server/src/main.ts --host 127.0.0.1 --port 4416 & exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 900 app:app"]
