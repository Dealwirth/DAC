/**
 * DAC – Dynamic Alarm Clock
 * Eigenes Home-Assistant-Panel (kein Lovelace): Vanilla Web-Component.
 *
 * Nutzt ausschließlich die DAC-HTTP-API (/api/dac) und hass.callApi().
 */
class DacPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._data = null;
    this._timer = null;
    this._busy = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._data) {
      this._refresh();
    } else {
      this._render();
    }
  }

  connectedCallback() {
    this._render();
    this._timer = setInterval(() => this._refresh(), 15000);
    this._refresh();
  }

  disconnectedCallback() {
    if (this._timer) clearInterval(this._timer);
  }

  async _refresh() {
    if (!this._hass || this._busy) return;
    this._busy = true;
    try {
      this._data = await this._hass.callApi("GET", "dac");
      this._render();
    } catch (err) {
      this._renderError(String(err && err.message ? err.message : err));
    } finally {
      this._busy = false;
    }
  }

  async _action(body) {
    try {
      await this._hass.callApi("POST", "dac", body);
      await this._refresh();
    } catch (err) {
      alert("DAC: Aktion fehlgeschlagen: " + (err && err.message ? err.message : err));
    }
  }

  _renderError(message) {
    this.shadowRoot.innerHTML = `
      <style>${STYLES}</style>
      <div class="wrap"><div class="card error">⚠ DAC-Fehler: ${_esc(message)}</div></div>`;
  }

  _render() {
    const d = this._data;
    if (!d || !d.entries || !d.entries.length) {
      this.shadowRoot.innerHTML = `
        <style>${STYLES}</style>
        <div class="wrap"><div class="card">DAC ist noch nicht eingerichtet.</div></div>`;
      return;
    }
    const e = d.entries[0];
    const status = _statusInfo(e);
    const target = e.alarm_target ? new Date(e.alarm_target) : null;
    const targetStr = target
      ? target.toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" }) +
        " · " +
        target.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })
      : "—";
    const countdown = target ? _countdown(target) : null;
    const ringing = e.state === "ringing";

    this.shadowRoot.innerHTML = `
      <style>${STYLES}</style>
      <div class="wrap">
        <div class="hero ${ringing ? "ringing" : ""}">
          <div class="hero-top">
            <span class="brand">⏰ DAC</span>
            <span class="mode-chip mode-${e.mode}">${_modeLabel(e.mode)}</span>
          </div>
          <div class="clock">${_clockNow()}</div>
          <div class="status">${status.emoji} ${status.label}</div>
          <div class="target">
            <div class="target-main">${e.alarm_time ? e.alarm_time.slice(0, 5) : "--:--"}</div>
            <div class="target-sub">${targetStr}${countdown ? ` · in ${countdown}` : ""}</div>
          </div>
          ${ringing ? `<button class="btn big stop" id="stop">⛔ WECKER STOPPEN</button>` : ""}
        </div>

        <div class="card">
          <h3>Arbeitsbeginn setzen</h3>
          <div class="row">
            <input type="time" id="worktime" value="${_inputTime(e.work_time)}" />
            <button class="btn" id="setwork">Setzen</button>
            <button class="btn ghost" id="clearwork">Zurücksetzen</button>
          </div>
          <div class="hint">
            Weckzeit = Arbeitsbeginn − ${e.offset_minutes} min.
            ${
              e.work_time
                ? `Aktuell gesetzt: <b>${e.work_time.slice(0, 5)}</b> Uhr (${e.work_time_day || "heute"})`
                : `Kein Arbeitsbeginn gesetzt – Fallback: <b>${(e.default_alarm_time || "").slice(0, 5)}</b> Uhr`
            }
          </div>
        </div>

        <div class="grid2">
          <div class="card">
            <h3>Modus</h3>
            <div class="modes">
              <button class="btn ${e.mode === "standard" ? "active" : ""}" data-mode="standard">Standard</button>
              <button class="btn ${e.mode === "dismissed" ? "active" : ""}" data-mode="dismissed">Heute aus</button>
              <button class="btn ${e.mode === "vacation" ? "active" : ""}" data-mode="vacation">Urlaub</button>
            </div>
            <button class="btn ghost wide" id="dismiss">Für heute deaktivieren</button>
          </div>
          <div class="card">
            <h3>Urlaub eintragen</h3>
            <div class="row">
              <input type="date" id="vacstart" />
              <input type="date" id="vacend" />
            </div>
            <div class="row">
              <input type="text" id="vacsummary" placeholder="z. B. Urlaub / Feiertag" />
              <button class="btn" id="addvac">Hinzufügen</button>
            </div>
            <div class="events">
              ${
                (e.vacation_events || []).length === 0
                  ? `<div class="hint">Keine geplanten Urlaubstage (nächste 14 Tage).</div>`
                  : (e.vacation_events || [])
                      .map(
                        (ev) => `
                    <div class="event">
                      <span>${_esc(ev.summary)}</span>
                      <span class="event-date">${_fmtRange(ev.start, ev.end)}</span>
                      <button class="btn tiny danger" data-uid="${_esc(ev.uid)}">✕</button>
                    </div>`
                      )
                      .join("")
              }
            </div>
          </div>
        </div>

        <div class="footer">DAC – Dynamic Alarm Clock · eigenes Panel, kein Lovelace-Dashboard</div>
      </div>`;

    // --- wiring -----------------------------------------------------------
    const q = (sel) => this.shadowRoot.querySelector(sel);
    q("#setwork").addEventListener("click", () => {
      const value = q("#worktime").value;
      if (value) this._action({ action: "set_work_time", time: value });
    });
    q("#clearwork").addEventListener("click", () =>
      this._action({ action: "set_work_time", clear: true })
    );
    q("#dismiss").addEventListener("click", () => this._action({ action: "dismiss" }));
    const stopBtn = q("#stop");
    if (stopBtn) stopBtn.addEventListener("click", () => this._action({ action: "stop" }));
    this.shadowRoot.querySelectorAll("[data-mode]").forEach((btn) =>
      btn.addEventListener("click", () =>
        this._action({ action: "mode", mode: btn.dataset.mode })
      )
    );
    q("#addvac").addEventListener("click", () => {
      const start = q("#vacstart").value;
      const end = q("#vacend").value || start;
      const summary = q("#vacsummary").value || "Urlaub";
      if (!start) return alert("Bitte ein Startdatum wählen.");
      this._action({
        action: "add_vacation",
        start: `${start}T00:00:00`,
        end: `${end}T23:59:59`,
        summary,
      });
    });
    this.shadowRoot.querySelectorAll("[data-uid]").forEach((btn) =>
      btn.addEventListener("click", () =>
        this._action({ action: "remove_vacation", uid: btn.dataset.uid })
      )
    );
  }
}

