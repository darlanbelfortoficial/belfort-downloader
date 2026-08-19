javascript
const $ = (id) => document.getElementById(id);

const VIDEO = [
  ["best", "Melhor disponível"],
  ["2160", "2160p (4K)"],
  ["1440", "1440p (2K)"],
  ["1080", "1080p (Full HD)"],
  ["720", "720p (HD)"],
  ["480", "480p"],
  ["360", "360p"]
];

const AUDIO = [
  ["320", "320 kbps"],
  ["256", "256 kbps"],
  ["192", "192 kbps"],
  ["128", "128 kbps"]
];

let currentJobId = null;
let pollTimer = null;
let deliveringFile = false;


/* =========================================================
   QUALIDADES
   ========================================================= */

function qualities() {
  const media = $("media");
  const quality = $("quality");

  if (!media || !quality) return;

  const list =
    media.value === "video"
      ? VIDEO
      : AUDIO;

  quality.innerHTML = list
    .map(([value, text]) => {
      return `<option value="${value}">${text}</option>`;
    })
    .join("");
}


/* =========================================================
   PASTA PADRÃO
   ========================================================= */

async function defaults() {
  try {
    const response = await fetch(
      "/api/default-folder",
      {
        cache: "no-store"
      }
    );

    if (!response.ok) {
      throw new Error(
        "Não foi possível obter a pasta padrão."
      );
    }

    const data = await response.json();

    const media = $("media");
    const dest = $("dest");

    if (!media || !dest) return;

    if (media.value === "video") {
      dest.value = data.video || "";
    } else {
      dest.value = data.audio || "";
    }

  } catch (error) {
    console.warn(
      "Pasta padrão:",
      error
    );
  }
}


/* =========================================================
   ALTERAÇÃO DE FORMATO
   ========================================================= */

const mediaElement = $("media");

if (mediaElement) {
  mediaElement.onchange = () => {
    qualities();
    defaults();
  };
}

/* =========================================================
   BOTÃO PADRÃO
   ========================================================= */

const defaultButton = $("default");

if (defaultButton) {
  defaultButton.onclick = async () => {
    const button = defaultButton;

    button.disabled = true;
    button.textContent = "Carregando...";

    try {
      await defaults();

    } finally {
      button.disabled = false;
      button.textContent = "Padrão";
    }
  };
}

/* =========================================================
   ESCOLHER PASTA
   ========================================================= */

const chooseButton = $("choose");

if (chooseButton) {
  chooseButton.onclick = async () => {
    const button = chooseButton;

    button.disabled = true;
    button.textContent = "Abrindo...";

    try {
      const response = await fetch(
        "/api/choose-folder",
        {
          method: "POST",

          headers: {
            "Content-Type": "application/json"
          },

          body: JSON.stringify({
            initial: $("dest")
              ? $("dest").value
              : ""
          })
        }
      );
//Nunca nem vi
      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.error ||
          "Não foi possível escolher a pasta."
        );
      }

      if ($("dest")) {
        $("dest").value =
          data.path || "";
      }

    } catch (error) {
      showMessage(
        error.message,
        true
      );

    } finally {
      button.disabled = false;
      button.textContent =
        "Escolher pasta";
    }
  };
}


/* =========================================================
   COLAR URL
   ========================================================= */

const pasteButton = $("paste");

if (pasteButton) {
  pasteButton.onclick = async () => {
    const button = pasteButton;

    try {
      const text =
        await navigator.clipboard.readText();

      if (!text.trim()) {
        showMessage(
          "A área de transferência está vazia.",
          true
        );

        return;
      }

      if ($("url")) {
        $("url").value =
          text.trim();
      }

      button.textContent =
        "✓ Colado";

      setTimeout(() => {
        button.textContent =
          "Colar";
      }, 1500);

    } catch (error) {
      showMessage(
        "Não foi possível acessar a área de transferência.",
        true
      );
    }
  };
}


/* =========================================================
   SESSÃO DO NAVEGADOR
   ========================================================= */

