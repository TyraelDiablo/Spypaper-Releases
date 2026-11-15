/* Spypaper Remote — telefon arayüzü. Masaüstündeki Spypaper'ın sunduğu /api uçlarını kullanır.
   Anahtar HttpOnly çerezde durur; bu dosya onu göremez. Harici kütüphane yok. */
"use strict";

const ICONS = {
  back: '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
  play: '<polygon points="6 3 20 12 6 21 6 3"/>',
  stop: '<rect width="18" height="18" x="3" y="3" rx="2"/>',
  restart: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
  map: '<path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z"/><path d="M15 5.764v15"/><path d="M9 3.236v15"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  log: '<path d="M15 12h-5"/><path d="M15 8h-5"/><path d="M19 17V5a2 2 0 0 0-2-2H4"/><path d="M8 21h12a2 2 0 0 0 2-2v-1a1 1 0 0 0-1-1H11a1 1 0 0 0-1 1v1a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v2a1 1 0 0 0 1 1h3"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/>',
  lock: '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  cpu: '<rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/>',
  ram: '<path d="M6 19v-3"/><path d="M10 19v-3"/><path d="M14 19v-3"/><path d="M18 19v-3"/><path d="M8 11V9"/><path d="M16 11V9"/><path d="M12 11V9"/><path d="M2 15h20"/><path d="M2 7a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v1.1a2 2 0 0 0 0 3.837V17a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-5.1a2 2 0 0 0 0-3.837Z"/>',
  phone: '<rect width="14" height="20" x="5" y="2" rx="2" ry="2"/><path d="M12 18h.01"/>',
};
const svg = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
let S = {};                                    // çeviriler (Türkçe kaynak -> panel dili)
const T = (k, vars) => {
  let s = S[k] || k;
  if (vars) for (const [a, b] of Object.entries(vars)) s = s.split("{" + a + "}").join(b);
  return s;
};
const GAMEMODES = ["Hayatta Kalma", "Yaratıcı", "Macera", "İzleyici"];

async function api(path, opts = {}) {
  const init = { credentials: "same-origin", cache: "no-store", ...opts };
  if (opts.body !== undefined) {
    init.method = "POST";
    init.headers = { "Content-Type": "application/json", "X-Spypaper": "1" };
    init.body = JSON.stringify(opts.body);
  }
  const r = await fetch(path, init);
  let data = {};
  try { data = await r.json(); } catch (_) { /* boş yanıt */ }
  if (!r.ok) { const e = new Error(data.error || r.status); e.status = r.status; e.data = data; throw e; }
  return data;
}

/* ---------------------------------------------------------------- Minecraft HUD */
// 9x9 desenler (kendi çizimimiz; masaüstündeki ui/hud.py ile aynı). Kullanıcının bilgisayarında
// Minecraft'ın kendi görselleri hazırlanmışsa (Oyun Dosyaları) /hud/*.png onları verir.
const PAT = {
  heart: ["..KK.KK..", ".KRRKRRK.", "KRHRRRRRK", "KRRRRRRDK", "KRRRRRRDK", ".KRRRRDK.", "..KRRDK..", "...KDK...", "....K...."],
  food: ["......KK.", ".....KHHK", "....KHHK.", "..KKRRK..", ".KRRRRK..", "KRRRRDK..", "KRRRDK...", ".KDDK....", "..KK....."],
  armor: ["KKKK.KKKK", "KHHRKRRDK", "KHRRRRRDK", "KRRRRRRDK", ".KRRRRDK.", ".KRRRRDK.", ".KRRRRDK.", ".KRRDRDK.", ".KKK.KKK."],
};
const PAL = {
  heart: { K: "#1d0303", R: "#d62a2a", H: "#ff9b9b", D: "#8f1414" },
  gold: { K: "#251a00", R: "#e6b412", H: "#fff1a0", D: "#9a7400" },
  food: { K: "#2a1606", R: "#b8702f", H: "#f0e6d8", D: "#7a4518" },
  armor: { K: "#1a1a1a", R: "#c8c8c8", H: "#ffffff", D: "#7d7d7d" },
};
function pattern(rows, pal, mode) {
  const c = document.createElement("canvas");
  c.width = c.height = 9;
  const g = c.getContext("2d");
  rows.forEach((line, y) => [...line].forEach((ch, x) => {
    if (ch === ".") return;
    let col = pal[ch];
    if (ch !== "K" && (mode === "empty" || (mode === "left" && x > 4) || (mode === "right" && x < 4))) col = "#2a2a2a";
    g.fillStyle = col;
    g.fillRect(x, y, 1, 1);
  }));
  return c;
}
const FALLBACK = {
  heart_container: () => pattern(PAT.heart, PAL.heart, "empty"),
  heart_full: () => pattern(PAT.heart, PAL.heart),
  heart_half: () => pattern(PAT.heart, PAL.heart, "left"),
  heart_absorbing_full: () => pattern(PAT.heart, PAL.gold),
  heart_absorbing_half: () => pattern(PAT.heart, PAL.gold, "left"),
  food_empty: () => pattern(PAT.food, PAL.food, "empty"),
  food_full: () => pattern(PAT.food, PAL.food),
  food_half: () => pattern(PAT.food, PAL.food, "right"),
  armor_empty: () => pattern(PAT.armor, PAL.armor, "empty"),
  armor_full: () => pattern(PAT.armor, PAL.armor),
  armor_half: () => pattern(PAT.armor, PAL.armor, "left"),
  experience_bar_background: () => null,
  experience_bar_progress: () => null,
};
const SPR = {};
let sprReady = null;
function loadSprites() {
  if (sprReady) return sprReady;
  const have = new Set((st.me && st.me.hud) || []);          // bilgisayarda hazırlanmış Minecraft görselleri
  sprReady = Promise.all(Object.keys(FALLBACK).map((n) => new Promise((done) => {
    if (!have.has(n)) { SPR[n] = FALLBACK[n](); done(); return; }
    const im = new Image();
    im.onload = () => { SPR[n] = im; done(); };
    im.onerror = () => { SPR[n] = FALLBACK[n](); done(); };
    im.src = "/hud/" + n + ".png";
  })));
  return sprReady;
}

