/**
 * DAC – Dynamic Alarm Clock · Lovelace Card ("custom:dac-wecker")
 * Simpel & perfekt: Uhr + Countdown, Arbeitsbeginn, Alexa-Helfer-Status,
 * Modus & Stopp – als native Lovelace-Karte in JEDEM Dashboard.
 */
class DacWeckerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._data = null;
    this._timer = null;
    this._clockTimer = null;
    this._busy = false;
  }

  setConfig() { /* no config needed */ }

  getCardSize() { return 4; }

  static getStubConfig() {
    return { type: "custom:dac-wecker" };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._data) this._refresh();
    else this._render();
  }

  connectedCallback() {
    this._render();
    this._timer = setInterval(() => this._refresh(), 15000);
    this._clockTimer = setInterval(() => {
      const el = this.shadowRoot.querySelector(".clock");
      if (el) el.textContent = _clockNow();
    }, 1000);
  }

  disconnectedCallback() {
    if (this._timer) clearInterval(this._timer);
    if (this._clockTimer) clearInterval(this._clockTimer);
  }

  async _refresh() {
    if (!this._hass || this._busy) return;
    this._busy = true;
    try {
      this._data = await this._hass.callApi("GET", "dac");
      this._render();
    } catch (err) {
      this.shadowRoot.innerHTML =
        `<style>${CARD_STYLES}</style><ha-card><div class="pad err">⚠ DAC: ${_esc(_msg(err))}</div></ha-card>`;
    } finally {
      this._busy = false;
    }
  }

  async _action(body) {
    try {
      await this._hass.callApi("POST", "dac", body);
      await this._refresh();
    } catch (err) {
      alert("DAC: " + _msg(err));
    }
  }

  _render() {
    const d = this._data;
    if (!d || !d.entries || !d.entries.length) {
      this.shadowRoot.innerHTML =
        `<style>${CARD_STYLES}</style><ha-card><div class="pad">DAC ist noch nicht eingerichtet.</div></ha-card>`;
      return;
    }
    const e = d.entries[0];
    const st = _statusInfo(e);
    const target = e.alarm_target ? new Date(e.alarm_target) : null;
    const countdown = target ? _countdown(target) : null;
    const ringing = e.state === "ringing";
    const alexa = e.alexa || {};
    const alexaParts = [];
    if (alexa.enabled) {
      alexaParts.push(alexa.stored_alarm ? `Alexa-Wecker: ${alexa.stored_alarm} Uhr` : "Kein Alexa-Wecker gesetzt");
      if (alexa.helper_ok === false) alexaParts.push("⚠ Helfer fehlt (input_text.gestellter_alexa_wecker)");
      if (alexa.gate_ok === false) alexaParts.push("⚠ Helfer fehlt (input_boolean.wecker_aktiv)");
    }

    this.shadowRoot.innerHTML = `
      <style>${CARD_STYLES}</style>
      <ha-card class="${ringing ? "ringing" : ""}">
        <div class="hero">
          <div class="row-top">
            <span class="brand">⏰ DAC</span>
            <span class="chip">${_modeLabel(e.mode)}</span>
          </div>
          <div class="clock">${_clockNow()}</div>
          <div class="status">${st.emoji} ${st.label}</div>
          <div class="alarm-line">
            <span class="big">${e.alarm_time ? e.alarm_time.slice(0, 5) : "--:--"}</span>
            <span class="sub">${countdown ? `in ${countdown}` : "kein Wecker aktiv"}</span>
          </div>
          ${ringing ? `<button class="btn stop" id="stop">⛔ WECKER STOPPEN</button>` : ""}
        </div>
        <div class="pad">
          <div class="lbl">Arbeitsbeginn</div>
          <div class="row">
            <input type="time" id="worktime" value="${_inputTime(e.work_time)}" />
            <button class="btn" id="setwork">Setzen</button>
            <button class="btn ghost" id="clearwork">✕</button>
          </div>
          <div class="hint">
            Weckzeit = Arbeitsbeginn − ${e.offset_minutes} min.
            ${e.work_time
              ? `Gesetzt: <b>${e.work_time.slice(0, 5)}</b> Uhr${e.work_time_day ? ` (${e.work_time_day})` : ""}`
              : `Fallback: <b>${(e.default_alarm_time || "").slice(0, 5)}</b> Uhr`}
          </div>
          ${alexaParts.length ? `<div class="hint alexa">${alexaParts.map(_esc).join(" · ")}</div>` : ""}
          <div class="lbl" style="margin-top:14px">Modus</div>
          <div class="modes">
            <button class="btn ${e.mode === "standard" ? "active" : ""}" data-mode="standard">Standard</button>
            <button class="btn ${e.mode === "dismissed" ? "active" : ""}" data-mode="dismissed">Heute aus</button>
            <button class="btn ${e.mode === "vacation" ? "active" : ""}" data-mode="vacation">Urlaub</button>
          </div>
        </div>
      </ha-card>`;

    const q = (sel) => this.shadowRoot.querySelector(sel);
    q("#setwork").addEventListener("click", () => {
      const value = q("#worktime").value;
      if (value) this._action({ action: "set_work_time", time: value });
    });
    q("#clearwork").addEventListener("click", () => this._action({ action: "set_work_time", clear: true }));
    const stopBtn = q("#stop");
    if (stopBtn) stopBtn.addEventListener("click", () => this._action({ action: "stop" }));
    this.shadowRoot.querySelectorAll("[data-mode]").forEach((btn) =>
      btn.addEventListener("click", () => this._action({ action: "mode", mode: btn.dataset.mode }))
    );
  }
}