const useBrowser = $("useBrowser");

if (useBrowser) {
  useBrowser.onchange = () => {

    const browserWrap =
      $("browserWrap");

    if (!browserWrap) return;

    browserWrap.classList.toggle(
      "hidden",
      !useBrowser.checked
    );
  };
}


/* =========================================================
   TEMA
   ========================================================= */

const themeButton = $("theme");

if (themeButton) {
  themeButton.onclick = () => {

    document.body.classList.toggle(
      "light"
    );

    themeButton.textContent =
      document.body.classList.contains("light")
        ? "🌙"
        : "☀️";
  };
}


/* =========================================================
   MENSAGENS
   ========================================================= */

function showMessage(
  text,
  error = false
) {
  const status = $("status");
  const msg = $("msg");

  if (status) {
    status.classList.remove(
      "hidden"
    );
  }

  if (msg) {
    msg.textContent =
      text || "";

    msg.className =
      error
        ? "error"
        : "";
  }
}


/* =========================================================
   ATUALIZAÇÃO DO STATUS
   ========================================================= */

function update(job) {

  if ($("status")) {
    $("status").classList.remove(
      "hidden"
    );
  }

  const percent =
    Number(job.percent || 0);

  if ($("percent")) {
    $("percent").textContent =
      `${percent}%`;
  }

  if ($("bar")) {
    $("bar").style.width =
      `${Math.min(
        100,
        Math.max(0, percent)
      )}%`;
  }

  if ($("speed")) {
    $("speed").textContent =
      job.speed || "--";
  }

  if ($("eta")) {
    $("eta").textContent =
      job.eta || "--";
  }

  if ($("file")) {
    $("file").textContent =
      job.filename || "--";
  }


  const states = {
    queued:
      "Na fila...",

    starting:
      "Preparando...",

    downloading:
      "Baixando...",

    processing:
      "Processando arquivo...",

    completed:
      "Download concluído!",

    error:
      "Download interrompido"
  };


  if ($("state")) {
    $("state").textContent =
      states[job.status] ||
      "Processando...";
  }


  if ($("msg")) {
    $("msg").textContent =
      job.error ||
      job.message ||
      "";

    $("msg").className =
      job.error
        ? "error"
        : "";
  }


  /* =======================================================
     DOWNLOAD CONCLUÍDO
     ======================================================= */

  if (
    job.status === "completed" &&
    !deliveringFile
  ) {

    if ($("percent")) {
      $("percent").textContent =
        "100%";
    }

    if ($("bar")) {
      $("bar").style.width =
        "100%";
    }

    if ($("speed")) {
      $("speed").textContent =
        "--";
    }

    if ($("eta")) {
      $("eta").textContent =
        "Concluído";
    }

    if ($("file")) {
      $("file").textContent =
        job.filename ||
        "Arquivo pronto";
    }

    if ($("msg")) {
      $("msg").textContent =
        "Preparando o arquivo para download...";

      $("msg").className = "";
    }

    deliverFile(
      job.id ||
      currentJobId
    );
  }


  /* =======================================================
     ERRO
     ======================================================= */

  if (
    job.status === "error"
  ) {

    if ($("msg")) {
      $("msg").textContent =
        job.error ||
        "O download não pôde ser concluído.";

      $("msg").className =
        "error";
    }

    resetDownloadButton(
      "↻ Tentar novamente"
    );
  }
}


/* =========================================================
   ENTREGA DO ARQUIVO
   ========================================================= */