const IC = 18, GAP = 1;
function drawHud(canvas, p) {
  const half = 10 * (IC + GAP), rightX = half + 16, yTop = 0, yMid = IC + 3, barY = yMid + IC + 6, barH = 6;
  canvas.width = rightX + half;
  canvas.height = barY + barH;
  const g = canvas.getContext("2d");
  g.imageSmoothingEnabled = false;
  const icon = (n, x, y) => { const im = SPR[n]; if (im) g.drawImage(im, x, y, IC, IC); };
  const row = (y, value, full, halfN, empty, rtl, x0, back) => {
    for (let i = 0; i < 10; i++) {
      const x = x0 + (rtl ? 9 - i : i) * (IC + GAP);
      if (back) icon(back, x, y);
      const pts = value - i * 2;
      if (pts >= 2) icon(full, x, y);
      else if (pts === 1) icon(halfN, x, y);
      else if (!back && empty) icon(empty, x, y);
    }
  };
  g.globalAlpha = (p.gamemode === 1 || p.gamemode === 3) ? 0.35 : 1;   // yaratıcı/izleyici: oyunda görünmez
  if (p.armor > 0) row(yTop, p.armor, "armor_full", "armor_half", "armor_empty", false, 0);
  if (p.absorption > 0) row(yTop, Math.round(p.absorption), "heart_absorbing_full", "heart_absorbing_half", null, false, p.armor ? rightX : 0);
  row(yMid, Math.round(p.health || 0), "heart_full", "heart_half", null, false, 0, "heart_container");
  row(yMid, p.food || 0, "food_full", "food_half", "food_empty", true, rightX, "food_empty");
  g.globalAlpha = 1;
  const w = canvas.width, bg = SPR.experience_bar_background, fg = SPR.experience_bar_progress, pr = Math.max(0, Math.min(1, p.progress || 0));
  if (bg && fg) {
    g.drawImage(bg, 0, barY, w, barH);
    if (pr > 0) g.drawImage(fg, 0, 0, Math.max(1, Math.round(fg.width * pr)), fg.height, 0, barY, w * pr, barH);
  } else {
    g.fillStyle = "#000"; g.fillRect(0, barY, w, barH);
    g.fillStyle = "#1b1b1b"; g.fillRect(1, barY + 1, w - 2, barH - 2);
    g.fillStyle = "#80ff20"; g.fillRect(1, barY + 1, (w - 2) * pr, barH - 2);
  }
}

/* ---------------------------------------------------------------- durum */
const st = { me: null, timer: null, view: "", tab: "players", lastErr: false, busy: false };

function banner(text) {
  const b = $("banner");
  b.hidden = !text;
  b.textContent = text || "";
}
function setBar(title, subtitle, back) {
  $("title").textContent = title;
  $("subtitle").textContent = subtitle || "";
  $("back").hidden = !back;
}
function schedule(fn, ms) {
  clearTimeout(st.timer);
  st.timer = setTimeout(() => { if (!document.hidden) fn(); else schedule(fn, ms); }, ms);
}

