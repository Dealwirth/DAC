/**
 * DAC – Dynamic Alarm Clock · Lovelace-Karte (custom:dac-wecker)
 *
 * Vollwertige Wecker-Oberfläche im Amazon-/Alexa-Look: Uhr, Countdown,
 * Arbeitsbeginn, Modus, Alexa-Status und Urlaubsverwaltung. Nutzt
 * ausschließlich die DAC-HTTP-API über hass.callApi("GET"|"POST", "dac").
 *
 * Das Element ist als <dac-wecker> registriert, damit der Lovelace-Typ
 * `custom:dac-wecker` korrekt aufgelöst wird.
 */
const DAC_CARD_VERSION = "0.3.0";

function dacEsc(value) {
  const div = document.createElement("div");
  div.textContent = String(value ?? "");
  return div.innerHTML;
}

function dacMsg(err) {
  if (!err) return "Unbekannter Fehler";
  if (typeof err === "string") return err;
  if (err.message) return err.message;
  if (err.body && err.body.message) return err.body.message;
  return "Aktion fehlgeschlagen";
}

function dacClockNow() {
  return new Date().toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
}

function dacCountdown(value) {
  const target = value ? new Date(value) : null;
  if (!target) return null;
  const diff = target.getTime() - Date.now();
  if (diff <= 0) return null;
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  const s = Math.floor((diff % 60000) / 1000);
  if (h > 0) return `${h} h ${m} min`;
  if (m > 0) return `${m} min ${s} s`;
  return `${s} s`;
}

function dacHm(value) {
  return value ? String(value).slice(0, 5) : "--:--";
}

function dacTimeOf(value) {
  if (!value) return "--:--";
  return new Date(value).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
}

function dacHmInput(value) {
  return value ? String(value).slice(0, 5) : "";
}

function dacDateLabel(value) {
  if (!value) return "";
  const d = new Date(value);
  return d.toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" });
}

function dacModeLabel(mode) {
  return { standard: "Standard", dismissed: "Heute aus", vacation: "Urlaub" }[mode] || mode || "—";
}

function dacStatus(entry) {
  if (entry.vacation) return { emoji: "🏖️", label: "Urlaub / Feiertag", tone: "vacation" };
  switch (entry.state) {
    case "ringing": return { emoji: "⏰", label: "WECKT GERADE", tone: "ringing" };
    case "scheduled": return { emoji: "✅", label: "Wecker gestellt", tone: "scheduled" };
    case "stopped": return { emoji: "🛑", label: "Gestoppt", tone: "stopped" };
    case "dismissed": return { emoji: "😴", label: "Heute deaktiviert", tone: "dismissed" };
    case "vacation": return { emoji: "🏖️", label: "Urlaub / Feiertag", tone: "vacation" };
    default: return { emoji: "🕓", label: "Warte auf Arbeitszeit", tone: "idle" };
  }
}

function dacRange(start, end) {
  const fmt = (v) => new Date(v).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
  try {
    return `${fmt(start)} – ${fmt(end)}`;
  } catch (err) {
    return "";
  }
}

class DacWeckerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._data = null;
    this._error = null;
    this._busy = false;
    this._entry = 0;
    this._poll = null;
    this._clock = null;
  }

  setConfig() { /* no configuration needed */ }

  getCardSize() { return 6; }

  static getStubConfig() {
    return { type: "custom:dac-wecker" };
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    // Re-rendering on every hass state change would thrash the DOM (and wipe
    // any input the user is typing). Initial paint only; the 10 s poll and the
    // 1 s clock interval keep the card fresh afterwards.
    if (!first) return;
    if (!this._data && !this._error) {
      this._refresh();
    } else {
      this._render();
    }
  }

  _countdownText(entry) {
    if (!entry) return "kein Wecker aktiv";
    if (entry.state === "ringing") return "jetzt";
    return dacCountdown(entry.alarm_target) || "kein Wecker aktiv";
  }

  connectedCallback() {
    this._render();
    this._poll = setInterval(() => this._refresh(), 10000);
    this._clock = setInterval(() => {
      const el = this.shadowRoot.querySelector(".dac-clock");
      if (el) el.textContent = dacClockNow();
      const cd = this.shadowRoot.querySelector(".dac-countdown");
      if (cd) cd.textContent = this._countdownText(this._entryData());
    }, 1000);
  }

  disconnectedCallback() {
    if (this._poll) clearInterval(this._poll);
    if (this._clock) clearInterval(this._clock);
  }

  _entries() {
    return (this._data && this._data.entries) || [];
  }

  _entryData() {
    const entries = this._entries();
    if (!entries.length) return null;
    return entries[Math.min(this._entry, entries.length - 1)];
  }

  async _refresh() {
    if (!this._hass || this._busy) return;
    this._busy = true;
    try {
      this._data = await this._hass.callApi("GET", "dac");
      this._error = null;
    } catch (err) {
      this._error = dacMsg(err);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _action(body) {
    if (!this._hass) return;
    const entry = this._entryData();
    if (entry && entry.entry_id) body.entry_id = entry.entry_id;
    try {
      await this._hass.callApi("POST", "dac", body);
    } catch (err) {
      this._error = dacMsg(err);
    }
    await this._refresh();
  }

  _render() {
    if (this._error) {
      this.shadowRoot.innerHTML =
        `<style>${DAC_STYLES}</style>
         <ha-card><div class="dac-error">⚠️ DAC: ${dacEsc(this._error)}</div></ha-card>`;
      return;
    }
    const entry = this._entryData();
    if (!entry) {
      this.shadowRoot.innerHTML =
        `<style>${DAC_STYLES}</style>
         <ha-card><div class="dac-pad dac-empty">DAC ist noch nicht eingerichtet.<br>
         <span class="dac-hint">Einstellungen → Geräte &amp; Dienste → Integration hinzufügen → „DAC“.</span></div></ha-card>`;
      return;
    }

    const status = dacStatus(entry);
    const ringing = entry.state === "ringing";
    const alexa = entry.alexa || {};
    const countdown = this._countdownText(entry);
    const targetLine = entry.alarm_target
      ? `${dacDateLabel(entry.alarm_target)} · ${new Date(entry.alarm_target).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}`
      : "Kein Weckzeitpunkt berechnet";

    const entryTabs = this._entries().length > 1
      ? `<div class="dac-tabs">${this._entries()
          .map((e, i) => `<button class="dac-tab ${i === this._entry ? "active" : ""}" data-entry="${i}">${dacEsc(dacModeLabel(e.mode))}</button>`)
          .join("")}</div>`
      : "";

    this.shadowRoot.innerHTML = `
      <style>${DAC_STYLES}</style>
      <ha-card class="dac-card ${ringing ? "ringing" : ""}">
        <div class="dac-hero tone-${status.tone}">
          <div class="dac-top">
            <span class="dac-brand">⏰ DAC</span>
            <span class="dac-chip">${dacEsc(dacModeLabel(entry.mode))}</span>
          </div>
          <div class="dac-clock">${dacClockNow()}</div>
          <div class="dac-status">${status.emoji} ${dacEsc(status.label)}</div>
          <div class="dac-alarm">
            <span class="dac-alarm-big">${dacTimeOf(entry.alarm_target)}</span>
            <span class="dac-countdown">${dacEsc(countdown)}</span>
          </div>
          <div class="dac-target">${dacEsc(targetLine)}</div>
          ${ringing ? `<button class="dac-btn dac-stop" id="stop">⛔ WECKER STOPPEN</button>` : ""}
        </div>

        <div class="dac-pad">
          <div class="dac-lbl">Arbeitsbeginn</div>
          <div class="dac-row">
            <input class="dac-input" type="time" id="worktime" value="${dacEsc(dacHmInput(entry.work_time))}" />
            <button class="dac-btn" id="setwork">Setzen</button>
            <button class="dac-btn ghost" id="clearwork" title="Arbeitszeit zurücksetzen">✕</button>
          </div>
          <div class="dac-hint">
            Weckzeit = Arbeitsbeginn − ${dacEsc(entry.offset_minutes)} min.
            ${entry.work_time
              ? `Gesetzt: <b>${dacHm(entry.work_time)}</b> Uhr${entry.work_time_day ? ` (${dacEsc(entry.work_time_day)})` : ""}`
              : `Fallback: <b>${dacHm(entry.default_alarm_time)}</b> Uhr`}
          </div>
          ${alexa.enabled ? this._alexaHint(alexa) : ""}

          <div class="dac-lbl spaced">Modus</div>
          <div class="dac-modes">
            <button class="dac-btn ${entry.mode === "standard" ? "active" : ""}" data-mode="standard">Standard</button>
            <button class="dac-btn ${entry.mode === "dismissed" ? "active" : ""}" data-mode="dismissed">Heute aus</button>
            <button class="dac-btn ${entry.mode === "vacation" ? "active" : ""}" data-mode="vacation">Urlaub</button>
          </div>

          <details class="dac-vac">
            <summary>Urlaubstage verwalten</summary>
            <div class="dac-row dac-vac-form">
              <input class="dac-input" type="date" id="vacstart" />
              <input class="dac-input" type="date" id="vacend" />
            </div>
            <div class="dac-row">
              <input class="dac-input" type="text" id="vacsummary" placeholder="Urlaub / Feiertag" />
              <button class="dac-btn" id="addvac">Hinzufügen</button>
            </div>
            <div class="dac-events">
              ${(entry.vacation_events || []).length === 0
                ? `<div class="dac-hint">Keine Urlaubstage in den nächsten 14 Tagen.</div>`
                : (entry.vacation_events || [])
                    .map((ev) => `
                      <div class="dac-event">
                        <span class="dac-event-name">${dacEsc(ev.summary)}</span>
                        <span class="dac-event-date">${dacEsc(dacRange(ev.start, ev.end))}</span>
                        <button class="dac-btn tiny danger" data-uid="${dacEsc(ev.uid)}">✕</button>
                      </div>`)
                    .join("")}
            </div>
          </details>
        </div>
        ${entryTabs}
      </ha-card>`;

    this._wire();
  }

  _alexaHint(alexa) {
    const parts = [];
    parts.push(alexa.stored_alarm
      ? `🔊 Alexa-Wecker: ${dacEsc(alexa.stored_alarm)} Uhr`
      : "Kein Alexa-Wecker gesetzt");
    if (alexa.player_ok === false) parts.push("⚠️ Echo-Player nicht verfügbar");
    if (alexa.helper_ok === false) parts.push("⚠️ Helfer input_text.gestellter_alexa_wecker fehlt");
    if (alexa.gate_ok === false) parts.push("⚠️ Helfer input_boolean.wecker_aktiv fehlt");
    return `<div class="dac-hint alexa">${parts.join(" · ")}</div>`;
  }

  _wire() {
    const q = (sel) => this.shadowRoot.querySelector(sel);
    const setwork = q("#setwork");
    if (setwork) setwork.addEventListener("click", () => {
      const value = q("#worktime").value;
      if (value) this._action({ action: "set_work_time", time: value });
    });
    const clearwork = q("#clearwork");
    if (clearwork) clearwork.addEventListener("click", () => this._action({ action: "set_work_time", clear: true }));
    const stop = q("#stop");
    if (stop) stop.addEventListener("click", () => this._action({ action: "stop" }));
    this.shadowRoot.querySelectorAll("[data-mode]").forEach((btn) =>
      btn.addEventListener("click", () => this._action({ action: "mode", mode: btn.dataset.mode })));

    const addvac = q("#addvac");
    if (addvac) addvac.addEventListener("click", () => {
      const start = q("#vacstart").value;
      const end = q("#vacend").value || start;
      const summary = q("#vacsummary").value || "Urlaub";
      if (!start) {
        this._error = "Bitte ein Startdatum wählen.";
        this._render();
        return;
      }
      this._action({ action: "add_vacation", start: `${start}T00:00:00`, end: `${end}T23:59:59`, summary });
    });
    this.shadowRoot.querySelectorAll("[data-uid]").forEach((btn) =>
      btn.addEventListener("click", () => this._action({ action: "remove_vacation", uid: btn.dataset.uid })));
    this.shadowRoot.querySelectorAll("[data-entry]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._entry = Number(btn.dataset.entry) || 0;
        this._render();
      }));
  }
}