async function deliverFile(jobId) {

  if (!jobId) {

    showMessage(
      "Download concluído, mas o identificador do arquivo não foi encontrado.",
      true
    );

    resetDownloadButton(
      "↻ Tentar novamente"
    );

    return;
  }


  if (deliveringFile) {
    return;
  }

  deliveringFile = true;


  try {

    const response =
      await fetch(
        `/api/download-file/${encodeURIComponent(jobId)}`,
        {
          cache: "no-store"
        }
      );


    if (!response.ok) {

      let message =
        "Não foi possível baixar o arquivo.";

      try {

        const data =
          await response.json();

        if (data.error) {
          message =
            data.error;
        }

      } catch (_) {
        // Resposta não era JSON.
      }

      throw new Error(
        message
      );
    }


    /* -----------------------------------------------------
       Recebe o arquivo
       ----------------------------------------------------- */

    const blob =
      await response.blob();


    if (!blob.size) {

      throw new Error(
        "O servidor retornou um arquivo vazio."
      );
    }


    /* -----------------------------------------------------
       Descobre o nome do arquivo
       ----------------------------------------------------- */

    let filename =
      "belfort-download";


    const disposition =
      response.headers.get(
        "Content-Disposition"
      );


    if (disposition) {

      const match =
        disposition.match(
          /filename\*=UTF-8''([^;]+)|filename="?([^"]+)"?/i
        );

      if (match) {

        try {
          filename =
            decodeURIComponent(
              match[1] ||
              match[2]
            );
        } catch (_) {
          filename =
            match[1] ||
            match[2] ||
            filename;
        }
      }
    }


    /* -----------------------------------------------------
       Cria o download
       ----------------------------------------------------- */

    const blobUrl =
      window.URL.createObjectURL(
        blob
      );


    const link =
      document.createElement("a");


    link.href =
      blobUrl;

    link.download =
      filename;

    document.body.appendChild(
      link
    );

    link.click();

    link.remove();


    setTimeout(() => {

      window.URL.revokeObjectURL(
        blobUrl
      );

    }, 1000);


    if ($("msg")) {
      $("msg").textContent =
        "✓ Arquivo baixado com sucesso!";

      $("msg").className = "";
    }


    if ($("state")) {
      $("state").textContent =
        "Download concluído!";
    }


    if ($("download")) {
      $("download").textContent =
        "✓ Download concluído";
    }


    setTimeout(() => {

      resetDownloadButton();

    }, 1800);


  } catch (error) {

    console.error(
      "Erro ao entregar arquivo:",
      error
    );

    showMessage(
      error.message ||
      "Erro ao baixar o arquivo final.",
      true
    );

    resetDownloadButton(
      "↻ Tentar novamente"
    );

  } finally {

    deliveringFile = false;
  }
}


/* =========================================================
   BOTÃO DE DOWNLOAD
   ========================================================= */

function resetDownloadButton(
  text = "⬇ Iniciar download"
) {

  const button =
    $("download");

  if (!button) return;

  button.disabled =
    false;

  button.textContent =
    text;
}


/* =========================================================
   MONITORAMENTO
   ========================================================= */

function stopPolling() {

  if (pollTimer) {

    clearInterval(
      pollTimer
    );

    pollTimer = null;
  }
}


function poll(jobId) {

  currentJobId =
    jobId;

  stopPolling();


  const check =
    async () => {

      try {

        const response =
          await fetch(
            `/api/progress/${encodeURIComponent(jobId)}`,
            {
              cache: "no-store"
            }
          );


        if (!response.ok) {

          throw new Error(
            "Não foi possível consultar o progresso."
          );
        }


        const job =
          await response.json();


        update({
          ...job,
          id: jobId
        });


        if (
          job.status === "completed" ||
          job.status === "error"
        ) {

          stopPolling();
        }


      } catch (error) {

        console.error(
          "Erro no monitoramento:",
          error
        );


        showMessage(
          "Perda de comunicação com o servidor.",
          true
        );


        stopPolling();


        resetDownloadButton(
          "↻ Tentar novamente"
        );
      }
    };


  check();


  pollTimer =
    setInterval(
      check,
      1000
    );
}


/* =========================================================
   INICIAR DOWNLOAD
   ========================================================= */

const downloadButton =
  $("download");