/* ---------------------------------------------------------------- pencere (alert/confirm yerine) */
function dialog({ title, text, ok, okClass = "primary", input = false }) {
  return new Promise((resolve) => {
    $("m-title").textContent = title || "";
    $("m-text").textContent = text || "";
    const inp = $("m-input");
    inp.hidden = !input;
    inp.value = "";
    inp.placeholder = input ? T("PIN") : "";
    $("m-ok").textContent = ok || T("Tamam");
    $("m-ok").className = "btn " + okClass;
    $("m-cancel").textContent = T("İptal");
    $("modal").hidden = false;
    if (input) setTimeout(() => inp.focus(), 50);
    const close = (val) => {
      $("modal").hidden = true;
      $("m-ok").onclick = $("m-cancel").onclick = inp.onkeydown = null;
      resolve(val);
    };
    $("m-ok").onclick = () => close(input ? inp.value : true);
    $("m-cancel").onclick = () => close(input ? null : false);
    inp.onkeydown = (e) => { if (e.key === "Enter") close(inp.value); };
  });
}

/* ---------------------------------------------------------------- ekranlar */
function stateClass(s) { return ["running", "starting", "stopping", "external"].includes(s) ? s : ""; }
function fmtRam(mb, max) { return mb == null ? "—" : (mb >= 1024 ? (mb / 1024).toFixed(1) + " GB" : mb + " MB"); }

function serverCard(s) {
  const initial = esc((s.name || "?").trim().charAt(0).toUpperCase());
  const sw = [s.software, s.version].filter(Boolean).join(" ");
  return `<button class="card server" data-id="${esc(s.id)}">
    <div class="row">
      <div class="avatar">${initial}</div>
      <div class="grow">
        <div class="row"><span class="name">${esc(s.name)}</span>${s.pin ? `<span class="lock" title="PIN">${svg("lock")}</span>` : ""}</div>
        <div class="row wrap" style="margin-top:4px">
          <span class="pill ${stateClass(s.state)}">${esc(s.state_text)}</span>
          ${sw ? `<span class="badge">${esc(sw)}</span>` : ""}
        </div>
      </div>
    </div>
    <div class="row meta wrap">
      <span>${svg("users").replace("<svg", '<svg style="width:14px;height:14px;vertical-align:-2px"')} <b>${s.online_count}</b> ${esc(T("Çevrimiçi").toLowerCase())}</span>
      <span>${esc(T("RAM"))} <b>${fmtRam(s.ram_mb)}</b></span>
      <span>${esc(T("CPU"))} <b>${s.cpu == null ? "—" : s.cpu + "%"}</b></span>
    </div>
  </button>`;
}

async function showList() {
  st.view = "list";
  setBar(T("Spypaper Remote"), st.me ? st.me.device : "", false);
  try {
    const d = await api("/api/servers");
    banner("");
    const v = $("view");
    v.innerHTML = d.servers.length ? d.servers.map(serverCard).join("") : `<div class="empty">—</div>`;
    v.querySelectorAll(".server").forEach((el) => el.addEventListener("click", () => { location.hash = "#s/" + el.dataset.id; }));
    $("subtitle").textContent = T("Son güncelleme: {t}", { t: d.time });
  } catch (e) {
    if (e.status === 401) return showUnpaired();
    banner(T("Bağlantı kesildi. Masaüstündeki Spypaper açık mı?"));
  }
  if (st.view === "list") schedule(showList, 4000);
}

function playerRow(p) {
  const gm = p.gamemode >= 0 && p.gamemode <= 3 ? T(GAMEMODES[p.gamemode]) : "";
  const hasHud = p.health !== undefined;
  return `<div class="player ${p.online ? "" : "off"}">
    <div class="row">
      <span class="dot ${p.online ? "on" : ""}"></span>
      <span class="grow name" style="font-size:15px">${esc(p.name)}</span>
      ${gm ? `<span class="gm">${esc(gm)}</span>` : ""}
      ${hasHud && p.level > 0 ? `<span class="lvl">${esc(T("Seviye {n}", { n: p.level }))}</span>` : ""}
    </div>
    ${hasHud ? `<canvas class="hud" aria-label="${esc(`${T("Can")} ${p.health}/20 · ${T("Açlık")} ${p.food}/20 · ${T("Zırh")} ${p.armor}`)}"></canvas>` : ""}
  </div>`;
}

