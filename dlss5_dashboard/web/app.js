"use strict";

const $ = (s, el = document) => el.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let GAMES = [];
let CURRENT = null;
let OPTIONS = null;

async function api(path, body) {
  const opts = { headers: { "X-Token": window.DLSS_TOKEN } };
  if (body !== undefined) {
    opts.method = "POST";
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (err ? " err" : "");
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), err ? 7000 : 3500);
}

// ---------------------------------------------------------------- system

async function loadSystem(refresh = false) {
  const el = $("#system");
  try {
    const s = await api("/api/sysinfo" + (refresh ? "?refresh=1" : ""));
    const g = s.gpus[0];
    const kv = (k, v) => `<div><div class="k">${esc(k)}</div><div class="v">${esc(v ?? "—")}</div></div>`;
    el.innerHTML =
      kv("GPU", g ? g.name : (s.adapters[0] || "Nessuna GPU NVIDIA")) +
      kv("Architettura", g ? `${g.arch} (${g.series})` : null) +
      kv("Driver NVIDIA", g?.driver) +
      kv("VRAM", g?.vram_mb ? `${(g.vram_mb / 1024).toFixed(0)} GB` : null) +
      kv("CPU", s.cpu) +
      kv("RAM", s.ram_gb ? `${s.ram_gb} GB` : null) +
      kv("Sistema", s.os) +
      `<div class="status ${esc(s.dlss5.level)}"><b>${esc(s.dlss5.title)}</b><div class="small muted">${esc(s.dlss5.detail)}</div></div>`;
  } catch (e) {
    el.innerHTML = `<div class="alert danger">Errore lettura sistema: ${esc(e.message)}</div>`;
  }
}

// ---------------------------------------------------------------- games list

async function loadGames() {
  try {
    GAMES = await api("/api/games");
  } catch (e) {
    toast(e.message, true);
    GAMES = [];
  }
  renderGames();
}

function renderGames() {
  const q = $("#search").value.toLowerCase();
  const list = GAMES.filter((g) => g.name.toLowerCase().includes(q));
  $("#games").innerHTML = list.length
    ? list.map((g) => `<li data-id="${esc(g.id)}" class="${g.id === CURRENT ? "active" : ""}">
        <span>${esc(g.name)}</span>
        ${g.installed_route ? `<span class="badge on">${esc(g.installed_route)}</span>` : ""}
      </li>`).join("")
    : `<li class="muted">Nessun gioco trovato. Aggiungilo a mano qui sotto.</li>`;
}

// ---------------------------------------------------------------- detail

async function openGame(id) {
  CURRENT = id;
  history.replaceState(null, "", "#game=" + encodeURIComponent(id));
  renderGames();
  $("#detail").innerHTML = `<div class="card empty">Analizzo il gioco…</div>`;
  try {
    const g = await api("/api/game?id=" + encodeURIComponent(id));
    if (CURRENT === id) renderDetail(g);
  } catch (e) {
    $("#detail").innerHTML = `<div class="card alert danger">${esc(e.message)}</div>`;
  }
}

function kv(k, v) {
  return `<div><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`;
}

