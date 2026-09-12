"use strict";
window.__APP_JS_VERSION = 3;  // cache-busting diagnostic
const $ = (id) => document.getElementById(id);

/* Official DeepSeek whale SVG path (injected by Python from assets/whale_path.txt). */
window.__setWhale = function (p) {
  $("whalePath").setAttribute("d", p);
};

let weekBuilt = false;
function buildWeek(week) {
  const grid = $("weekGrid");
  const col = $("dayCol");
  grid.innerHTML = "";
  col.innerHTML = "";
  const days = ["M", "T", "W", "T", "F", "S", "S"];
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

/* State pushed every second by Python (single source of truth). */
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
  $("progressMeta").textContent = s.blockPct + "% of the current block elapsed";
  $("beijingClock").textContent = s.beijingClock;
  if (!weekBuilt) buildWeek(s.week);
  document.querySelectorAll("#weekGrid .cell.now").forEach((c) => c.classList.remove("now"));
  const cur = document.querySelector('#weekGrid .cell[data-d="' + s.curDay + '"][data-h="' + s.curHour + '"]');
  if (cur) cur.classList.add("now");
  $("tzNote").textContent = s.tzDifferent
    ? "Always decided in Beijing time (≠ local timezone)"
    : "Local timezone = Beijing time";
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

  /* Hide the panel as soon as it loses focus: the tray whale keeps running
     in the background and clicking it brings the panel back. */
  window.addEventListener("blur", () => {
    const a = api();
    if (a) a.close_panel();
  });

  /* The ◢ grip starts a page-driven resize (Python tracks the real cursor,
     so it works in and outside the window with live feedback). The 8 px
     window bands stay native-only on purpose: a single driver at a time. */
  const grip = $("grip");
  if (grip) grip.addEventListener("mousedown", (e) => {
    e.preventDefault();
    const a = api();
    if (a) a.begin_resize();
  });
});
