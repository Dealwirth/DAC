/**
 * DAC – Dynamic Alarm Clock · Sidebar-Panel (dac-panel)
 *
 * Vollständige Verwaltung der Integration auf einer Seite: Wecker, Modus,
 * Alexa, Urlaubskalender und alle Einstellungen. Nutzt die DAC-HTTP-API über
 * hass.callApi("GET"|"POST", "dac") und das Design von Home Assistant gemischt
 * mit der Amazon-/Alexa-Farbwelt (Navy + Orange).
 */
const DAC_VERSION = "0.4.0";
const DAC_AMBER = "#ff9900";
const DAC_NAVY = "#232f3e";

const WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
const MONTHS = [
  "Januar", "Februar", "März", "April", "Mai", "Juni",
  "Juli", "August", "September", "Oktober", "November", "Dezember",
];

function esc(value) {
  const div = document.createElement("div");
  div.textContent = String(value ?? "");
  return div.innerHTML;
}

function errMsg(err) {
  if (!err) return "Unbekannter Fehler";
  if (typeof err === "string") return err;
  if (err.body && err.body.message) return err.body.message;
  if (err.message) return err.message;
  return "Aktion fehlgeschlagen";
}

function hm(value) {
  return value ? String(value).slice(0, 5) : "";
}

function timeOf(value) {
  if (!value) return "--:--";
  return new Date(value).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
}

function dateLabel(value) {
  if (!value) return "";
  const d = new Date(value);
  return d.toLocaleDateString("de-DE", { weekday: "long", day: "2-digit", month: "long" });
}

