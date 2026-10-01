/**
 * DAC – Dynamic Alarm Clock · Dashboard-Panel
 *
 * Ein einziges Sidebar-Panel („DAC“, /dac) mit mehreren Seiten:
 *   Home          – Wecker, Testmodus, Modus, Alexa-Status
 *   Kalender      – Urlaubskalender + gekoppelte Home-Assistant-Kalender
 *   Einstellungen – alle Optionen, inkl. Alexa-Suche
 *   Hilfe         – Kurzanleitung, Alexa-Routine, Dienste
 *
 * Entitäten werden über ein echtes Suchfeld mit Live-Vorschlägen gewählt:
 * Tippen filtert sofort über Name, Entity-ID und Bereich (Area); passende
 * Domains stehen zuerst, „auch gefunden“ danach. So findet man einen Echo,
 * ohne den genauen Entity-Namen zu kennen.
 */
const DAC_VERSION = "0.7.0";
const DAC_AMBER = "#ff9900";
const DAC_NAVY = "#232f3e";
const MAX_SUGGESTIONS = 10;

const WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
const MONTHS = [
  "Januar", "Februar", "März", "April", "Mai", "Juni",
  "Juli", "August", "September", "Oktober", "November", "Dezember",
];

// Pro Feld erlaubte Domains; null = alle Domains durchsuchbar.
const FIELD_DOMAINS = {
  alarm_lights: ["light", "switch"],
  vacation_calendars: ["calendar"],
  alexa_media_player: ["media_player"],
  alexa_text_helper: ["input_text"],
  alexa_enabled_boolean: ["input_boolean"],
};

const FIELD_EXAMPLES = {
  alarm_lights: "z. B. Schlafzimmer",
  vacation_calendars: "z. B. Feiertage",
  alexa_media_player: "z. B. Echo, Küche …",
  alexa_text_helper: "z. B. gestellter Wecker",
  alexa_enabled_boolean: "z. B. wecker aktiv",
};

// Felder, die mehrere Entitäten halten (Chips + reine Suche im Eingabefeld).
const MULTI_FIELDS = { alarm_lights: true, vacation_calendars: true };

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

function dayLabel(iso) {
  if (!iso) return "";
  const [y, m, d] = String(iso).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("de-DE", {
    weekday: "short", day: "2-digit", month: "2-digit",
  });
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
  if (entry.vacation) return { label: "Urlaub / Feiertag", tone: "vacation" };
  switch (entry.state) {
    case "ringing": return { label: "Weckt gerade", tone: "ringing" };
    case "scheduled":
      return entry.test_mode
        ? { label: "Testwecker gestellt", tone: "test" }
        : { label: "Wecker gestellt", tone: "scheduled" };
    case "stopped": return { label: "Gestoppt", tone: "stopped" };
    case "dismissed": return { label: "Heute deaktiviert", tone: "dismissed" };
    case "vacation": return { label: "Urlaub / Feiertag", tone: "vacation" };
    default: return { label: "Warte auf Arbeitszeit", tone: "idle" };
  }
}

function listToText(value) {
  if (Array.isArray(value)) return value.join(", ");
  return value || "";
}

function splitList(value) {
  return String(value || "").split(",").map((part) => part.trim()).filter(Boolean);
}

/**
 * Sucht Entitäten: passende Domains zuerst, danach Treffer aus anderen
 * Domains ("auch gefunden"). Query trifft Name, Entity-ID und Bereich.
 */
function searchEntities(items, query, domains) {
  const q = String(query || "").trim().toLowerCase();
  const inDomain = [];
  const others = [];
  for (const item of items) {
    if (!q) {
      if (!domains || domains.includes(item.domain)) inDomain.push(item);
      continue;
    }
    const haystack = [item.id, item.name, item.area || ""].join(" ").toLowerCase();
    if (!haystack.includes(q)) continue;
    if (!domains || domains.includes(item.domain)) inDomain.push(item);
    else others.push(item);
  }
  const rank = (a, b) => {
    const an = (a.name || "").toLowerCase().startsWith(q) ? 0 : 1;
    const bn = (b.name || "").toLowerCase().startsWith(q) ? 0 : 1;
    if (an !== bn) return an - bn;
    if (a.alexa !== b.alexa) return a.alexa ? -1 : 1;
    return (a.name || a.id).localeCompare(b.name || b.id);
  };
  inDomain.sort(rank);
  others.sort(rank);
  return { primary: inDomain.slice(0, MAX_SUGGESTIONS), extra: others.slice(0, 5) };
}