/* ---- shared helpers (same look & logic as the sidebar panel) ---- */
function _statusInfo(e) {
  if (e.vacation) return { emoji: "🏖️", label: "Urlaub / Feiertag – Wecker aus" };
  switch (e.state) {
    case "ringing": return { emoji: "⏰", label: "WECKT GERADE" };
    case "scheduled": return { emoji: "✅", label: "Wecker gestellt" };
    case "stopped": return { emoji: "🛑", label: "Gestoppt" };
    case "dismissed": return { emoji: "😴", label: "Deaktiviert" };
    case "vacation": return { emoji: "🏖️", label: "Urlaub / Feiertag" };
    default: return { emoji: "🕓", label: "Warte auf Eingabe" };
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
function _msg(err) {
  return String(err && err.message ? err.message : err);
}
function _esc(text) {
  const div = document.createElement("div");
  div.textContent = String(text ?? "");
  return div.innerHTML;
}

const CARD_STYLES = `
  :host { display: block; }
  ha-card { overflow: hidden; }
  .hero {
    background: linear-gradient(135deg, #1a237e, #283593);
    padding: 18px; text-align: center; color: #fff;
  }
  ha-card.ringing .hero { background: linear-gradient(135deg, #b71c1c, #e53935); animation: pulse 1.2s infinite; }
  @keyframes pulse { 50% { filter: brightness(1.25); } }
  .row-top { display: flex; justify-content: space-between; align-items: center; }
  .brand { font-weight: 700; letter-spacing: 2px; font-size: 13px; }
  .chip { background: rgba(255,255,255,.18); padding: 3px 10px; border-radius: 999px; font-size: 12px; }
  .clock { font-size: 46px; font-weight: 200; margin: 8px 0 2px; font-variant-numeric: tabular-nums; }
  .status { opacity: .85; font-size: 13px; margin-bottom: 8px; }
  .alarm-line { display: flex; align-items: baseline; justify-content: center; gap: 10px; }
  .big { font-size: 38px; font-weight: 600; }
  .sub { opacity: .75; font-size: 13px; }
  .pad { padding: 14px 16px 16px; }
  .lbl { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; opacity: .55; margin-bottom: 6px; }
  .row { display: flex; gap: 8px; align-items: center; }
  input {
    flex: 1; background: var(--secondary-background-color, #262626); color: inherit;
    border: 1px solid rgba(255,255,255,.12); border-radius: 8px; padding: 8px 10px; font-size: 15px;
    min-width: 0;
  }
  .btn {
    background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff);
    border: none; border-radius: 8px; padding: 8px 12px; font-size: 13px; cursor: pointer; font-weight: 600;
  }
  .btn:hover { filter: brightness(1.1); }
  .btn.ghost { background: transparent; border: 1px solid rgba(255,255,255,.25); padding: 8px 10px; }
  .btn.active { outline: 2px solid var(--primary-color, #03a9f4); }
  .btn.stop { background: #fff; color: #b71c1c; font-size: 15px; padding: 12px 20px; margin-top: 10px; width: 90%; }
  .modes { display: flex; gap: 8px; flex-wrap: wrap; }
  .hint { font-size: 12px; opacity: .7; margin-top: 8px; }
  .hint.alexa { color: var(--warning-color, #ffa726); opacity: 1; }
  .err { background: #b71c1c; color: #fff; }
`;

customElements.define("dac-wecker-card", DacWeckerCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "dac-wecker-card",
  name: "DAC Wecker",
  description: "Dynamic Alarm Clock – Arbeitsbeginn, Weckzeit, Alexa-Status und Modus in einer Karte.",
});