if (downloadButton) {

  downloadButton.onclick =
    async () => {

      const url =
        $("url")
          ? $("url").value.trim()
          : "";

      const dest =
        $("dest")
          ? $("dest").value.trim()
          : "";


      /* ---------------------------------------------------
         Validação da URL
         --------------------------------------------------- */

      if (!url) {

        showMessage(
          "Cole uma URL do YouTube.",
          true
        );

        if ($("url")) {
          $("url").focus();
        }

        return;
      }


      /* ---------------------------------------------------
         Detecta Render
         --------------------------------------------------- */

      const isRender =
        window.location.hostname.includes(
          "onrender.com"
        );


      /* ---------------------------------------------------
         Destino local
         --------------------------------------------------- */

      if (
        !dest &&
        !isRender
      ) {

        showMessage(
          "Escolha uma pasta de destino.",
          true
        );

        if ($("dest")) {
          $("dest").focus();
        }

        return;
      }


      /* ---------------------------------------------------
         Para polling anterior
         --------------------------------------------------- */

      stopPolling();

      currentJobId =
        null;

      deliveringFile =
        false;


      /* ---------------------------------------------------
         Estado inicial
         --------------------------------------------------- */

      downloadButton.disabled =
        true;

      downloadButton.textContent =
        "⏳ Preparando...";


      if ($("status")) {
        $("status").classList.remove(
          "hidden"
        );
      }


      if ($("state")) {
        $("state").textContent =
          "Preparando...";
      }

      if ($("percent")) {
        $("percent").textContent =
          "0%";
      }

      if ($("bar")) {
        $("bar").style.width =
          "0%";
      }

      if ($("speed")) {
        $("speed").textContent =
          "--";
      }

      if ($("eta")) {
        $("eta").textContent =
          "--";
      }

      if ($("file")) {
        $("file").textContent =
          "--";
      }

      if ($("msg")) {
        $("msg").textContent =
          "Iniciando download...";

        $("msg").className = "";
      }


      /* ---------------------------------------------------
         Dados enviados para Flask
         --------------------------------------------------- */

      const body = {

        url: url,

        mode:
          $("mode")
            ? $("mode").value
            : "download",

        media:
          $("media")
            ? $("media").value
            : "video",

        quality:
          $("quality")
            ? $("quality").value
            : "best",

        destination:
          dest,

        browser:
          $("useBrowser") &&
          $("useBrowser").checked
            ? (
                $("browser")
                  ? $("browser").value
                  : "none"
              )
            : "none"
      };


      try {

        const response =
          await fetch(
            "/api/download",
            {
              method: "POST",

              headers: {
                "Content-Type":
                  "application/json"
              },

              body:
                JSON.stringify(body)
            }
          );


        let data;


        try {

          data =
            await response.json();

        } catch (_) {

          throw new Error(
            "O servidor retornou uma resposta inválida."
          );
        }


        if (!response.ok) {

          throw new Error(
            data.error ||
            "Não foi possível iniciar o download."
          );
        }


        if (!data.job_id) {

          throw new Error(
            "O servidor não retornou o ID do download."
          );
        }


        /* -------------------------------------------------
           Download iniciado
           ------------------------------------------------- */

        currentJobId =
          data.job_id;


        downloadButton.textContent =
          "⏳ Baixando...";


        poll(
          data.job_id
        );


      } catch (error) {

        console.error(
          "Erro ao iniciar download:",
          error
        );


        resetDownloadButton();


        showMessage(
          error.message ||
          "Não foi possível iniciar o download.",
          true
        );
      }
    };
}

/* =========================================================
   ENTER PARA BAIXAR
   ========================================================= */

const urlElement =
  $("url");


if (urlElement) {

  urlElement.addEventListener(
    "keydown",
    (event) => {

      if (
        event.key === "Enter" &&
        !event.shiftKey
      ) {

        event.preventDefault();


        const button =
          $("download");


        if (
          button &&
          !button.disabled
        ) {

          button.click();
        }
      }
    }
  );
}

/* =========================================================
   INICIALIZAÇÃO
   ========================================================= */

qualities();
defaults();
