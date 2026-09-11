"use strict";
const $ = (id) => document.getElementById(id);

/* Chemin SVG officiel de la baleine (injecté par Python depuis assets/whale_path.txt). */
window.__setWhale = function (p) {
  $("whalePath").setAttribute("d", p);
};

let weekBuilt = false;
function buildWeek(week) {
  const grid = $("weekGrid");
  const col = $("dayCol");
  grid.innerHTML = "";
  col.innerHTML = "";
  const days = ["L", "M", "M", "J", "V", "S", "D"];
  week.forEach((row, d) => {
    const r = document.createElement("div");
    r.className = "crow";
    row.forEach((v, h) => {
      const c = document.createElement("div");
      c.className = "cell" + (v ? " on" : "");
      c.dataset.d = d;
      c.dataset.h = h;
      r.appendChild(c);
    });
    grid.appendChild(r);
    const l = document.createElement("span");
    l.textContent = days[d];
    col.appendChild(l);
  });
  weekBuilt = true;
}

/* État poussé chaque seconde par Python (source de vérité unique). */
window.__update = function (s) {
  window.__state = s;
  const app = $("app");
  app.classList.toggle("peak", s.isPeak);
  app.classList.toggle("offpeak", !s.isPeak);
  $("chip").textContent = s.chip;
  $("countdown").textContent = s.countdown;
  $("nextLabel").textContent = s.nextLabel;
  $("nextAt").textContent = s.nextAt;
  $("progressFill").style.width = s.blockPct + "%";
  $("progressMeta").textContent = s.blockPct + " % du bloc en cours écoulé";
  $("beijingClock").textContent = s.beijingClock;
  if (!weekBuilt) buildWeek(s.week);
  document.querySelectorAll("#weekGrid .cell.now").forEach((c) => c.classList.remove("now"));
  const cur = document.querySelector('#weekGrid .cell[data-d="' + s.curDay + '"][data-h="' + s.curHour + '"]');
  if (cur) cur.classList.add("now");
  $("tzNote").textContent = s.tzDifferent
    ? "Décision toujours en heure de Pékin (≠ fuseau local)"
    : "Fuseau local = heure de Pékin";
  $("beijingDate").textContent = s.beijingDate;
  $("ver").textContent = "v" + s.version;
  document.querySelectorAll("#pills button").forEach((b) => {
    b.classList.toggle("active", (b.dataset.mode || null) === s.preview);
  });
  $("previewBanner").hidden = !s.preview;
  const lt = $("loginToggle");
  if (lt.checked !== s.launchAtLogin) lt.checked = s.launchAtLogin;
};

document.addEventListener("DOMContentLoaded", () => {
  const api = () => (window.pywebview ? pywebview.api : null);
  $("closeBtn").addEventListener("click", () => { const a = api(); if (a) a.close_panel(); });
  $("exitPreview").addEventListener("click", () => { const a = api(); if (a) a.set_preview(""); });
  document.querySelectorAll("#pills button").forEach((b) =>
    b.addEventListener("click", () => { const a = api(); if (a) a.set_preview(b.dataset.mode); }));
  $("loginToggle").addEventListener("change", (e) => {
    const a = api(); if (a) a.set_launch_at_login(e.target.checked);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { const a = api(); if (a) a.close_panel(); }
  });
});