async function action(s, act) {
  if (st.busy) return;
  if (act !== "start") {
    const ok = await dialog({
      title: s.name, text: T(act === "stop" ? "Sunucu durdurulsun mu?" : "Sunucu yeniden başlatılsın mı?"),
      ok: T(act === "stop" ? "Durdur" : "Yeniden Başlat"), okClass: act === "stop" ? "danger" : "primary",
    });
    if (!ok) return;
  }
  let pin;
  if (s.pin) {
    pin = await dialog({ title: s.name, text: T("Bu sunucu PIN ile korunuyor."), input: true });
    if (pin === null) return;
  }
  st.busy = true;
  try {
    await api(`/api/servers/${encodeURIComponent(s.id)}/${act}`, { body: { pin } });
    banner("");
  } catch (e) {
    if (e.status === 401 && !(e.data && e.data.need_pin)) return showUnpaired();
    await dialog({ title: s.name, text: e.message });
  } finally {
    st.busy = false;
  }
  showDetail(s.id, false);
}

async function showDetail(id, toBottom) {
  const v = $("view");
  if (st.view !== "detail:" + id) { st.view = "detail:" + id; v.innerHTML = ""; }
  try {
    const s = await api("/api/servers/" + encodeURIComponent(id));
    banner("");
    setBar(s.name, T("Son güncelleme: {t}", { t: s.time }), true);
    const running = ["running", "starting"].includes(s.state);
    const canCtl = s.control && s.state !== "external";
    const tab = st.tab;
    v.innerHTML = `
      <div class="card">
        <div class="row wrap">
          <span class="pill ${stateClass(s.state)}">${esc(s.state_text)}</span>
          ${[s.software, s.version].filter(Boolean).length ? `<span class="badge">${esc([s.software, s.version].filter(Boolean).join(" "))}</span>` : ""}
          ${s.pin ? `<span class="lock">${svg("lock")}</span>` : ""}
        </div>
        ${!s.exists ? `<div class="err">${esc(T("Sunucu klasörü bulunamadı."))}</div>` : ""}
        <div class="controls">
          <button class="btn primary" id="a-start" ${!canCtl || s.state !== "stopped" ? "disabled" : ""}>${svg("play")}${esc(T("Başlat"))}</button>
          <button class="btn danger" id="a-stop" ${!canCtl || !running ? "disabled" : ""}>${svg("stop")}${esc(T("Durdur"))}</button>
          <button class="btn" id="a-restart" ${!canCtl || s.state !== "running" ? "disabled" : ""} aria-label="${esc(T("Yeniden Başlat"))}">${svg("restart")}</button>
        </div>
        ${s.control_note ? `<div class="muted small" style="margin-top:8px">${esc(s.control_note)}</div>` : ""}
        <div class="stats">
          <div class="stat"><div class="k">${svg("users")}${esc(T("Çevrimiçi"))}</div><div class="v">${s.online_count}</div></div>
          <div class="stat"><div class="k">${svg("users")}${esc(T("Bugünkü giriş"))}</div><div class="v">${s.joins_today}</div></div>
          <div class="stat"><div class="k">${svg("ram")}${esc(T("RAM"))}</div><div class="v">${fmtRam(s.ram_mb)}</div></div>
          <div class="stat"><div class="k">${svg("cpu")}${esc(T("CPU"))}</div><div class="v">${s.cpu == null ? "—" : s.cpu + "%"}</div></div>
        </div>
        ${s.map_url ? `<a class="btn" style="margin-top:10px;width:100%;text-decoration:none" href="${esc(s.map_url)}" target="_blank" rel="noopener noreferrer">${svg("map")}${esc(T("Haritayı Aç"))}</a>` : ""}
      </div>
      <div class="tabs" role="tablist">
        <button class="tab ${tab === "players" ? "on" : ""}" data-tab="players">${svg("users")}${esc(T("Oyuncular"))}</button>
        <button class="tab ${tab === "log" ? "on" : ""}" data-tab="log">${svg("log")}${esc(T("Günlük"))}</button>
      </div>
      <div id="tabbody"></div>`;
    $("a-start").onclick = () => action(s, "start");
    $("a-stop").onclick = () => action(s, "stop");
    $("a-restart").onclick = () => action(s, "restart");
    v.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => { st.tab = b.dataset.tab; showDetail(id, st.tab === "log"); }));
    const body = $("tabbody");
    if (tab === "players") {
      const list = s.players || [];
      body.innerHTML = list.length ? `<div class="card players">${list.map(playerRow).join("")}</div>`
        : `<div class="card empty">${esc(T("Henüz oyuncu yok."))}</div>`;
      await loadSprites();
      body.querySelectorAll("canvas.hud").forEach((c, i) => drawHud(c, list[i]));
    } else {
      const lg = await api(`/api/servers/${encodeURIComponent(id)}/log`);
      body.innerHTML = lg.missing ? `<div class="card empty">${esc(T("Log dosyası bulunamadı."))}</div>`
        : `<div class="card log">${lg.lines.map((l) => `<div class="${esc(l.k)}">${esc(l.t)}</div>`).join("")}</div>`;
      const box = body.querySelector(".log");
      if (box) box.scrollTop = box.scrollHeight;
      if (toBottom) window.scrollTo(0, document.body.scrollHeight);
    }
  } catch (e) {
    if (e.status === 401) return showUnpaired();
    if (e.status === 404) { location.hash = ""; return; }
    banner(T("Bağlantı kesildi. Masaüstündeki Spypaper açık mı?"));
  }
  if (st.view === "detail:" + id) schedule(() => showDetail(id), 3000);
}