/** Basisklasse: lädt den API-Zustand, hält Einstellungen und die Seiten-Navigation. */
class DacBase extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._data = null;
    this._error = null;
    this._busy = false;
    this._entryIndex = 0;
    this._settings = {};
    this._dirty = false;
    this._page = "home";
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first && !this._data) this._refresh();
  }

  set panel(panel) {
    this._panel = panel;
    // Deep-Link: /dac-settings öffnet direkt die Einstellungs-Seite.
    const path = (panel && panel.config && panel.config.route) || window.location.pathname;
    if (String(path).includes("settings")) this._page = "settings";
  }

  set narrow(narrow) { this._narrow = narrow; }

  entries() {
    return (this._data && this._data.entries) || [];
  }

  entry() {
    const list = this.entries();
    if (!list.length) return null;
    return list[Math.min(this._entryIndex, list.length - 1)];
  }

  entities() {
    return (this.entry() && this.entry().entities) || [];
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

  _toast(message) {
    if (!message) return;
    const el = this.shadowRoot.querySelector(".toast");
    if (!el) return;
    el.textContent = message;
    el.classList.add("on");
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => el.classList.remove("on"), 2600);
  }

  _go(page) {
    this._page = page;
    this._render();
  }

  _errorView() {
    return `<style>${STYLES}</style>
      <div class="wrap"><div class="banner error">⚠️ ${esc(this._error)}</div></div>`;
  }

  _emptyView() {
    return `<style>${STYLES}</style>
      <div class="wrap"><div class="empty">
        <h2>DAC ist noch nicht eingerichtet</h2>
        <p>Einstellungen → Geräte &amp; Dienste → Integration hinzufügen → „DAC“.</p>
      </div></div>`;
  }

  _tabs() {
    if (this.entries().length <= 1) return "";
    return `<div class="entries">${this.entries().map((e, i) =>
      `<button class="tab ${i === this._entryIndex ? "on" : ""}" data-entry="${i}">Wecker ${i + 1}</button>`).join("")}</div>`;
  }

  _wireTabs() {
    this.shadowRoot.querySelectorAll("[data-entry]").forEach((btn) =>
      btn.onclick = () => {
        this._entryIndex = Number(btn.dataset.entry) || 0;
        this._settings = { ...(this.entry()?.settings || {}) };
        this._dirty = false;
        this._render();
      });
  }

  /** Kopfzeile mit Seitennavigation – ein Dashboard, mehrere Seiten. */
  _nav(tone) {
    const pages = [
      ["home", "🏠 Home"],
      ["calendar", "📅 Kalender"],
      ["settings", "⚙️ Einstellungen"],
      ["help", "❓ Hilfe"],
    ];
    return `
      <nav class="nav tone-${tone}">
        <div class="nav-top">
          <span class="brand">⏰ DAC</span>
          <span class="nav-sub">${esc(this._pageTitle())}</span>
        </div>
        <div class="nav-pages">
          ${pages.map(([key, label]) =>
            `<button class="page ${this._page === key ? "on" : ""}" data-page="${key}">${label}</button>`).join("")}
        </div>
      </nav>`;
  }

  _pageTitle() {
    return {
      home: "Wecker & Steuerung",
      calendar: "Urlaub & Kalender",
      settings: "Einstellungen",
      help: "Hilfe & Einrichtung",
    }[this._page] || "DAC";
  }

  _wireNav() {
    this.shadowRoot.querySelectorAll("[data-page]").forEach((btn) =>
      btn.onclick = () => this._go(btn.dataset.page));
  }

  // ------------------------------------------------------- entity search UI
  /** Ein Entity-Feld: Suchfeld + Live-Vorschläge (Klick übernimmt).
   *
   * Mehrfachfelder zeigen ihre Auswahl als Chips und das Eingabefeld ist eine
   * reine Suche; Einzelfelder zeigen den Wert im Feld selbst (bearbeitbar).
   */
  _entityField(key, label, value, { multi = false } = {}) {
    const current = listToText(value);
    const chips = multi
      ? splitList(current).map((id) =>
        `<button class="chosen" data-unpick="${key}" data-value="${esc(id)}" title="Entfernen">${esc(this._entityName(id))} <b>✕</b></button>`).join("")
      : "";
    const input = multi
      ? `<input class="inp search" type="text" data-search="${key}" autocomplete="off"
           placeholder="${esc(FIELD_EXAMPLES[key] || "🔍 Name oder Bereich eingeben …")}" />`
      : `<input class="inp search" type="text" data-field="${key}" data-search="${key}" autocomplete="off"
           value="${esc(current)}" placeholder="${esc(FIELD_EXAMPLES[key] || "🔍 Name oder Bereich eingeben …")}" />`;
    return `<div class="field entity-field" data-efield="${key}">
      <span>${esc(label)}</span>
      ${multi ? `<div class="chosen-row">${chips || `<span class="muted">noch nichts gewählt</span>`}</div>` : ""}
      ${input}
      <div class="suggestions" data-suggestions="${key}"></div>
      ${multi ? `<span class="hint">Mehrere per Klick hinzufügen – die Suche bleibt danach offen.</span>` : ""}
    </div>`;
  }

  _entityName(id) {
    const found = this.entities().find((item) => item.id === id);
    return found ? found.name : id;
  }

  /** Vorschlagsliste für ein Suchfeld neu aufbauen. */
  _updateSuggestions(key) {
    const box = this.shadowRoot.querySelector(`[data-suggestions="${key}"]`);
    const input = this.shadowRoot.querySelector(`[data-search="${key}"]`);
    if (!box) return;
    const query = (input && input.value || "").trim();
    const domains = FIELD_DOMAINS[key] || null;
    const chosen = new Set(splitList(this._settings[key]));
    const { primary, extra } = searchEntities(this.entities(), query, domains);
    const usable = primary.filter((item) => !chosen.has(item.id));
    const extraUsable = extra.filter((item) => !chosen.has(item.id));
    if (!usable.length && !extraUsable.length) {
      box.innerHTML = query
        ? `<span class="muted">Nichts gefunden für „${esc(query)}“.</span>`
        : `<span class="muted">Tippen, um zu suchen.</span>`;
      return;
    }
    const render = (items) => items.map((item) =>
      `<button class="chip suggest ${item.alexa ? "alexa" : ""}" data-pick="${key}" data-value="${esc(item.id)}">
        ${item.alexa ? "🔊 " : ""}${esc(item.name)}
        <em>${esc(item.id)}${item.area ? ` · ${esc(item.area)}` : ""}</em></button>`).join("");
    box.innerHTML = render(usable) + (extraUsable.length
      ? `<span class="extra-label">auch gefunden</span>${render(extraUsable)}`
      : "");
    box.querySelectorAll("[data-pick]").forEach((btn) =>
      btn.onclick = () => this._pickEntity(key, btn.dataset.value));
  }

  _pickEntity(key, value) {
    const multi = this._isMulti(key);
    if (multi) {
      const parts = splitList(this._settings[key]);
      if (!parts.includes(value)) parts.push(value);
      this._settings[key] = parts.join(", ");
    } else {
      this._settings[key] = value;
    }
    this._dirty = true;
    this._render();
    // Keep focus on the field so selecting several entities stays quick.
    const again = this.shadowRoot.querySelector(`[data-search="${key}"]`);
    if (again) again.focus();
    this._toast(`${this._entityName(value)} übernommen`);
  }

  _isMulti(key) {
    if (MULTI_FIELDS[key]) return true;
    const field = this.shadowRoot.querySelector(`[data-field="${key}"]`);
    return !!(field && field.dataset.multi === "true");
  }

  _unpickEntity(key, value) {
    this._settings[key] = splitList(this._settings[key]).filter((id) => id !== value).join(", ");
    this._dirty = true;
    this._render();
  }

  _wireEntityFields() {
    this.shadowRoot.querySelectorAll("[data-search]").forEach((input) => {
      const key = input.dataset.search;
      const multi = this._isMulti(key);
      input.oninput = () => {
        if (!multi) {
          this._settings[key] = input.value;
          this._dirty = true;
          this._refreshDirty();
        }
        this._updateSuggestions(key);
      };
      input.onfocus = () => this._updateSuggestions(key);
    });
    this.shadowRoot.querySelectorAll("[data-unpick]").forEach((btn) =>
      btn.onclick = () => this._unpickEntity(btn.dataset.unpick, btn.dataset.value));
    Object.keys(FIELD_DOMAINS).forEach((key) => {
      if (this.shadowRoot.querySelector(`[data-suggestions="${key}"]`)) {
        this._updateSuggestions(key);
      }
    });
  }

  // ------------------------------------------------------- common form wiring
  _wireSettingsFields() {
    this.shadowRoot.querySelectorAll("[data-field]").forEach((input) => {
      const key = input.dataset.field;
      if (input.dataset.search) return;
      input.oninput = () => {
        const value = input.type === "checkbox" ? input.checked : input.value;
        this._settings[key] = input.classList.contains("time") && value ? `${value}:00` : value;
        this._dirty = true;
        this._refreshDirty();
      };
      input.onchange = input.oninput;
    });
    this.shadowRoot.querySelectorAll("select[data-field]").forEach((select) => {
      select.onchange = () => {
        this._settings[select.dataset.field] = select.value;
        this._dirty = true;
        this._refreshDirty();
      };
    });
  }

  _refreshDirty() {
    const el = this.shadowRoot.querySelector(".dirty");
    if (!el) return;
    el.classList.toggle("on", this._dirty);
    el.textContent = this._dirty ? "Ungespeicherte Änderungen" : "Alles gespeichert";
  }

  // ------------------------------------------------------------ field builder
  _fieldTime(key, label, value) {
    return `<label class="field">
      <span>${esc(label)}</span>
      <input class="inp time" type="time" data-field="${key}" value="${hm(value)}" />
    </label>`;
  }

  _fieldNumber(key, label, value, min, max, step, unit) {
    return `<label class="field">
      <span>${esc(label)}${unit ? ` (${esc(unit)})` : ""}</span>
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

  _fieldSwitch(key, label, value) {
    return `<label class="switch">
      <input type="checkbox" data-field="${key}" ${value ? "checked" : ""} />
      <span>${esc(label)}</span>
    </label>`;
  }
}

/* ==========================================================================
 * Dashboard-Panel  (/dac)
 * ========================================================================== */
class DacPanel extends DacBase {
  constructor() {
    super();
    this._month = new Date();
    this._selected = new Set();
    this._clock = null;
  }

  connectedCallback() {
    this._render();
    this._refresh();
    this._clock = setInterval(() => this._tick(), 1000);
  }

  disconnectedCallback() {
    clearInterval(this._clock);
  }

  getCardSize() { return 20; }

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

  _render() {
    if (this._error) { this.shadowRoot.innerHTML = this._errorView(); return; }
    const entry = this.entry();
    if (!entry) { this.shadowRoot.innerHTML = this._emptyView(); return; }
    const views = {
      home: () => this._home(entry),
      calendar: () => this._calendarPage(entry),
      settings: () => this._settingsPage(entry),
      help: () => this._helpPage(entry),
    };
    const body = (views[this._page] || views.home)();
    this.shadowRoot.innerHTML =
      `<style>${STYLES}</style><div class="wrap">${this._nav(statusOf(entry).tone)}${body}${this._tabs()}<div class="toast"></div></div>`;
    this._wire();
  }

  // ------------------------------------------------------------------- Home
  _home(entry) {
    const status = statusOf(entry);
    const ringing = entry.state === "ringing";
    const alexa = entry.alexa || {};
    return `
      <header class="hero tone-${status.tone}">
        <div class="hero-top">
          <span class="brand">Nächster Wecker</span>
          ${ringing ? `<span class="pill">klingelt</span>` : ""}
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
        ${this._cardWorkTime(entry, this._settings)}
        ${this._cardTestMode(entry, this._settings)}
        ${this._cardMode(entry)}
        ${this._cardAlexa(alexa)}
      </div>`;
  }

  _cardWorkTime(entry, s) {
    const quick = ["04:00", "05:00", "06:00", "06:30", "07:00", "08:00"];
    return `
      <section class="card">
        <h3>Arbeitsbeginn</h3>
        <p class="muted">Weckzeit = Arbeitsbeginn − ${esc(entry.offset_minutes)} min</p>
        <div class="row">
          <input class="inp time" type="time" id="work-input"
            value="${hm(entry.work_time) || hm(s.default_alarm_time) || "06:00"}" />
          <button class="btn" id="set-work">Setzen</button>
          <button class="btn ghost" id="clear-work" title="Zurücksetzen">Zurücksetzen</button>
        </div>
        <div class="chips">
          ${quick.map((t) => `<button class="chip" data-work="${t}">${t}</button>`).join("")}
        </div>
        <p class="hint">${entry.work_time
          ? `Gesetzt für ${esc(entry.work_time_day || "heute")}`
          : `Fallback: ${hm(entry.default_alarm_time)} Uhr`}</p>
      </section>`;
  }

  _cardTestMode(entry, s) {
    const active = entry.test_mode;
    return `
      <section class="card ${active ? "test-on" : ""}">
        <h3>Testmodus ${active ? `<span class="badge">aktiv</span>` : ""}</h3>
        ${active
          ? `<p class="muted">Der Testwecker klingelt um <b>${timeOf(entry.test_target)}</b> – mit Licht und Echo wie der echte Wecker.</p>
             <div class="row"><button class="btn danger" id="test-cancel">Testwecker abbrechen</button></div>`
          : `<p class="muted">Klingelt in X Minuten – prüft die komplette Kette (Licht, Echo, Wiederholung).</p>
             <div class="row">
               <input class="inp small" type="number" id="test-minutes" min="1" max="120"
                 value="${esc(s.test_mode_minutes ?? 1)}" />
               <span class="muted">Minuten</span>
               <button class="btn" id="test-start">Testwecker starten</button>
             </div>`}
      </section>`;
  }

  _cardMode(entry) {
    return `
      <section class="card">
        <h3>Modus</h3>
        <div class="seg">
          ${["standard", "dismissed", "vacation"].map((m) =>
            `<button class="segbtn ${entry.mode === m ? "on" : ""}" data-mode="${m}">${esc(modeLabel(m))}</button>`).join("")}
        </div>
        <p class="hint">„Urlaub“ überschreibt den Wecker für heute, „Heute aus“ deaktiviert ihn einmalig.</p>
      </section>`;
  }

  _cardAlexa(alexa) {
    const stopWord = alexa.stop_word || "Wecker aus";
    const routine = alexa.routine_name || "DAC Stopp";
    return `
      <section class="card">
        <h3>Alexa (Echo-Wecker)</h3>
        <div class="kv"><span>Status</span><b>${alexa.enabled ? "aktiv" : "aus"}</b></div>
        <div class="kv"><span>Echo</span><b>${esc(alexa.player ? this._entityName(alexa.player) : "—")}</b></div>
        <div class="kv"><span>Gesetzter Wecker</span><b>${esc(alexa.stored_alarm || "keiner")}</b></div>
        <div class="row">
          <button class="btn" id="alexa-set">Wecker setzen</button>
          <button class="btn ghost" id="alexa-sync">Sync</button>
          <button class="btn danger" id="alexa-clear">Löschen</button>
        </div>
        ${alexa.enabled ? "" : `<p class="hint">Aktiviere Alexa und wähle deinen Echo auf der Seite <button class="linklike" data-page="settings">Einstellungen</button> – dort genügt ein Suchbegriff wie „Echo“.</p>`}
        <p class="hint">Stoppen per Sprache: Alexa-App → Routine <b>„${esc(routine)}“</b>, Auslöser „Wecker mit dem Namen <b>${esc(stopWord)}</b> klingelt“, Aktion „Smart-Home-Gerät → DAC → Wecker stoppen“.</p>
      </section>`;
  }

  // --------------------------------------------------------------- Kalender
  _calendarPage(entry) {
    const cal = entry.calendar || { own: [], external: [], home_calendars: [] };
    const calendars = entry.calendars || [];
    const home = cal.home_calendars || [];
    return `
      <section class="card wide">
        <h3>Urlaubskalender</h3>
        <p class="muted">Tage markieren und mit einem Namen speichern. DAC legt sie im eigenen Kalender ab – sie erscheinen auch in Home Assistant.</p>
        ${this._calendar(cal)}
      </section>

      <section class="card wide">
        <h3>Home-Assistant-Kalender</h3>
        <p class="muted">Welche Kalender DAC als Urlaub/Feiertag wertet, stellst du in den <button class="linklike" data-page="settings">Einstellungen</button> ein.</p>
        ${this._calendarList(calendars)}
        <h4>Termine im Zeitraum</h4>
        ${this._homeEvents(home)}
      </section>`;
  }

  _calendarList(calendars) {
    if (!calendars.length) return `<p class="muted">Keine Kalender-Entitäten gefunden.</p>`;
    return `<div class="lists">${calendars.map((cal) => {
      const tags = [
        cal.is_own ? `<span class="tag own">DAC-Urlaub</span>` : "",
        cal.is_vacation ? `<span class="tag vac">Urlaub/Feiertag</span>` : "",
      ].join("");
      return `<div class="item">
        <span>${esc(cal.name)}<em class="muted"> ${esc(cal.id)}</em></span>
        <span>${tags || `<span class="tag">—</span>`}</span>
      </div>`;
    }).join("")}</div>`;
  }

  _homeEvents(events) {
    if (!events.length) {
      return `<p class="muted">Keine Termine. Wähle in den Einstellungen Kalender aus, um sie hier zu sehen.</p>`;
    }
    return `<div class="events">${events.slice(0, 60).map((ev) => `
      <div class="item">
        <span>${esc(dayLabel(ev.date))}${ev.all_day ? "" : ` · ${esc(this._eventTime(ev))}`}</span>
        <span>${esc(ev.summary)}</span>
        <button class="btn tiny" data-import="${esc(ev.date)}" data-summary="${esc(ev.summary)}" data-source="${esc(ev.calendar)}">als Urlaub</button>
      </div>`).join("")}</div>`;
  }

  _eventTime(ev) {
    const start = ev.start ? new Date(ev.start) : null;
    const end = ev.end ? new Date(ev.end) : null;
    if (!start || isNaN(start)) return "";
    const fmt = (d) => d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
    return end && !isNaN(end) ? `${fmt(start)}–${fmt(end)}` : fmt(start);
  }

  _calendar(cal) {
    const own = {};
    (cal.own || []).forEach((d) => { own[d.date] = d; });
    const external = {};
    (cal.external || []).forEach((d) => { external[d.date] = d; });
    const home = {};
    (cal.home_calendars || []).forEach((d) => { home[d.date] = d; });

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
        home[iso] ? "home" : "",
        this._selected.has(iso) ? "sel" : "",
        iso === todayIso ? "today" : "",
      ].join(" ");
      const title = own[iso]?.summary || external[iso]?.summary || home[iso]?.summary || "";
      cells.push(`<button class="${cls}" data-day="${iso}" title="${esc(title)}">${day}</button>`);
    }

    const selectedList = [...this._selected].sort();
    const ownList = (cal.own || []).slice().sort((a, b) => a.date.localeCompare(b.date)).slice(0, 40);
    const extList = (cal.external || []).slice().sort((a, b) => a.date.localeCompare(b.date)).slice(0, 40);

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
        <span><i class="dot home"></i> HA-Termin</span>
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
            <span>${esc(dayLabel(d.date))}</span><span class="muted">${esc(d.summary)}</span>
            <button class="btn tiny danger" data-remove="${esc(d.uid)}">✕</button>
          </div>`).join("") : `<p class="muted">Noch keine Urlaubstage.</p>`}
        </div>
        <div>
          <h4>Aus Kalendern erkannt</h4>
          ${extList.length ? extList.map((d) => `<div class="item">
            <span>${esc(dayLabel(d.date))}</span><span class="muted">${esc(d.summary)}</span>
          </div>`).join("") : `<p class="muted">Keine externen Urlaubstage im Zeitraum.</p>`}
        </div>
      </div>`;
  }

  // ------------------------------------------------------------ Einstellungen
  _settingsPage() {
    const s = this._settings;
    return `
      <section class="card wide">
        <div class="fieldsets">
          ${this._fieldsetZeiten(s)}
          ${this._fieldsetGeraete(s)}
          ${this._fieldsetAlexa(s)}
        </div>
        <div class="row end">
          <span class="dirty ${this._dirty ? "on" : ""}">${this._dirty ? "Ungespeicherte Änderungen" : "Alles gespeichert"}</span>
          <button class="btn" id="save-settings">Einstellungen speichern</button>
        </div>
      </section>`;
  }

  _fieldsetZeiten(s) {
    return `
      <fieldset class="fieldset">
        <legend>Zeiten &amp; Weckzyklus</legend>
        <div class="fields">
          ${this._fieldTime("default_alarm_time", "Standard-Weckzeit (Fallback)", s.default_alarm_time)}
          ${this._fieldNumber("offset_minutes", "Offset vor Arbeitsbeginn", s.offset_minutes, 0, 600, 5, "min")}
          ${this._fieldNumber("loop_interval_minutes", "Weck-Wiederholung", s.loop_interval_minutes, 1, 60, 1, "min")}
          ${this._fieldNumber("test_mode_minutes", "Testwecker nach", s.test_mode_minutes, 1, 120, 1, "min")}
          ${this._fieldTime("reminder_time", "Tägliche Erinnerung", s.reminder_time)}
          ${this._fieldText("reminder_text", "Erinnerungstext ({alarm_time})", s.reminder_text, "Denk an die Arbeitszeit!")}
          ${this._fieldText("vacation_keywords", "Urlaubs-Schlagwörter (Komma-getrennt)", s.vacation_keywords, "urlaub, feiertag")}
        </div>
      </fieldset>`;
  }

  _fieldsetGeraete(s) {
    return `
      <fieldset class="fieldset">
        <legend>Geräte &amp; Benachrichtigung</legend>
        <div class="fields">
          ${this._entityField("alarm_lights", "Weck-Lichter", s.alarm_lights, { multi: true })}
          ${this._entityField("vacation_calendars", "Urlaubs-Kalender", s.vacation_calendars, { multi: true })}
          ${this._fieldText("notifier", "Benachrichtigungsdienst", s.notifier, "notify.mobile_app_…")}
        </div>
      </fieldset>`;
  }

  _fieldsetAlexa(s) {
    return `
      <fieldset class="fieldset">
        <legend>Alexa (Echo-Wecker)</legend>
        <div class="fields">
          ${this._fieldSwitch("alexa_enabled", "Echten Wecker auf dem Echo stellen", s.alexa_enabled)}
          ${this._entityField("alexa_media_player", "Echo (Alexa)", s.alexa_media_player)}
          ${this._entityField("alexa_text_helper", "Helfer: gesetzter Wecker", s.alexa_text_helper)}
          ${this._entityField("alexa_enabled_boolean", "Helfer: Wecker aktiv", s.alexa_enabled_boolean)}
          ${this._fieldNumber("pre_alarm_minutes", "Vorab-Wecker Echo", s.pre_alarm_minutes, 0, 30, 1, "min")}
          ${this._fieldText("stop_word", "Stopp-Wort (Name des Echo-Weckers)", s.stop_word, "Wecker aus")}
        </div>
      </fieldset>`;
  }

  // ------------------------------------------------------------------- Hilfe
  _helpPage(entry) {
    const alexa = entry.alexa || {};
    return `
      <section class="card wide">
        <h3>So funktioniert DAC</h3>
        <ol class="steps">
          <li><b>Arbeitsbeginn setzen</b> – auf der Seite <button class="linklike" data-page="home">Home</button> per Uhrzeit, Schnellwahl oder Dienst <code>dac.set_work_time</code> (z. B. NFC-Tag).</li>
          <li><b>Weckzeit</b> – DAC rechnet automatisch Arbeitsbeginn − Offset und stellt den Wecker.</li>
          <li><b>Wecken</b> – Lichter gehen an, der Echo klingelt über seinen eigenen Wecker (kein TTS).</li>
          <li><b>Urlaub</b> – Tage im <button class="linklike" data-page="calendar">Kalender</button> markieren oder HA-Kalender koppeln; DAC weckt dann nicht.</li>
          <li><b>Testen</b> – im Testmodus klingelt die komplette Kette gefahrlos in X Minuten.</li>
        </ol>
      </section>

      <section class="card wide">
        <h3>Alexa einrichten (ohne genauen Namen zu kennen)</h3>
        <p class="muted">Auf der Seite <button class="linklike" data-page="settings">Einstellungen</button> genügt ein Suchbegriff – z. B. „Echo“ oder der Raumname. DAC schlägt alle passenden Geräte vor.</p>
        <div class="steps">
          <p>1. Einstellungen → „Echo (Alexa)“ → tippen und Vorschlag anklicken.</p>
          <p>2. Optional die beiden Helfer wählen: <code>input_text</code> (gesetzter Wecker) und <code>input_boolean</code> (Wecker aktiv).</p>
          <p>3. In der Alexa-App eine Routine <b>„${esc(alexa.routine_name || "DAC Stopp")}“</b> anlegen: Auslöser „Wecker mit dem Namen <b>${esc(alexa.stop_word || "Wecker aus")}</b> klingelt“, Aktion „Smart-Home-Gerät → DAC → Wecker stoppen“.</p>
        </div>
      </section>

      <section class="card wide">
        <h3>Dienste</h3>
        <div class="kv"><span>dac.set_work_time</span><b>Arbeitsbeginn setzen (NFC)</b></div>
        <div class="kv"><span>dac.stop_alarm</span><b>Wecker stoppen (auch von Alexa-Routine)</b></div>
        <div class="kv"><span>dac.start_test_alarm</span><b>Testwecker starten</b></div>
        <div class="kv"><span>dac.cancel_test_alarm</span><b>Testwecker abbrechen</b></div>
        <div class="kv"><span>dac.dismiss_for_today</span><b>Für heute deaktivieren</b></div>
        <div class="kv"><span>dac.set_alexa_alarm</span><b>Echo-Wecker setzen</b></div>
        <div class="kv"><span>dac.clear_alexa_alarm</span><b>DAC-eigenen Echo-Wecker löschen</b></div>
      </section>`;
  }

  // ------------------------------------------------------------------ wiring
  _wire() {
    this._wireNav();
    this._wireTabs();
    this._wireSettingsFields();
    this._wireEntityFields();

    const q = (sel) => this.shadowRoot.querySelector(sel);
    const stop = q("#stop");
    if (stop) stop.onclick = () => this._action({ action: "stop" });

    const workInput = q("#work-input");
    const setWork = q("#set-work");
    if (setWork) setWork.onclick = () =>
      this._action({ action: "set_work_time", time: `${workInput.value || "06:00"}:00` });
    const clearWork = q("#clear-work");
    if (clearWork) clearWork.onclick = () => this._action({ action: "clear_work_time" });

    this.shadowRoot.querySelectorAll("[data-work]").forEach((btn) =>
      btn.onclick = () => {
        if (workInput) workInput.value = btn.dataset.work;
        this._action({ action: "set_work_time", time: `${btn.dataset.work}:00` });
      });

    const testStart = q("#test-start");
    if (testStart) testStart.onclick = () => {
      const minutes = Number(q("#test-minutes").value) || 1;
      this._action({ action: "test_start", minutes });
    };
    const testCancel = q("#test-cancel");
    if (testCancel) testCancel.onclick = () => this._action({ action: "test_cancel" });

    this.shadowRoot.querySelectorAll("[data-mode]").forEach((btn) =>
      btn.onclick = () => this._action({ action: "mode", mode: btn.dataset.mode }));

    const alexaSet = q("#alexa-set");
    if (alexaSet) alexaSet.onclick = () => this._action({ action: "alexa_set" });
    const alexaSync = q("#alexa-sync");
    if (alexaSync) alexaSync.onclick = () => this._action({ action: "alexa_sync" });
    const alexaClear = q("#alexa-clear");
    if (alexaClear) alexaClear.onclick = () => this._action({ action: "alexa_clear" });

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

    this.shadowRoot.querySelectorAll("[data-import]").forEach((btn) =>
      btn.onclick = () => this._action({
        action: "import_vacation",
        date: btn.dataset.import,
        summary: btn.dataset.summary,
        source: btn.dataset.source,
      }));

    const save = q("#save-settings");
    if (save) save.onclick = () =>
      this._action({ action: "save_settings", settings: this._settings });
  }

  _selectRange(fromIso, toIso) {
    const parse = (iso) => {
      const [y, m, d] = String(iso).split("-").map(Number);
      return new Date(y, m - 1, d);
    };
    const from = parse(fromIso);
    const to = parse(toIso);
    const start = from <= to ? from : to;
    const end = from <= to ? to : from;
    this._selected.clear();
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      this._selected.add(localIso(d));
    }
  }
}

const STYLES = `
  :host { display: block; background: var(--primary-background-color, #f4f5f7); min-height: 100vh; }
  .wrap { max-width: 1100px; margin: 0 auto; padding: 16px; font-family: "Amazon Ember", var(--paper-font-body1_-_font-family, -apple-system, "Segoe UI", Roboto, sans-serif); color: var(--primary-text-color, #212121); }
  .nav { border-radius: 18px; padding: 14px 18px; color: #fff; background: linear-gradient(135deg, ${DAC_NAVY} 0%, #37475a 100%); box-shadow: 0 8px 26px rgba(0,0,0,.22); }
  .nav-top { display: flex; justify-content: space-between; align-items: baseline; }
  .nav-sub { opacity: .8; font-size: 13px; }
  .nav-pages { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 12px; }
  .page { background: rgba(255,255,255,.14); color: #fff; border: none; border-radius: 10px; padding: 9px 14px; cursor: pointer; font-size: 14px; }
  .page:hover { background: rgba(255,255,255,.26); }
  .page.on { background: ${DAC_AMBER}; color: #111; font-weight: 700; }
  .hero { border-radius: 18px; padding: 22px; color: #fff; margin-top: 16px; background: linear-gradient(135deg, ${DAC_NAVY} 0%, #37475a 100%); box-shadow: 0 8px 26px rgba(0,0,0,.22); }
  .tone-ringing { background: linear-gradient(135deg, #b12704, ${DAC_AMBER}); animation: pulse 1.2s infinite; }
  .tone-scheduled { background: linear-gradient(135deg, #146eb4, ${DAC_NAVY}); }
  .tone-test { background: linear-gradient(135deg, #0f7b6c, ${DAC_NAVY}); }
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
  .card.wide { margin-top: 16px; }
  .card.test-on { outline: 2px solid #0f7b6c; }
  h3 { margin: 0 0 6px; font-size: 16px; }
  h4 { margin: 12px 0 6px; font-size: 13px; text-transform: uppercase; letter-spacing: .5px; opacity: .6; }
  .badge { background: ${DAC_AMBER}; color: #111; border-radius: 999px; font-size: 11px; padding: 2px 9px; margin-left: 6px; vertical-align: middle; }
  .muted { color: var(--secondary-text-color, #6b7280); font-size: 13px; margin: 0 0 10px; }
  .hint { color: var(--secondary-text-color, #6b7280); font-size: 12px; margin: 6px 0 0; line-height: 1.5; }
  .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .row.end { justify-content: flex-end; margin-top: 14px; }
  .dirty { font-size: 12px; color: var(--secondary-text-color, #6b7280); margin-right: auto; }
  .dirty.on { color: ${DAC_AMBER}; font-weight: 700; }
  .btn { background: linear-gradient(180deg, #ffb84d, ${DAC_AMBER}); color: #111; border: none; border-radius: 10px; padding: 10px 16px; font-weight: 700; cursor: pointer; font-size: 14px; }
  .btn:hover { filter: brightness(1.06); }
  .btn.ghost { background: transparent; color: inherit; border: 1px solid var(--divider-color, rgba(0,0,0,.22)); }
  .btn.danger { background: #b12704; color: #fff; }
  .btn.tiny { padding: 3px 9px; font-size: 12px; }
  .btn.stop { background: #fff; color: #b12704; font-size: 16px; padding: 13px 22px; margin-top: 14px; width: 100%; }
  .linklike { background: none; border: none; color: #146eb4; cursor: pointer; padding: 0; font: inherit; text-decoration: underline; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
  .chip { background: var(--secondary-background-color, #eef1f5); border: 1px solid var(--divider-color, rgba(0,0,0,.1)); border-radius: 999px; padding: 6px 12px; cursor: pointer; font-size: 13px; color: inherit; }
  .suggestions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; min-height: 8px; }
  .chip.suggest { text-align: left; }
  .chip.suggest.alexa { border-color: #146eb4; background: rgba(20,110,180,.1); }
  .chip.suggest em { display: block; font-style: normal; opacity: .55; font-size: 11px; }
  .extra-label { width: 100%; font-size: 11px; text-transform: uppercase; letter-spacing: .5px; opacity: .5; margin-top: 4px; }
  .chosen-row { display: flex; gap: 6px; flex-wrap: wrap; }
  .chosen { background: ${DAC_NAVY}; color: #fff; border: none; border-radius: 999px; padding: 5px 11px; font-size: 12px; cursor: pointer; }
  .chosen b { opacity: .7; margin-left: 4px; }
  .seg { display: flex; gap: 6px; background: var(--secondary-background-color, #eef1f5); border-radius: 12px; padding: 4px; }
  .segbtn { flex: 1; border: none; background: transparent; border-radius: 9px; padding: 9px; cursor: pointer; font-weight: 600; color: inherit; }
  .segbtn.on { background: ${DAC_AMBER}; color: #111; }
  .kv { display: flex; justify-content: space-between; gap: 12px; padding: 5px 0; font-size: 14px; border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.07)); }
  .kv b { text-align: right; font-weight: 600; }
  .fieldsets { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-top: 8px; }
  .fieldset { border: 1px solid var(--divider-color, rgba(0,0,0,.1)); border-radius: 14px; padding: 10px 14px 14px; margin: 0; }
  .fieldset legend { font-size: 12px; text-transform: uppercase; letter-spacing: .6px; opacity: .65; padding: 0 6px; }
  .fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
  .field { display: flex; flex-direction: column; gap: 5px; font-size: 13px; }
  .field > span { color: var(--secondary-text-color, #6b7280); }
  .inp, .field input[type=text], .field input[type=number], .field input[type=time], .field select { background: var(--secondary-background-color, #eef1f5); border: 1px solid var(--divider-color, rgba(0,0,0,.12)); border-radius: 10px; padding: 9px 11px; font-size: 14px; color: inherit; width: 100%; box-sizing: border-box; }
  .inp.time { width: auto; font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .inp.small { width: 90px; }
  .entity-field .search { border-color: #146eb4; }
  .switch { display: flex; align-items: center; gap: 10px; font-size: 14px; padding: 6px 0; grid-column: 1 / -1; }
  .switch input { width: 20px; height: 20px; }
  .cal-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
  .cal-week, .cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; }
  .cal-week span { text-align: center; font-size: 12px; opacity: .6; padding: 4px 0; }
  .cell { aspect-ratio: 1 / 1; border-radius: 10px; border: 1px solid var(--divider-color, rgba(0,0,0,.08)); background: var(--secondary-background-color, #f0f2f5); cursor: pointer; font-size: 14px; color: inherit; display: flex; align-items: center; justify-content: center; }
  .cell.empty { background: transparent; border: none; cursor: default; }
  .cell.own { background: ${DAC_AMBER}; color: #111; font-weight: 700; }
  .cell.ext { background: #146eb4; color: #fff; }
  .cell.home { outline: 2px solid #0f7b6c; }
  .cell.sel { outline: 3px solid #146eb4; }
  .cell.today { box-shadow: inset 0 0 0 2px ${DAC_NAVY}; }
  .legend { display: flex; gap: 14px; flex-wrap: wrap; margin: 10px 0; font-size: 12px; color: var(--secondary-text-color, #6b7280); }
  .legend .dot { width: 10px; height: 10px; border-radius: 3px; box-shadow: none; display: inline-block; margin-right: 5px; }
  .legend .dot.own { background: ${DAC_AMBER}; }
  .legend .dot.ext { background: #146eb4; }
  .legend .dot.home { background: #0f7b6c; }
  .legend .dot.sel { background: transparent; outline: 2px solid #146eb4; }
  .lists { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin-top: 8px; }
  .events { display: flex; flex-direction: column; }
  .item { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 5px 0; font-size: 13px; border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.06)); }
  .item .muted { margin: 0; }
  .tag { font-size: 11px; background: var(--secondary-background-color, #eef1f5); border-radius: 999px; padding: 2px 9px; }
  .tag.own { background: ${DAC_AMBER}; color: #111; }
  .tag.vac { background: #146eb4; color: #fff; }
  .entries { display: flex; gap: 6px; margin-top: 16px; }
  .tab { background: var(--secondary-background-color, #eef1f5); border: none; border-radius: 9px; padding: 8px 14px; cursor: pointer; color: inherit; }
  .tab.on { background: ${DAC_AMBER}; color: #111; font-weight: 700; }
  .steps { margin: 0; padding-left: 18px; line-height: 1.7; font-size: 14px; }
  .steps p { margin: 4px 0; }
  code { background: var(--secondary-background-color, #eef1f5); border-radius: 5px; padding: 1px 5px; font-size: 12px; }
  .banner.error { background: #b12704; color: #fff; padding: 14px 16px; border-radius: 12px; }
  .empty { background: var(--card-background-color, #fff); border-radius: 16px; padding: 40px; text-align: center; }
  .toast { position: fixed; left: 50%; bottom: 26px; transform: translateX(-50%) translateY(20px); background: ${DAC_NAVY}; color: #fff; padding: 11px 20px; border-radius: 999px; font-size: 13px; opacity: 0; pointer-events: none; transition: all .25s ease; box-shadow: 0 8px 22px rgba(0,0,0,.3); }
  .toast.on { opacity: 1; transform: translateX(-50%) translateY(0); }
`;

if (!customElements.get("dac-panel")) {
  customElements.define("dac-panel", DacPanel);
}

if (window.console && window.console.info) {
  window.console.info(`%c DAC-PANEL %c ${DAC_VERSION} `,
    `background:${DAC_AMBER};color:#111;font-weight:700`, `background:${DAC_NAVY};color:#fff`);
}
