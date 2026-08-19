const $ = id => document.getElementById(id);
const VIDEO = [["best","Melhor disponível"],["2160","2160p (4K)"],["1440","1440p (2K)"],["1080","1080p (Full HD)"],["720","720p (HD)"],["480","480p"],["360","360p"]];
const AUDIO = [["320","320 kbps"],["256","256 kbps"],["192","192 kbps"],["128","128 kbps"]];

function qualities(){
  const list = $("media").value === "video" ? VIDEO : AUDIO;
  $("quality").innerHTML = list.map(([v,t]) => `<option value="${v}">${t}</option>`).join("");
}

async function defaults(){
  try {
    const d = await (await fetch("/api/default-folder")).json();
    $("dest").value = $("media").value === "video" ? d.video : d.audio;
  } catch {}
}

$("media").onchange = () => { qualities(); defaults(); };
$("default").onclick = defaults;

$("choose").onclick = async () => {
  const button = $("choose");
  button.disabled = true;
  button.textContent = "Abrindo...";
  try {
    const r = await fetch("/api/choose-folder", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({initial:$("dest").value})});
    const d = await r.json();
    if (!r.ok) throw Error(d.error || "Não foi possível escolher a pasta.");
    $("dest").value = d.path;
  } catch(e) {
    showMessage(e.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "Escolher pasta";
  }
};

$("paste").onclick = async () => {
  try { $("url").value = await navigator.clipboard.readText(); }
  catch { showMessage("Não foi possível acessar a área de transferência.", true); }
};

$("useBrowser").onchange = () => $("browserWrap").classList.toggle("hidden", !$("useBrowser").checked);

$("theme").onclick = () => {
  document.body.classList.toggle("light");
  $("theme").textContent = document.body.classList.contains("light") ? "🌙" : "☀️";
};

function showMessage(text, error=false){
  $("status").classList.remove("hidden");
  $("msg").textContent = text || "";
  $("msg").className = error ? "error" : "";
}

function update(j){
  $("status").classList.remove("hidden");
  $("percent").textContent = (j.percent || 0) + "%";
  $("bar").style.width = (j.percent || 0) + "%";
  $("speed").textContent = j.speed || "--";
  $("eta").textContent = j.eta || "--";
  $("file").textContent = j.filename || "--";
  $("state").textContent = {queued:"Na fila...",starting:"Preparando...",downloading:"Baixando...",processing:"Processando...",completed:"Download concluído!",error:"Download interrompido"}[j.status] || "Processando...";
  $("msg").textContent = j.error || j.message || "";
  $("msg").className = j.error ? "error" : "";
}

function poll(id){
  const timer = setInterval(async () => {
    try {
      const j = await (await fetch("/api/progress/" + id)).json();
      update(j);
      if (["completed","error"].includes(j.status)) {
        clearInterval(timer);
        $("download").disabled = false;
        $("download").textContent = j.status === "completed" ? "✓ Download concluído" : "↻ Tentar novamente";
      }
    } catch(e) {
      showMessage("Perda de comunicação com o servidor.", true);
      clearInterval(timer);
      $("download").disabled = false;
    }
  }, 800);
}

$("download").onclick = async () => {
  const url = $("url").value.trim();
  const dest = $("dest").value.trim();
  if (!url) return showMessage("Cole uma URL do YouTube.", true);
  if (!dest) return showMessage("Escolha uma pasta de destino.", true);

  $("download").disabled = true;
  $("download").textContent = "Preparando...";
  try {
    const body = {
      url,
      mode: $("mode").value,
      media: $("media").value,
      quality: $("quality").value,
      destination: dest,
      browser: $("useBrowser").checked ? $("browser").value : "none"
    };
    const r = await fetch("/api/download", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
    const d = await r.json();
    if (!r.ok) throw Error(d.error || "Não foi possível iniciar o download.");
    poll(d.job_id);
  } catch(e) {
    $("download").disabled = false;
    $("download").textContent = "⬇ Iniciar download";
    showMessage(e.message, true);
  }
};

qualities();
defaults();