function localIso(date) {
  const d = date || new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function clockNow() {
  return new Date().toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
}

function countdown(value) {
  if (!value) return null;
  const diff = new Date(value).getTime() - Date.now();
  if (diff <= 0) return null;
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  const s = Math.floor((diff % 60000) / 1000);
  if (h > 0) return `${h} h ${m} min`;
  if (m > 0) return `${m} min ${s} s`;
  return `${s} s`;
}

function modeLabel(mode) {
  return { standard: "Standard", dismissed: "Heute aus", vacation: "Urlaub" }[mode] || "Standard";
}

function statusOf(entry) {
  if (entry.vacation) return { icon: "beach", label: "Urlaub / Feiertag", tone: "vacation" };
  switch (entry.state) {
    case "ringing": return { icon: "alarm", label: "Weckt gerade", tone: "ringing" };
    case "scheduled": return { icon: "check", label: "Wecker gestellt", tone: "scheduled" };
    case "stopped": return { icon: "stop", label: "Gestoppt", tone: "stopped" };
    case "dismissed": return { icon: "sleep", label: "Heute deaktiviert", tone: "dismissed" };
    case "vacation": return { icon: "beach", label: "Urlaub / Feiertag", tone: "vacation" };
    default: return { icon: "clock", label: "Warte auf Arbeitszeit", tone: "idle" };
  }
}

function listToText(value) {
  if (Array.isArray(value)) return value.join(", ");
  return value || "";
}

class DacPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._data = null;
    this._error = null;
    this._busy = false;
    this._entryIndex = 0;
    this._month = new Date();
    this._selected = new Set();
    this._picker = null;
    this._settings = {};
    this._dirty = false;
    this._clock = null;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first && !this._data) this._refresh();
  }

  set panel(panel) { this._panel = panel; }
  set narrow(narrow) { this._narrow = narrow; }

  connectedCallback() {
    this._render();
    // Kein Dauer-Polling: der Server ist Single-Source-of-Truth und wird nach
    // jeder Aktion neu geladen. Die Uhr/Countdown laufen rein lokal.
    this._clock = setInterval(() => this._tick(), 1000);
  }

  disconnectedCallback() {
    clearInterval(this._clock);
  }

  getCardSize() { return 20; }

  // ------------------------------------------------------------------- data
  entries() {
    return (this._data && this._data.entries) || [];
  }

  entry() {
    const list = this.entries();
    if (!list.length) return null;
    return list[Math.min(this._entryIndex, list.length - 1)];
  }

  async _refresh() {
    if (!this._hass || this._busy) return;
    this._busy = true;
    try {
      this._data = await this._hass.callApi("GET", "dac");
      this._error = null;
      if (!this._dirty) this._settings = { ...(this.entry()?.settings || {}) };
    } catch (err) {
      this._error = errMsg(err);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _action(body) {
    if (!this._hass) return;
    const entry = this.entry();
    if (entry) body.entry_id = entry.entry_id;
    try {
      await this._hass.callApi("POST", "dac", body);
      this._error = null;
    } catch (err) {
      this._error = errMsg(err);
    }
    this._dirty = false;
    await this._refresh();
  }

  _tick() {
    const clock = this.shadowRoot.querySelector(".clock");
    if (clock) clock.textContent = clockNow();
    const cd = this.shadowRoot.querySelector(".countdown");
    if (cd) cd.textContent = this._countdownText();
  }

  _countdownText() {
    const entry = this.entry();
    if (!entry) return "";
    if (entry.state === "ringing") return "jetzt";
    return countdown(entry.alarm_target) || "kein Wecker aktiv";
  }

  // ----------------------------------------------------------------- render
  _render() {
    if (this._picker) return; // never wipe an open dialog
    if (this._error) {
      this.shadowRoot.innerHTML = `<style>${STYLES}</style>
        <div class="wrap"><div class="banner error">⚠️ ${esc(this._error)}</div></div>`;
      return;
    }
    const entry = this.entry();
    if (!entry) {
      this.shadowRoot.innerHTML = `<style>${STYLES}</style>
        <div class="wrap"><div class="empty">
          <h2>DAC ist noch nicht eingerichtet</h2>
          <p>Einstellungen → Geräte &amp; Dienste → Integration hinzufügen → „DAC“.</p>
        </div></div>`;
      return;
    }
    this.shadowRoot.innerHTML = `<style>${STYLES}</style>${this._body(entry)}<div id="dialog"></div>`;
    this._wire();
  }

  _body(entry) {
    const status = statusOf(entry);
    const ringing = entry.state === "ringing";
    const s = this._settings;
    const cal = entry.calendar || { own: [], external: [] };
    const alexa = entry.alexa || {};
    const tabs = this.entries().length > 1
      ? `<div class="tabs">${this.entries().map((e, i) =>
          `<button class="tab ${i === this._entryIndex ? "on" : ""}" data-entry="${i}">${esc(e.entry_id.slice(0, 6))}</button>`).join("")}</div>`
      : "";

    return `
    <div class="wrap">
      <header class="hero tone-${status.tone}">
        <div class="hero-top">
          <span class="brand">⏰ DAC</span>
          <span class="pill">${esc(modeLabel(entry.mode))}</span>
        </div>
        <div class="clock">${clockNow()}</div>
        <div class="status"><span class="dot"></span>${esc(status.label)}</div>
        <div class="alarm">
          <span class="alarm-time">${timeOf(entry.alarm_target)}</span>
          <span class="countdown">${esc(this._countdownText())}</span>
        </div>
        <div class="target">${esc(dateLabel(entry.alarm_target) || "Kein Weckzeitpunkt berechnet")}</div>
        ${ringing ? `<button class="btn stop" id="stop">⛔ Wecker stoppen</button>` : ""}
      </header>

      <div class="grid">
        <section class="card">
          <h3>Arbeitsbeginn</h3>
          <p class="muted">Weckzeit = Arbeitsbeginn − ${esc(entry.offset_minutes)} min</p>
          <div class="row">
            <button class="timebtn" id="pick-work">
              <span class="timebtn-value">${hm(entry.work_time) || "--:--"}</span>
              <span class="timebtn-hint">Arbeitsbeginn wählen</span>
            </button>
            <button class="btn" id="set-work">Setzen</button>
            <button class="btn ghost" id="clear-work" title="Zurücksetzen">Zurücksetzen</button>
          </div>
          <div class="chips" id="work-chips">
            ${["04:00", "05:00", "06:00", "07:00", "08:00", "09:00"].map((t) =>
              `<button class="chip" data-work="${t}">${t}</button>`).join("")}
          </div>
          <p class="hint">${entry.work_time
            ? `Gesetzt für ${esc(entry.work_time_day || "heute")}`
            : `Fallback: ${hm(entry.default_alarm_time)} Uhr`}</p>
        </section>

        <section class="card">
          <h3>Modus</h3>
          <div class="seg">
            ${["standard", "dismissed", "vacation"].map((m) =>
              `<button class="segbtn ${entry.mode === m ? "on" : ""}" data-mode="${m}">${esc(modeLabel(m))}</button>`).join("")}
          </div>
          <p class="hint">„Urlaub“ überschreibt den Wecker für heute, „Heute aus“ deaktiviert ihn einmalig.</p>
        </section>

        <section class="card">
          <h3>Alexa (Echo-Wecker)</h3>
          <div class="kv"><span>Status</span><b>${alexa.enabled ? "aktiv" : "aus"}</b></div>
          <div class="kv"><span>Echo</span><b>${esc(alexa.player || "—")}</b></div>
          <div class="kv"><span>Gesetzter Wecker</span><b>${esc(alexa.stored_alarm || "keiner")}</b></div>
          <div class="row">
            <button class="btn" id="alexa-set">Wecker setzen</button>
            <button class="btn ghost" id="alexa-sync">Sync</button>
            <button class="btn danger" id="alexa-clear">Löschen</button>
          </div>
          ${alexa.enabled ? "" : `<p class="hint">Aktiviere Alexa unten in den Einstellungen und wähle deinen Echo.</p>`}
        </section>

        <section class="card">
          <h3>Einstellungen</h3>
          <div class="fields">
            ${this._fieldTime("default_alarm_time", "Standard-Weckzeit (Fallback)", s.default_alarm_time)}
            ${this._fieldNumber("offset_minutes", "Offset vor Arbeitsbeginn (min)", s.offset_minutes, 0, 600, 5)}
            ${this._fieldTime("reminder_time", "Tägliche Erinnerung", s.reminder_time)}
            ${this._fieldText("notifier", "Benachrichtigungsdienst", s.notifier, "notify.mobile_app_…")}
            ${this._fieldText("alarm_lights", "Weck-Lichter (Komma-getrennt)", listToText(s.alarm_lights), "light.schlafzimmer")}
            ${this._fieldText("media_players", "Weck-Lautsprecher (Komma-getrennt)", listToText(s.media_players), "media_player.echo")}
            ${this._fieldText("vacation_calendars", "Externe Urlaubskalender", listToText(s.vacation_calendars), "calendar.feiertage")}
            ${this._fieldNumber("alarm_volume", "Lautstärke (0–1)", s.alarm_volume, 0, 1, 0.05)}
            ${this._fieldText("wake_text", "Weck-Ansage", s.wake_text, "Guten Morgen!")}
            ${this._fieldText("vacation_keywords", "Urlaubs-Schlagwörter (Komma-getrennt)", s.vacation_keywords, "urlaub, feiertag")}
            <label class="switch">
              <input type="checkbox" data-field="alexa_enabled" ${s.alexa_enabled ? "checked" : ""} />
              <span>Alexa-Gerätewecker auf dem Echo stellen</span>
            </label>
            ${this._fieldText("alexa_media_player", "Echo (alexa_media)", s.alexa_media_player, "media_player.echo")}
            ${this._fieldText("alexa_text_helper", "Helfer: gesetzter Wecker", s.alexa_text_helper, "input_text.gestellter_alexa_wecker")}
            ${this._fieldText("alexa_enabled_boolean", "Helfer: Wecker aktiv", s.alexa_enabled_boolean, "input_boolean.wecker_aktiv")}
            ${this._fieldSelect("alexa_command_type", "Alexa-Befehlstyp", s.alexa_command_type, [
              ["custom", "custom – Textbefehl (empfohlen)"],
              ["tts", "tts – gesprochen"],
            ])}
            ${this._fieldNumber("pre_alarm_minutes", "Vorab-Wecker Echo (min)", s.pre_alarm_minutes, 0, 30, 1)}
            ${this._fieldText("reminder_text", "Erinnerungstext ({alarm_time})", s.reminder_text, "Denk an die Arbeitszeit!")}
          </div>
          <div class="row end">
            <button class="btn" id="save-settings">Einstellungen speichern</button>
          </div>
        </section>

        <section class="card wide">
          <h3>Urlaubskalender</h3>
          ${this._calendar(cal)}
        </section>
      </div>
      ${tabs}
      <div class="foot">DAC ${esc(DAC_VERSION)} · Alle Einstellungen werden hier gespeichert – der Einrichtungsassistent fragt nichts ab.</div>
    </div>`;
  }

  _fieldTime(key, label, value) {
    return `<label class="field">
      <span>${esc(label)}</span>
      <button class="timebtn small" data-timefield="${key}">
        <span class="timebtn-value">${hm(value) || "--:--"}</span>
      </button>
    </label>`;
  }

  _fieldNumber(key, label, value, min, max, step) {
    return `<label class="field">
      <span>${esc(label)}</span>
      <input type="number" data-field="${key}" value="${esc(value ?? "")}"
        min="${min}" max="${max}" step="${step}" />
    </label>`;
  }

  _fieldText(key, label, value, placeholder) {
    return `<label class="field">
      <span>${esc(label)}</span>
      <input type="text" data-field="${key}" value="${esc(value ?? "")}"
        placeholder="${esc(placeholder || "")}" />
    </label>`;
  }

  _fieldSelect(key, label, value, options) {
    return `<label class="field">
      <span>${esc(label)}</span>
      <select data-field="${key}">
        ${options.map(([val, text]) =>
          `<option value="${esc(val)}" ${String(value ?? "") === val ? "selected" : ""}>${esc(text)}</option>`).join("")}
      </select>
    </label>`;
  }

  _calendar(cal) {
    const own = {};
    (cal.own || []).forEach((d) => { own[d.date] = d; });
    const external = {};
    (cal.external || []).forEach((d) => { external[d.date] = d; });

    const year = this._month.getFullYear();
    const month = this._month.getMonth();
    const first = new Date(year, month, 1);
    const startOffset = (first.getDay() + 6) % 7; // Monday first
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const todayIso = localIso();

    const cells = [];
    for (let i = 0; i < startOffset; i++) cells.push(`<div class="cell empty"></div>`);
    for (let day = 1; day <= daysInMonth; day++) {
      const iso = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      const cls = [
        "cell",
        own[iso] ? "own" : "",
        external[iso] ? "ext" : "",
        this._selected.has(iso) ? "sel" : "",
        iso === todayIso ? "today" : "",
      ].join(" ");
      cells.push(`<button class="${cls}" data-day="${iso}" title="${esc(own[iso]?.summary || external[iso]?.summary || "")}">${day}</button>`);
    }

    const selectedList = [...this._selected].sort();
    const ownList = (cal.own || []).sort((a, b) => a.date.localeCompare(b.date)).slice(0, 40);
    const extList = (cal.external || []).sort((a, b) => a.date.localeCompare(b.date)).slice(0, 40);

    return `
      <div class="cal-head">
        <button class="btn ghost" id="cal-prev">‹</button>
        <b>${MONTHS[month]} ${year}</b>
        <button class="btn ghost" id="cal-next">›</button>
      </div>
      <div class="cal-week">${WEEKDAYS.map((w) => `<span>${w}</span>`).join("")}</div>
      <div class="cal-grid">${cells.join("")}</div>
      <div class="legend">
        <span><i class="dot own"></i> Urlaub (DAC)</span>
        <span><i class="dot ext"></i> aus Kalender</span>
        <span><i class="dot sel"></i> ausgewählt</span>
      </div>
      <div class="row">
        <input class="inp" type="text" id="vac-summary" placeholder="Urlaub / Feiertag" />
        <button class="btn" id="vac-add">${selectedList.length > 1 ? `${selectedList.length} Tage` : "Tag"} markieren</button>
        <button class="btn ghost" id="vac-clear-sel">Auswahl leeren</button>
      </div>
      <div class="lists">
        <div>
          <h4>Eigene Urlaubstage</h4>
          ${ownList.length ? ownList.map((d) => `<div class="item">
            <span>${esc(d.date)}</span><span class="muted">${esc(d.summary)}</span>
            <button class="btn tiny danger" data-remove="${esc(d.uid)}">✕</button>
          </div>`).join("") : `<p class="muted">Noch keine Urlaubstage.</p>`}
        </div>
        <div>
          <h4>Aus Kalendern erkannt</h4>
          ${extList.length ? extList.map((d) => `<div class="item">
            <span>${esc(d.date)}</span><span class="muted">${esc(d.summary)}</span>
          </div>`).join("") : `<p class="muted">Keine externen Urlaubstage im Zeitraum.</p>`}
        </div>
      </div>`;
  }

  // ------------------------------------------------------------ interaction
  _wire() {
    const q = (sel) => this.shadowRoot.querySelector(sel);
    const stop = q("#stop");
    if (stop) stop.onclick = () => this._action({ action: "stop" });

    const pickWork = q("#pick-work");
    if (pickWork) pickWork.onclick = () =>
      this._openPicker("Arbeitsbeginn", hm(this.entry().work_time) || "06:00", (value) => {
        this._action({ action: "set_work_time", time: `${value}:00` });
      });

    const setWork = q("#set-work");
    if (setWork) setWork.onclick = () => {
      const value = hm(this.entry().work_time) || "06:00";
      this._action({ action: "set_work_time", time: `${value}:00` });
    };
    const clearWork = q("#clear-work");
    if (clearWork) clearWork.onclick = () => this._action({ action: "clear_work_time" });

    this.shadowRoot.querySelectorAll("[data-work]").forEach((btn) =>
      btn.onclick = () => this._action({ action: "set_work_time", time: `${btn.dataset.work}:00` }));

    this.shadowRoot.querySelectorAll("[data-mode]").forEach((btn) =>
      btn.onclick = () => this._action({ action: "mode", mode: btn.dataset.mode }));

    const alexaSet = q("#alexa-set");
    if (alexaSet) alexaSet.onclick = () => this._action({ action: "alexa_set" });
    const alexaSync = q("#alexa-sync");
    if (alexaSync) alexaSync.onclick = () => this._action({ action: "alexa_sync" });
    const alexaClear = q("#alexa-clear");
    if (alexaClear) alexaClear.onclick = () => this._action({ action: "alexa_clear" });

    this.shadowRoot.querySelectorAll("[data-timefield]").forEach((btn) =>
      btn.onclick = () => {
        const key = btn.dataset.timefield;
        this._openPicker(btn.closest("label").querySelector("span").textContent,
          hm(this._settings[key]) || "06:00",
          (value) => {
            this._settings[key] = `${value}:00`;
            this._dirty = true;
            this._render();
          });
      });

    this.shadowRoot.querySelectorAll("[data-field]").forEach((input) =>
      input.oninput = () => {
        const key = input.dataset.field;
        this._settings[key] = input.type === "checkbox" ? input.checked : input.value;
        this._dirty = true;
      });

    const save = q("#save-settings");
    if (save) save.onclick = () => {
      this._action({ action: "save_settings", settings: this._settings });
    };

    const prev = q("#cal-prev");
    if (prev) prev.onclick = () => { this._month = new Date(this._month.getFullYear(), this._month.getMonth() - 1, 1); this._render(); };
    const next = q("#cal-next");
    if (next) next.onclick = () => { this._month = new Date(this._month.getFullYear(), this._month.getMonth() + 1, 1); this._render(); };

    this.shadowRoot.querySelectorAll("[data-day]").forEach((btn) =>
      btn.onclick = (ev) => {
        const iso = btn.dataset.day;
        if (ev.shiftKey && this._selected.size) {
          this._selectRange([...this._selected][0], iso);
        } else if (this._selected.has(iso)) {
          this._selected.delete(iso);
        } else {
          this._selected.add(iso);
        }
        this._render();
      });

    const add = q("#vac-add");
    if (add) add.onclick = () => {
      const days = [...this._selected].sort();
      if (!days.length) return;
      const summary = q("#vac-summary").value || "Urlaub";
      this._selected.clear();
      this._action({ action: "add_vacation", start: days[0], end: days[days.length - 1], summary });
    };
    const clearSel = q("#vac-clear-sel");
    if (clearSel) clearSel.onclick = () => { this._selected.clear(); this._render(); };

    this.shadowRoot.querySelectorAll("[data-remove]").forEach((btn) =>
      btn.onclick = () => this._action({ action: "remove_vacation", uid: btn.dataset.remove }));

    this.shadowRoot.querySelectorAll("[data-entry]").forEach((btn) =>
      btn.onclick = () => {
        this._entryIndex = Number(btn.dataset.entry) || 0;
        this._settings = { ...(this.entry()?.settings || {}) };
        this._dirty = false;
        this._render();
      });
  }

  _selectRange(fromIso, toIso) {
    const from = new Date(fromIso);
    const to = new Date(toIso);
    const start = from <= to ? from : to;
    const end = from <= to ? to : from;
    this._selected.clear();
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      this._selected.add(localIso(d));
    }
  }

  // --------------------------------------------------------- time picker UI
  _openPicker(title, value, onApply) {
    const [h0, m0] = (value || "06:00").split(":").map(Number);
    this._picker = { hour: h0 || 0, minute: m0 || 0, onApply };
    const hours = Array.from({ length: 24 }, (_, i) => i);
    const minutes = Array.from({ length: 12 }, (_, i) => i * 5);
    const root = this.shadowRoot.querySelector("#dialog");
    root.innerHTML = `
      <div class="overlay" id="ovl">
        <div class="picker" role="dialog" aria-label="${esc(title)}">
          <div class="picker-head">${esc(title)}</div>
          <div class="picker-value">${String(this._picker.hour).padStart(2, "0")}:${String(this._picker.minute).padStart(2, "0")}</div>
          <div class="wheels">
            <div class="wheel" data-wheel="hour">
              ${hours.map((h) => `<button class="witem ${h === this._picker.hour ? "on" : ""}" data-h="${h}">${String(h).padStart(2, "0")}</button>`).join("")}
            </div>
            <div class="colon">:</div>
            <div class="wheel" data-wheel="minute">
              ${minutes.map((m) => `<button class="witem ${m === this._picker.minute ? "on" : ""}" data-m="${m}">${String(m).padStart(2, "0")}</button>`).join("")}
            </div>
          </div>
          <div class="chips center">
            ${["05:00", "06:00", "06:30", "07:00", "08:00"].map((t) =>
              `<button class="chip" data-preset="${t}">${t}</button>`).join("")}
          </div>
          <div class="picker-actions">
            <button class="btn ghost" id="pick-cancel">Abbrechen</button>
            <button class="btn" id="pick-ok">Übernehmen</button>
          </div>
        </div>
      </div>`;
    this._wirePicker();
  }

  _wirePicker() {
    const root = this.shadowRoot.querySelector("#dialog");
    const close = () => { this._picker = null; root.innerHTML = ""; this._render(); };

    root.querySelector("#ovl").onclick = (ev) => { if (ev.target.id === "ovl") close(); };
    root.querySelector("#pick-cancel").onclick = close;
    root.querySelector("#pick-ok").onclick = () => {
      const { hour, minute, onApply } = this._picker;
      const value = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
      this._picker = null;
      root.innerHTML = "";
      onApply(value);
    };

    root.querySelectorAll("[data-h]").forEach((btn) => btn.onclick = () => {
      this._picker.hour = Number(btn.dataset.h);
      this._repaintPicker();
    });
    root.querySelectorAll("[data-m]").forEach((btn) => btn.onclick = () => {
      this._picker.minute = Number(btn.dataset.m);
      this._repaintPicker();
    });
    root.querySelectorAll("[data-preset]").forEach((btn) => btn.onclick = () => {
      const [h, m] = btn.dataset.preset.split(":").map(Number);
      this._picker.hour = h;
      this._picker.minute = m;
      this._repaintPicker();
    });

    this._scrollPicker();
  }

  _repaintPicker() {
    const root = this.shadowRoot.querySelector("#dialog");
    root.querySelector(".picker-value").textContent =
      `${String(this._picker.hour).padStart(2, "0")}:${String(this._picker.minute).padStart(2, "0")}`;
    root.querySelectorAll("[data-h]").forEach((b) => b.classList.toggle("on", Number(b.dataset.h) === this._picker.hour));
    root.querySelectorAll("[data-m]").forEach((b) => b.classList.toggle("on", Number(b.dataset.m) === this._picker.minute));
    this._scrollPicker();
  }

  _scrollPicker() {
    const root = this.shadowRoot.querySelector("#dialog");
    [["hour", this._picker.hour], ["minute", this._picker.minute]].forEach(([kind, value]) => {
      const wheel = root.querySelector(`[data-wheel="${kind}"]`);
      const item = kind === "hour" ? wheel.querySelector(`[data-h="${value}"]`) : wheel.querySelector(`[data-m="${value}"]`);
      if (item) item.scrollIntoView({ block: "center" });
    });
  }
}

