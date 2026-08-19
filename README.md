# BELFORT DOWNLOADER

Aplicativo local em Flask para baixar vídeos/áudio do YouTube com:

- Vídeo MP4 e áudio MP3.
- Qualidade de vídeo: melhor, 4K, 2K, 1080p, 720p, 480p e 360p, quando disponível.
- Qualidade de áudio: 320/256/192/128 kbps.
- Escolha de pasta por seletor nativo do Linux (KDialog/Zenity/Tkinter).
- Pastas padrão separadas para Vídeos e Músicas.
- Modo **Somente este vídeo**, que remove parâmetros `list`/`mix` do link e força `noplaylist=True`.
- Modo playlist separado.
- Deno detectado automaticamente em `~/.deno/bin/deno`.
- FFmpeg detectado automaticamente.
- Tentativas com clientes YouTube alternativos para reduzir falhas 403.
- Opção de ler cookies do navegador localmente, sem enviá-los ao aplicativo.
- Favicon e interface responsiva.

## Instalação no Fedora/Bazzite

1. Instale FFmpeg pelo sistema se ainda não tiver:

```bash
sudo rpm-ostree install ffmpeg
```

Reinicie se o sistema solicitar.

2. Entre na pasta do projeto e rode:

```bash
chmod +x setup.sh
./setup.sh
```

3. Ative o ambiente:

```bash
source .venv/bin/activate
```

4. Inicie:

```bash
python app.py
```

5. Abra no navegador:

```text
http://127.0.0.1:5000
```

## Sobre HTTP 403 do YouTube

O YouTube passou a exigir Proof-of-Origin Tokens (PO Tokens) para alguns clientes/formas de entrega. Por isso, um 403 pode ocorrer mesmo com Deno e yt-dlp instalados corretamente.

O projeto inclui o pacote `bgutil-ytdlp-pot-provider` como suporte opcional. O provider pode exigir uma instalação/serviço externo adicional dependendo do método escolhido. O BELFORT também tenta clientes alternativos antes de apresentar o erro.

O aplicativo **não promete que todo vídeo estará baixável**: disponibilidade, região, login, idade, direitos do conteúdo e mudanças do YouTube podem impedir um download.

## Cookies

A opção de sessão do navegador faz o `yt-dlp` ler cookies localmente. Não coloque arquivos de cookies no projeto, no ZIP ou em repositórios.

Se a leitura falhar, feche o navegador e tente novamente. Use cookies somente quando necessário.