const DAC_STYLES = `
  :host { display: block; }
  ha-card {
    overflow: hidden;
    font-family: "Amazon Ember", -apple-system, "Segoe UI", Roboto, sans-serif;
    color: var(--primary-text-color, #f2f4f8);
    background: var(--ha-card-background, var(--card-background-color, #232f3e));
    border-radius: 14px;
  }
  .dac-hero {
    padding: 20px 18px 22px; text-align: center; color: #fff;
    background: linear-gradient(135deg, #232f3e 0%, #37475a 100%);
  }
  .tone-ringing { background: linear-gradient(135deg, #b12704, #ff9900); animation: dacPulse 1.2s infinite; }
  .tone-scheduled { background: linear-gradient(135deg, #146eb4, #232f3e); }
  .tone-vacation { background: linear-gradient(135deg, #0f7b6c, #232f3e); }
  .tone-dismissed, .tone-stopped { background: linear-gradient(135deg, #4a5568, #232f3e); }
  .tone-idle { background: linear-gradient(135deg, #37475a, #232f3e); }
  @keyframes dacPulse { 50% { filter: brightness(1.25); } }
  .dac-top { display: flex; justify-content: space-between; align-items: center; }
  .dac-brand { font-weight: 800; letter-spacing: 2px; font-size: 13px; }
  .dac-chip { background: rgba(255,255,255,.18); padding: 3px 12px; border-radius: 999px; font-size: 12px; }
  .dac-clock { font-size: 46px; font-weight: 200; margin: 10px 0 2px; font-variant-numeric: tabular-nums; }
  .dac-status { opacity: .9; font-size: 14px; margin-bottom: 8px; }
  .dac-alarm { display: flex; align-items: baseline; justify-content: center; gap: 12px; }
  .dac-alarm-big { font-size: 40px; font-weight: 700; }
  .dac-countdown { opacity: .8; font-size: 14px; }
  .dac-target { opacity: .65; font-size: 12px; margin-top: 4px; }
  .dac-pad { padding: 16px; }
  .dac-empty { text-align: center; padding: 28px 16px; }
  .dac-lbl { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; opacity: .6; margin-bottom: 8px; }
  .dac-lbl.spaced { margin-top: 16px; }
  .dac-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .dac-input {
    flex: 1; min-width: 0; box-sizing: border-box;
    background: var(--secondary-background-color, #1b2531);
    color: inherit; border: 1px solid rgba(255,255,255,.16);
    border-radius: 9px; padding: 9px 10px; font-size: 15px;
  }
  .dac-btn {
    background: linear-gradient(180deg, #ffb84d, #ff9900);
    color: #111; border: none; border-radius: 9px;
    padding: 9px 14px; font-size: 13px; font-weight: 700; cursor: pointer;
  }
  .dac-btn:hover { filter: brightness(1.06); }
  .dac-btn.ghost { background: transparent; color: inherit; border: 1px solid rgba(255,255,255,.28); }
  .dac-btn.active { outline: 2px solid #ff9900; }
  .dac-btn.danger { background: #b12704; color: #fff; }
  .dac-btn.tiny { padding: 3px 9px; font-size: 12px; }
  .dac-btn.dac-stop { background: #fff; color: #b12704; font-size: 16px; padding: 13px 22px; margin-top: 12px; width: 92%; }
  .dac-modes { display: flex; gap: 8px; flex-wrap: wrap; }
  .dac-hint { font-size: 12px; opacity: .7; margin-top: 10px; line-height: 1.5; }
  .dac-hint.alexa { color: #ffb84d; opacity: 1; }
  .dac-vac { margin-top: 16px; border-top: 1px solid rgba(255,255,255,.1); padding-top: 12px; }
  .dac-vac summary { cursor: pointer; font-weight: 600; font-size: 14px; opacity: .85; }
  .dac-vac-form { margin-top: 10px; }
  .dac-events { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; }
  .dac-event { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-size: 14px; }
  .dac-event-date { opacity: .6; font-size: 12px; }
  .dac-error { background: #b12704; color: #fff; padding: 14px 16px; border-radius: 10px; }
  .dac-tabs { display: flex; gap: 6px; padding: 0 16px 16px; }
  .dac-tab { flex: 1; background: rgba(255,255,255,.08); color: inherit; border: none; border-radius: 8px; padding: 8px; font-size: 12px; cursor: pointer; }
  .dac-tab.active { background: #ff9900; color: #111; font-weight: 700; }
`;

if (!customElements.get("dac-wecker")) {
  customElements.define("dac-wecker", DacWeckerCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "dac-wecker")) {
  window.customCards.push({
    type: "dac-wecker",
    name: "DAC Wecker",
    description: "Dynamic Alarm Clock – Arbeitsbeginn, Weckzeit, Alexa-Status, Modus und Urlaub in einer Karte.",
  });
}

if (window.console && window.console.info) {
  window.console.info(`%c DAC-WECKER %c ${DAC_CARD_VERSION} `,
    "background:#ff9900;color:#111;font-weight:700", "background:#232f3e;color:#fff");
}