function _statusInfo(e) {
  if (e.vacation) return { emoji: "🏖️", label: "Urlaub / Feiertag – Wecker aus" };
  switch (e.state) {
    case "ringing":
      return { emoji: "⏰", label: "WECKT GERADE" };
    case "scheduled":
      return { emoji: "✅", label: "Wecker gestellt" };
    case "stopped":
      return { emoji: "🛑", label: "Gestoppt" };
    case "dismissed":
      return { emoji: "😴", label: "Deaktiviert" };
    case "vacation":
      return { emoji: "🏖️", label: "Urlaub / Feiertag" };
    default:
      return { emoji: "🕓", label: "Warte auf Eingabe" };
  }
}

function _modeLabel(mode) {
  return { standard: "Standard", dismissed: "Heute aus", vacation: "Urlaub" }[mode] || mode;
}

function _clockNow() {
  return new Date().toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
}

function _countdown(target) {
  const diff = target - new Date();
  if (diff <= 0) return null;
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  return h > 0 ? `${h} h ${m} min` : `${m} min`;
}

function _inputTime(value) {
  return value ? String(value).slice(0, 5) : "";
}

function _fmtRange(start, end) {
  const s = new Date(start);
  const e = new Date(end);
  const opts = { day: "2-digit", month: "2-digit" };
  return `${s.toLocaleDateString("de-DE", opts)} – ${e.toLocaleDateString("de-DE", opts)}`;
}

function _esc(text) {
  const div = document.createElement("div");
  div.textContent = String(text ?? "");
  return div.innerHTML;
}

const STYLES = `
  :host { all: initial; }
  .wrap {
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    max-width: 720px; margin: 0 auto; padding: 16px;
    color: var(--primary-text-color, #eee);
    background: var(--primary-background-color, #111);
    min-height: 100vh; box-sizing: border-box;
  }
  .hero {
    background: linear-gradient(135deg, #1a237e, #283593);
    border-radius: 20px; padding: 28px; text-align: center; margin-bottom: 16px;
  }
  .hero.ringing { background: linear-gradient(135deg, #b71c1c, #e53935); animation: pulse 1.2s infinite; }
  @keyframes pulse { 50% { filter: brightness(1.25); } }
  .hero-top { display: flex; justify-content: space-between; align-items: center; }
  .brand { font-weight: 700; letter-spacing: 2px; }
  .mode-chip { background: rgba(255,255,255,.18); padding: 4px 12px; border-radius: 999px; font-size: 13px; }
  .clock { font-size: 64px; font-weight: 200; margin: 18px 0 4px; font-variant-numeric: tabular-nums; }
  .status { opacity: .85; margin-bottom: 18px; }
  .target-main { font-size: 44px; font-weight: 600; }
  .target-sub { opacity: .75; font-size: 14px; }
  .card {
    background: var(--card-background-color, #1c1c1c);
    border-radius: 14px; padding: 16px; margin-bottom: 16px;
  }
  .card h3 { margin: 0 0 12px; font-size: 15px; font-weight: 600; opacity: .9; }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 640px) { .grid2 { grid-template-columns: 1fr; } }
  .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  input {
    background: var(--secondary-background-color, #262626); color: inherit;
    border: 1px solid rgba(255,255,255,.12); border-radius: 8px; padding: 9px 10px; font-size: 15px;
  }
  .btn {
    background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff);
    border: none; border-radius: 8px; padding: 9px 14px; font-size: 14px; cursor: pointer; font-weight: 600;
  }
  .btn:hover { filter: brightness(1.1); }
  .btn.ghost { background: transparent; border: 1px solid rgba(255,255,255,.25); }
  .btn.active { outline: 2px solid var(--primary-color, #03a9f4); }
  .btn.big { font-size: 18px; padding: 14px 22px; margin-top: 12px; }
  .btn.stop { background: #fff; color: #b71c1c; }
  .btn.tiny { padding: 2px 8px; font-size: 12px; }
  .btn.danger { background: #b71c1c; }
  .btn.wide { width: 100%; margin-top: 10px; }
  .modes { display: flex; gap: 8px; flex-wrap: wrap; }
  .hint { font-size: 13px; opacity: .7; margin-top: 10px; }
  .events { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }
  .event { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-size: 14px; }
  .event-date { opacity: .6; font-size: 12px; }
  .error { background: #b71c1c; }
  .footer { text-align: center; opacity: .45; font-size: 12px; margin-top: 8px; }
`;

customElements.define("dac-panel", DacPanel);