function showUnpaired() {
  clearTimeout(st.timer);
  st.view = "unpaired";
  setBar(T("Spypaper Remote"), "", false);
  $("logout").hidden = true;
  banner("");
  $("view").innerHTML = `<div class="card pair">
    <img src="/icon.svg" alt="">
    <h1>${esc(T("Bu cihaz eşli değil"))}</h1>
    <p class="muted">${esc(T("Masaüstündeki Spypaper'da ☰ → Spypaper Remote → Yeni Cihaz Eşle'ye bas ve çıkan QR kodu telefonun kamerasıyla okut."))}</p>
  </div>`;
}

function showPair(code) {
  st.view = "pair";
  setBar(T("Spypaper Remote"), "", false);
  const me = st.me;
  if (me.code_valid === false) {
    $("view").innerHTML = `<div class="card pair"><img src="/icon.svg" alt=""><h1>${esc(T("Bu cihazı eşle"))}</h1>
      <p class="err">${esc(T("Eşleşme kodu geçersiz ya da süresi dolmuş. Panelde yeni bir QR oluştur."))}</p></div>`;
    return;
  }
  $("view").innerHTML = `<div class="card pair">
    <img src="/icon.svg" alt="">
    <h1>${esc(T("Bu cihazı eşle"))}</h1>
    <label class="field"><span>${esc(T("Cihaz adı"))}</span><input id="devname" maxlength="40" value="${esc(me.suggest_name)}"></label>
    <button class="btn primary" id="dopair" style="width:100%">${svg("phone")}${esc(T("Eşle"))}</button>
    <div class="err" id="perr"></div>
  </div>`;
  $("dopair").onclick = async () => {
    $("dopair").disabled = true;
    try {
      await api("/api/pair", { body: { code, name: $("devname").value } });
      history.replaceState(null, "", "/");           // kodu adres çubuğundan ve geçmişten temizle
      await boot();
    } catch (e) {
      $("perr").textContent = e.message;
      $("dopair").disabled = false;
    }
  };
}

function route() {
  clearTimeout(st.timer);
  if (!st.me || !st.me.paired) return;
  const m = location.hash.match(/^#s\/([A-Za-z0-9_-]+)/);
  if (m) showDetail(m[1], st.tab === "log");
  else showList();
}

async function boot() {
  $("back").innerHTML = svg("back");
  $("logout").innerHTML = svg("logout");
  $("back").onclick = () => { location.hash = ""; };
  $("logout").onclick = async () => {
    const ok = await dialog({ title: T("Bu cihazın eşleşmesini kaldır"), text: T("Eşleşme kaldırılsın mı? Tekrar bağlanmak için yeni QR gerekir."), okClass: "danger" });
    if (!ok) return;
    try { await api("/api/logout", { body: {} }); } catch (_) { /* zaten düşmüş */ }
    st.me.paired = false;
    showUnpaired();
  };
  const code = new URLSearchParams(location.search).get("code") || "";
  try {
    st.me = await api("/api/me" + (code ? "?code=" + encodeURIComponent(code) : ""));
  } catch (e) {
    banner("Spypaper?");
    setTimeout(boot, 4000);
    return;
  }
  S = st.me.strings || {};
  document.documentElement.lang = (st.me.lang || "tr").replace("_", "-");
  document.documentElement.dir = st.me.rtl ? "rtl" : "ltr";
  $("back").setAttribute("aria-label", "←");
  if (!st.me.paired) return code ? showPair(code) : showUnpaired();
  if (code) history.replaceState(null, "", "/");
  $("logout").hidden = false;
  $("logout").setAttribute("aria-label", T("Bu cihazın eşleşmesini kaldır"));
  route();
}

window.addEventListener("hashchange", route);
document.addEventListener("visibilitychange", () => { if (!document.hidden && st.me && st.me.paired) route(); });
boot();