function renderDetail(g) {
  const inst = g.install;
  const native = Object.keys(g.native_dlss || {});
  const enabled = inst ? inst.enabled : null;
  const prefs = g.prefs || {};
  const dlssOn = prefs.dlss_on ?? true;

  const info = `
    <div class="card">
      <div class="title-row">
        <h2>${esc(g.name)}</h2>
        <div class="row">
          ${inst ? `<span class="badge ${enabled === false ? "off" : "on"}">${esc(inst.route)} ${enabled === false ? "disattivato" : "installato"}</span>` : `<span class="badge">non installato</span>`}
          <button class="ghost" data-act="folder">Apri cartella</button>
          ${g.source === "manual" ? `<button class="ghost" data-act="remove">Rimuovi</button>` : ""}
        </div>
      </div>
      <div class="grid">
        ${kv("Eseguibile", esc(g.exe || "non trovato"))}
        ${kv("Architettura / API", esc(`${g.arch || "?"} · ${g.api || "non rilevata"}`))}
        ${kv("DLSS nativo", native.length ? esc(native.join(", ")) : "No")}
        ${kv("Anti-cheat", Object.keys(g.anticheat || {}).length ? `<span class="badge err">${esc(Object.keys(g.anticheat).join(", "))}</span>` : "Nessuno rilevato")}
      </div>
      ${(g.warnings || []).map((w) => `<div class="alert danger">${esc(w)}</div>`).join("")}
      ${(g.notes || []).map((n) => `<div class="alert">${esc(n)}</div>`).join("")}
    </div>`;

  const launch = g.exe ? `
    <div class="card">
      <h3>Avvio</h3>
      <div class="launch">
        <label class="switch" title="${inst ? "" : "Installa prima una route"}">
          <input type="checkbox" id="dlss-on" ${dlssOn && inst ? "checked" : ""} ${inst ? "" : "disabled"}>
          <span class="track"></span><span id="dlss-label">DLSS 5 ${dlssOn && inst ? "ON" : "OFF"}</span>
        </label>
        <input class="args" id="args" placeholder="Parametri di avvio (es. -nointro)" value="${esc(prefs.args || "")}">
        <button class="big" data-act="launch">▶ Avvia gioco</button>
      </div>
      <div class="small muted" style="margin-top:8px">OFF rinomina le DLL iniettate in *.dlss5off: il gioco parte originale. ON le rimette.</div>
    </div>` : "";

  $("#detail").innerHTML = info + launch + installCard(g) + settingsCards(g);
  bindDetail(g);
}