const STYLES = `
  :host { display: block; background: var(--primary-background-color, #f4f5f7); min-height: 100vh; }
  .wrap { max-width: 1100px; margin: 0 auto; padding: 16px; font-family: "Amazon Ember", var(--paper-font-body1_-_font-family, -apple-system, "Segoe UI", Roboto, sans-serif); color: var(--primary-text-color, #212121); }
  .hero { border-radius: 18px; padding: 22px; color: #fff; background: linear-gradient(135deg, ${DAC_NAVY} 0%, #37475a 100%); box-shadow: 0 8px 26px rgba(0,0,0,.22); }
  .tone-ringing { background: linear-gradient(135deg, #b12704, ${DAC_AMBER}); animation: pulse 1.2s infinite; }
  .tone-scheduled { background: linear-gradient(135deg, #146eb4, ${DAC_NAVY}); }
  .tone-vacation { background: linear-gradient(135deg, #0f7b6c, ${DAC_NAVY}); }
  .tone-dismissed, .tone-stopped { background: linear-gradient(135deg, #4a5568, ${DAC_NAVY}); }
  @keyframes pulse { 50% { filter: brightness(1.22); } }
  .hero-top { display: flex; justify-content: space-between; align-items: center; }
  .brand { font-weight: 800; letter-spacing: 2px; }
  .pill { background: rgba(255,255,255,.18); padding: 3px 12px; border-radius: 999px; font-size: 12px; }
  .clock { font-size: 54px; font-weight: 200; margin: 8px 0 0; font-variant-numeric: tabular-nums; }
  .status { opacity: .92; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
  .dot { width: 9px; height: 9px; border-radius: 50%; background: ${DAC_AMBER}; box-shadow: 0 0 0 4px rgba(255,153,0,.25); }
  .alarm { display: flex; align-items: baseline; gap: 12px; }
  .alarm-time { font-size: 42px; font-weight: 700; }
  .countdown { opacity: .8; }
  .target { opacity: .68; font-size: 13px; margin-top: 2px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-top: 16px; }
  .card { background: var(--card-background-color, #fff); border-radius: 16px; padding: 16px 18px; box-shadow: 0 2px 10px rgba(0,0,0,.08); }
  .card.wide { grid-column: 1 / -1; }
  h3 { margin: 0 0 6px; font-size: 16px; }
  h4 { margin: 12px 0 6px; font-size: 13px; text-transform: uppercase; letter-spacing: .5px; opacity: .6; }
  .muted { color: var(--secondary-text-color, #6b7280); font-size: 13px; margin: 0 0 10px; }
  .hint { color: var(--secondary-text-color, #6b7280); font-size: 12px; margin: 10px 0 0; }
  .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .row.end { justify-content: flex-end; margin-top: 12px; }
  .btn { background: linear-gradient(180deg, #ffb84d, ${DAC_AMBER}); color: #111; border: none; border-radius: 10px; padding: 10px 16px; font-weight: 700; cursor: pointer; font-size: 14px; }
  .btn:hover { filter: brightness(1.06); }
  .btn.ghost { background: transparent; color: inherit; border: 1px solid var(--divider-color, rgba(0,0,0,.22)); }
  .btn.danger { background: #b12704; color: #fff; }
  .btn.tiny { padding: 3px 9px; font-size: 12px; }
  .btn.stop { background: #fff; color: #b12704; font-size: 16px; padding: 13px 22px; margin-top: 14px; width: 100%; }
  .timebtn { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; background: var(--secondary-background-color, #eef1f5); border: 1px solid var(--divider-color, rgba(0,0,0,.12)); border-radius: 12px; padding: 10px 16px; cursor: pointer; color: inherit; }
  .timebtn.small { padding: 8px 12px; }
  .timebtn-value { font-size: 26px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .timebtn.small .timebtn-value { font-size: 18px; }
  .timebtn-hint { font-size: 11px; opacity: .6; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
  .chips.center { justify-content: center; }
  .chip { background: var(--secondary-background-color, #eef1f5); border: 1px solid var(--divider-color, rgba(0,0,0,.1)); border-radius: 999px; padding: 6px 12px; cursor: pointer; font-size: 13px; color: inherit; }
  .seg { display: flex; gap: 6px; background: var(--secondary-background-color, #eef1f5); border-radius: 12px; padding: 4px; }
  .segbtn { flex: 1; border: none; background: transparent; border-radius: 9px; padding: 9px; cursor: pointer; font-weight: 600; color: inherit; }
  .segbtn.on { background: ${DAC_AMBER}; color: #111; }
  .kv { display: flex; justify-content: space-between; padding: 5px 0; font-size: 14px; border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.07)); }
  .fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; margin-top: 8px; }
  .field { display: flex; flex-direction: column; gap: 5px; font-size: 13px; }
  .field > span { color: var(--secondary-text-color, #6b7280); }
  .inp, .field input[type=text], .field input[type=number] { background: var(--secondary-background-color, #eef1f5); border: 1px solid var(--divider-color, rgba(0,0,0,.12)); border-radius: 10px; padding: 9px 11px; font-size: 14px; color: inherit; width: 100%; box-sizing: border-box; }
  .switch { display: flex; align-items: center; gap: 10px; grid-column: 1 / -1; font-size: 14px; padding: 6px 0; }
  .switch input { width: 20px; height: 20px; }
  .cal-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
  .cal-week, .cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; }
  .cal-week span { text-align: center; font-size: 12px; opacity: .6; padding: 4px 0; }
  .cell { aspect-ratio: 1 / 1; border-radius: 10px; border: 1px solid var(--divider-color, rgba(0,0,0,.08)); background: var(--secondary-background-color, #f0f2f5); cursor: pointer; font-size: 14px; color: inherit; display: flex; align-items: center; justify-content: center; }
  .cell.empty { background: transparent; border: none; cursor: default; }
  .cell.own { background: ${DAC_AMBER}; color: #111; font-weight: 700; }
  .cell.ext { background: #146eb4; color: #fff; }
  .cell.sel { outline: 3px solid #146eb4; }
  .cell.today { box-shadow: inset 0 0 0 2px ${DAC_NAVY}; }
  .legend { display: flex; gap: 14px; flex-wrap: wrap; margin: 10px 0; font-size: 12px; color: var(--secondary-text-color, #6b7280); }
  .legend .dot { width: 10px; height: 10px; border-radius: 3px; box-shadow: none; display: inline-block; margin-right: 5px; }
  .legend .dot.own { background: ${DAC_AMBER}; }
  .legend .dot.ext { background: #146eb4; }
  .legend .dot.sel { background: transparent; outline: 2px solid #146eb4; }
  .lists { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin-top: 8px; }
  .item { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 5px 0; font-size: 13px; border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.06)); }
  .tabs { display: flex; gap: 6px; margin-top: 16px; }
  .tab { background: var(--secondary-background-color, #eef1f5); border: none; border-radius: 9px; padding: 8px 14px; cursor: pointer; color: inherit; }
  .tab.on { background: ${DAC_AMBER}; color: #111; font-weight: 700; }
  .banner.error { background: #b12704; color: #fff; padding: 14px 16px; border-radius: 12px; }
  .empty { background: var(--card-background-color, #fff); border-radius: 16px; padding: 40px; text-align: center; }
  .foot { text-align: center; color: var(--secondary-text-color, #6b7280); font-size: 12px; margin: 20px 0; }
  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 10; }
  .picker { background: var(--card-background-color, #fff); border-radius: 20px; padding: 20px; width: min(420px, 92vw); box-shadow: 0 20px 60px rgba(0,0,0,.4); }
  .picker-head { font-weight: 700; text-align: center; margin-bottom: 4px; }
  .picker-value { text-align: center; font-size: 40px; font-weight: 700; font-variant-numeric: tabular-nums; color: ${DAC_AMBER}; }
  .wheels { display: flex; align-items: center; justify-content: center; gap: 10px; margin: 12px 0; }
  .wheel { height: 180px; overflow-y: auto; scroll-snap-type: y mandatory; display: flex; flex-direction: column; gap: 4px; width: 90px; padding: 4px; }
  .witem { scroll-snap-align: center; border: none; background: transparent; padding: 10px 0; font-size: 20px; border-radius: 10px; cursor: pointer; color: inherit; font-variant-numeric: tabular-nums; }
  .witem.on { background: ${DAC_AMBER}; color: #111; font-weight: 700; }
  .colon { font-size: 28px; font-weight: 700; }
  .picker-actions { display: flex; justify-content: space-between; gap: 10px; margin-top: 16px; }
`;

if (!customElements.get("dac-panel")) {
  customElements.define("dac-panel", DacPanel);
}

if (window.console && window.console.info) {
  window.console.info(`%c DAC-PANEL %c ${DAC_VERSION} `,
    `background:${DAC_AMBER};color:#111;font-weight:700`, `background:${DAC_NAVY};color:#fff`);
}
