"use strict";
window.__APP_JS_VERSION = 5;  // + balance card
const $ = (id) => document.getElementById(id);

/* Official DeepSeek whale SVG path (pulled from Python). */
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

/* Account balance card. `editing` keeps the key editor open across pulls. */
let editing = false;
function renderBalance(bal) {
  bal = bal || {};
  const act = $("balanceAction"), body = $("balanceBody"), err = $("balanceErr"),
        ed = $("keyEditor"), inp = $("keyInput"), rem = $("keyRemove");
  ed.hidden = !editing;
  inp.hidden = !editing;
  rem.hidden = !editing || !bal.hasKey;
  act.textContent = bal.hasKey ? "Change key" : "Enter API key";
  err.hidden = !bal.error || editing;
  if (!err.hidden) err.textContent = (bal.suggestsRekey ? "\u26A0 " : "") + bal.error;
  const show = bal.hasKey && !editing;
  body.hidden = !show;
  if (show) {
    const rows = $("balanceRows");
    rows.innerHTML = "";
    if (bal.state === "loading" && !bal.infos.length) {
      const d = document.createElement("div");
      d.className = "bal-load"; d.textContent = "Loading\u2026";
      rows.appendChild(d);
    } else {
      bal.infos.forEach((i) => {
        const d = document.createElement("div"); d.className = "bal-row";
        const a = document.createElement("span"); a.className = "bal-amount";
        a.textContent = i.symbol + i.total;
        const sp = document.createElement("span"); sp.className = "bal-split";
        sp.textContent = "\u2014 " + i.currency + " \u00B7 granted " + i.symbol + i.granted
          + " \u00B7 topped-up " + i.symbol + i.toppedUp;
        d.appendChild(a); d.appendChild(sp); rows.appendChild(d);
      });
      if (bal.infos.length && bal.isAvailable === false) {
        const w = document.createElement("div"); w.className = "bal-warn";
        w.textContent = "Balance exhausted \u2014 API calls will fail.";
        rows.appendChild(w);
      }
      const ft = $("balanceTime");
      ft.textContent = bal.lastOk ? "updated " + bal.lastOk : "never refreshed";
    }
  }
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
  renderBalance(s.balance);
  const lt = $("loginToggle");
  if (lt.checked !== s.launchAtLogin) lt.checked = s.launchAtLogin;
};

document.addEventListener("DOMContentLoaded", () => {
  const api = () => (window.pywebview ? pywebview.api : null);

  /* Pull the whale path once, then the full state every second.
     While the window is hidden, WebView2 never delivers API replies, so we
     must NOT touch the API then: the calls would pile up and wedge the
     bridge (this froze the clock). Resume instantly on show. */
  function boot() {
    const a = api();
    if (!a) { setTimeout(boot, 250); return; }
    if (typeof a.get_whale === "function" && !document.hidden) {
      Promise.resolve(a.get_whale()).then((p) => { if (p) window.__setWhale(p); })
        .catch(() => {});
    }
    tick();
    setInterval(tick, 1000);
  }
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) tick();
  });
  function tick() {
    if (document.hidden) return;
    const a = api();
    if (!a || typeof a.get_state !== "function") return;
    Promise.resolve(a.get_state()).then((s) => {
      if (s && s.version) window.__update(s);
    }).catch(() => {});
  }
  boot();

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

  /* ---- balance / API key editor ---- */
  $("balanceAction").addEventListener("click", () => { editing = true; renderBalance(window.__state && window.__state.balance); });
  $("balanceRefresh").addEventListener("click", () => { const a = api(); if (a) a.refresh_balance(); });
  $("keyCancel").addEventListener("click", () => { editing = false; $("keyInput").value = ""; renderBalance(window.__state && window.__state.balance); });
  $("keySave").addEventListener("click", saveKey);
  $("keyRemove").addEventListener("click", () => {
    const a = api();
    if (!a) return;
    Promise.resolve(a.remove_api_key()).then(() => {
      editing = false; $("keyInput").value = "";
    });
  });
  $("keyInput").addEventListener("keydown", (e) => { if (e.key === "Enter") saveKey(); });
  function saveKey() {
    const a = api();
    const v = $("keyInput").value.trim();
    if (!a || !v) return;
    $("keySave").disabled = true;
    Promise.resolve(a.set_api_key(v)).then((ok) => {
      $("keySave").disabled = false;
      if (ok) { editing = false; $("keyInput").value = ""; }
      else { $("keyInput").placeholder = "Could not save (Credential Manager refused). Try again."; }
    }).catch(() => { $("keySave").disabled = false; });
  }

  /* Hide the panel as soon as it loses focus — EXCEPT while editing the key
     (the input's context menu / paste flow can fire a spurious blur). */
  window.addEventListener("blur", () => {
    if (editing) return;
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