function installCard(g) {
  if (!g.exe) return "";
  if (g.install) {
    const i = g.install;
    return `<div class="card">
      <h3>Installazione</h3>
      <div class="grid">
        ${kv("Route", esc(i.route))}
        ${kv("File aggiunti", esc(i.added.length))}
        ${kv("DLL proxy (on/off)", esc(i.proxies.join(", ") || "—"))}
        ${kv("Backup", `<code class="small">${esc(i.backup_dir)}</code>`)}
      </div>
      <details class="group"><summary>Elenco file aggiunti</summary><pre class="small">${esc(i.added.join("\n"))}</pre></details>
      <div class="row end"><button class="danger" data-act="restore">Disinstalla e ripristina originale</button></div>
    </div>`;
  }
  const rec = g.recommended_route;
  const o = OPTIONS || { consumers: {}, opti_builds: {}, proxies: [] };
  const sel = (id, obj) => `<select id="${id}">${Object.entries(obj).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join("")}</select>`;
  return `<div class="card">
    <h3>Installa DLSS 5</h3>
    <div class="form">
      <div class="field"><label>Route</label>
        <select id="route">
          <option value="feeder" ${rec === "feeder" ? "selected" : ""}>DLSS5-Feeder${rec === "feeder" ? " (consigliata)" : ""} — giochi senza DLSS</option>
          <option value="optiscaler" ${rec === "optiscaler" ? "selected" : ""}>OptiScaler DLSS-NR${rec === "optiscaler" ? " (consigliata)" : ""} — giochi con DLSS</option>
        </select>
        <div class="help">Consigliata in base ai file del gioco (DLSS nativo: ${Object.keys(g.native_dlss || {}).length ? "sì" : "no"}).</div>
      </div>
      <div class="field" data-route="feeder"><label>API grafica del gioco</label>
        <select id="api">${Object.entries(o.apis || {}).map(([k, v]) => `<option value="${esc(k)}" ${k === g.feeder_api ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
        <div class="help">Decide come viene caricato ReShade (dxgi.dll per DirectX, layer di sistema per Vulkan).${g.feeder_api !== "Auto" ? " Preimpostata per questo gioco." : ""}</div></div>
      <div class="field" data-route="feeder"><label>Add-on neurale</label>${sel("consumer", o.consumers)}
        <div class="help">Si apre la finestra PowerShell dell'installer ufficiale del Feeder: rispondi lì alle domande.</div></div>
      <div class="field" data-route="optiscaler"><label>Build OptiScaler</label>${sel("build", o.opti_builds)}</div>
      <div class="field" data-route="optiscaler"><label>Nome DLL</label>${sel("proxy", Object.fromEntries(o.proxies.map((p) => [p, p])))}
        <div class="help">dxgi.dll va bene per la maggior parte dei giochi.</div></div>
      <div class="field"><label>nvngx_dlssnr.dll (facoltativo)</label>
        <input type="text" id="dlssnr" placeholder="C:\\percorso\\nvngx_dlssnr.dll">
        <div class="help">Il modello neurale DLSS 5. Su RTX 40 la versione firmata NVIDIA non parte: serve una build modificata dalla community. Sceglila tu, a tuo rischio: è un binario NVIDIA alterato e non verificabile.</div></div>
    </div>
    <div class="alert warn">Viene fatto un backup automatico dei file del gioco. Non usare in giochi online/multiplayer.</div>
    <div class="row end"><button data-act="install">Installa</button></div>
  </div>`;
}

function fieldHtml(f, value) {
  const id = `f-${f.id}`;
  let input;
  if (f.type === "select") {
    input = `<select id="${esc(id)}" data-fid="${esc(f.id)}">${Object.entries(f.options).map(([k, v]) =>
      `<option value="${esc(k)}" ${String(value) === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>`;
  } else {
    const isAuto = f.auto && (value === "auto" || value === undefined);
    const num = isAuto ? (f.min + f.max) / 2 : Number(value);
    const shown = isAuto ? Math.min(Math.max(1, f.min), f.max) : num;
    input = `<div class="num">
      <input type="range" id="${esc(id)}" data-fid="${esc(f.id)}" min="${f.min}" max="${f.max}" step="${f.step}" value="${esc(shown)}" ${isAuto ? "disabled" : ""}>
      <output>${isAuto ? "—" : esc(shown)}</output>
      ${f.auto ? `<label class="auto"><input type="checkbox" data-auto="${esc(f.id)}" ${isAuto ? "checked" : ""}>auto</label>` : ""}
    </div>`;
  }
  return `<div class="field"><label for="${esc(id)}">${esc(f.label)}</label>${input}${f.help ? `<div class="help">${esc(f.help)}</div>` : ""}</div>`;
}

function settingsCards(g) {
  return Object.entries(g.settings || {}).map(([key, { schema, values }]) => `
    <div class="card" data-settings="${esc(key)}">
      <h3>${esc(schema.title)}</h3>
      <div class="small muted">File: <code>${esc(schema.file)}</code> — le modifiche valgono dal prossimo avvio (alcune anche live dall'overlay del gioco).</div>
      ${schema.groups.map((gr) => {
        const body = `<div class="form">${gr.fields.map((f) => fieldHtml(f, values[f.id])).join("")}</div>`;
        return gr.advanced
          ? `<details class="group"><summary>${esc(gr.title)}</summary>${body}</details>`
          : `<div class="group"><h4>${esc(gr.title)}</h4>${body}</div>`;
      }).join("")}
      <div class="row end"><button data-act="save" data-file="${esc(key)}">Salva parametri</button></div>
    </div>`).join("");
}

function collect(card) {
  const values = {};
  card.querySelectorAll("[data-fid]").forEach((el) => {
    const auto = card.querySelector(`[data-auto="${CSS.escape(el.dataset.fid)}"]`);
    values[el.dataset.fid] = auto && auto.checked ? "auto" : el.value;
  });
  return values;
}

function bindDetail(g) {
  const d = $("#detail");
  const routeSel = $("#route", d);
  const syncRoute = () => d.querySelectorAll("[data-route]").forEach((el) =>
    (el.hidden = routeSel && el.dataset.route !== routeSel.value));
  if (routeSel) { routeSel.onchange = syncRoute; syncRoute(); }

  d.querySelectorAll('input[type=range]').forEach((r) => {
    r.oninput = () => (r.nextElementSibling.textContent = r.value);
  });
  d.querySelectorAll("[data-auto]").forEach((cb) => {
    cb.onchange = () => {
      const r = d.querySelector(`[data-fid="${CSS.escape(cb.dataset.auto)}"]`);
      r.disabled = cb.checked;
      r.nextElementSibling.textContent = cb.checked ? "—" : r.value;
    };
  });
  const sw = $("#dlss-on", d);
  if (sw) sw.onchange = async () => {
    $("#dlss-label").textContent = `DLSS 5 ${sw.checked ? "ON" : "OFF"}`;
    try {
      const r = await api("/api/toggle", { id: g.id, enabled: sw.checked });
      toast(r.log.length ? r.log.join("\n") : "Nessuna modifica");
    } catch (e) { toast(e.message, true); sw.checked = !sw.checked; }
  };

  d.onclick = async (ev) => {
    const b = ev.target.closest("button[data-act]");
    if (!b) return;
    const act = b.dataset.act;
    try {
      if (act === "launch") {
        const r = await api("/api/launch", { id: g.id, dlss_on: !!(sw && sw.checked), args: $("#args").value });
        toast(r.log.join("\n"));
      } else if (act === "folder") {
        await api("/api/open-folder", { id: g.id });
      } else if (act === "remove") {
        await api("/api/games/remove", { id: g.id });
        CURRENT = null; $("#detail").innerHTML = `<div class="card empty">Rimosso.</div>`; loadGames();
      } else if (act === "install") {
        const options = { api: $("#api").value, consumer: $("#consumer").value, build: $("#build").value,
                          proxy: $("#proxy").value, dlssnr: $("#dlssnr").value.trim() };
        const r = await api("/api/install", { id: g.id, route: $("#route").value, options });
        runJob(r.job, g.id);
      } else if (act === "restore") {
        if (!confirm("Rimuovere tutto quello che è stato installato e ripristinare i file originali?")) return;
        const r = await api("/api/restore", { id: g.id });
        runJob(r.job, g.id);
      } else if (act === "save") {
        const card = b.closest("[data-settings]");
        const r = await api("/api/settings", { id: g.id, file: b.dataset.file, values: collect(card) });
        toast(r.changed.length ? `Salvati ${r.changed.length} parametri` : "Nessuna modifica");
      }
    } catch (e) { toast(e.message, true); }
  };
}

// ---------------------------------------------------------------- jobs

async function runJob(jid, gameId) {
  const dlg = $("#job");
  $("#job-log").textContent = "";
  $("#job-status").textContent = "in corso";
  $("#job-status").className = "badge";
  dlg.showModal();
  for (;;) {
    let j;
    try { j = await api("/api/job?id=" + jid); } catch (e) { toast(e.message, true); return; }
    $("#job-title").textContent = j.title;
    const log = $("#job-log");
    log.textContent = j.log.join("\n");
    log.scrollTop = log.scrollHeight;
    if (j.status !== "running") {
      $("#job-status").textContent = j.status === "done" ? "completato" : "errore";
      $("#job-status").className = "badge " + (j.status === "done" ? "on" : "err");
      loadGames();
      if (CURRENT === gameId) openGame(gameId);
      return;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
}

// ---------------------------------------------------------------- init

document.addEventListener("DOMContentLoaded", async () => {
  $("#games").onclick = (e) => { const li = e.target.closest("li[data-id]"); if (li) openGame(li.dataset.id); };
  $("#search").oninput = renderGames;
  $("#refresh-sys").onclick = () => loadSystem(true);
  $("#job-close").onclick = () => $("#job").close();
  $("#add-btn").onclick = async () => {
    try {
      const g = await api("/api/games/add", { exe: $("#add-exe").value.trim().replace(/^"|"$/g, ""), name: $("#add-name").value.trim() });
      $("#add-exe").value = $("#add-name").value = "";
      await loadGames();
      openGame(g.id);
    } catch (e) { toast(e.message, true); }
  };
  OPTIONS = await api("/api/options").catch(() => null);
  loadSystem();
  await loadGames();
  const m = location.hash.match(/^#game=(.+)$/);
  if (m) openGame(decodeURIComponent(m[1]));
});
