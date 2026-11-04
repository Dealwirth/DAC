# AGENTS.md – DAC – Dynamic Alarm Clock

## Projekt
Home Assistant Custom Integration (`custom_components/dac`), verteilt via HACS.
Repo: https://github.com/Dealwirth/DAC

## Umgebung
- Python 3.13, Home Assistant 2026.2.3 (Test-Matrix in `.github/workflows/ci.yml`).
- Tests: `python -m pytest tests -q` (131 Tests). Konfiguration in `pytest.ini`.
- Lint: `python -m ruff check custom_components tests`.
- JS-Syntaxcheck: `node --check custom_components/dac/www/dac-panel.js`.

## Architektur (wichtig)
- **Konfiguration liegt komplett im DAC-Dashboard** (`www/dac-panel.js`,
  registriert in `frontend.py` über `panel_custom`): **ein** Sidebar-Eintrag
  `/dac` (`<dac-panel>`) mit vier Seiten – Home, Kalender, Einstellungen, Hilfe
  (interne Navigation über `_page` / `data-page`). Der Config-Flow stellt keine
  Fragen und legt nur einen Entry mit `default_options()` an.
- `settings.py` ist die Single Source of Truth für Optionen: `default_options()`,
  `EDITABLE_KEYS`, `coerce_options()`, `build_settings_schema()`, `vacation_keywords()`.
  Neue Optionen immer hier ergänzen (plus `translations/{en,de}.json` und Panel-JS).
- `http_api.py` (`DacApiView`, `/api/dac`) ist die API des Dashboards (GET=Zustand,
  POST=Aktionen). `entries[].entities` ist EINE flache Liste
  (`{id, name, domain, area, alexa}`) über `ENTITY_SEARCH_EXCLUDE_DOMAINS`; das
  Panel filtert lokal über `searchEntities()` (`FIELD_DOMAINS` in `dac-panel.js`)
  nach Name, Entity-ID und Area – Domain-Treffer zuerst, andere unter „auch gefunden".
  Zusätzlich: `entries[].calendars` (alle HA-Kalender + Rolle) und
  `entries[].calendar.home_calendars` (echte Termine via `calendar.get_events`).
  Urlaubstage liegen als Ganztages-Events im `calendar.py`-Store;
  `import_vacation` übernimmt einen HA-Kalendertag in den DAC-Kalender.
- `coordinator.py` liest Optionen aus **`entry.data` UND `entry.options`** (gemerged) –
  beide Speicherwege (Panel und Options-Flow) müssen identisch funktionieren.
- `logic.py` ist HA-frei und unit-testbar; `alexa.py` kapselt die Echo-Wecker
  (Textbefehl immer `media_content_type: custom`, gezieltes Löschen nur des eigenen
  Weckers, Gate-Steuerung `input_boolean.wecker_aktiv`, Vorab-Wecker im Loop).
  **DAC spielt kein TTS und macht keine Ansagen** – es legt einen echten
  Echo-Wecker (wie die YAML-Automation) und schaltet im Loop nur das Licht.
  Das Gate setzt DAC selbst (an beim Planen/Klingeln, aus beim Stoppen) – es ist
  ein Sicherheitsnetz, keine Voraussetzung. Echo-Wecker werden mit dem
  konfigurierbaren Stopp-Wort (`CONF_STOP_WORD`) benannt; die Alexa-Routine
  „DAC Stopp" (Auslöser: Wecker mit diesem Namen klingelt) ruft `dac.stop_alarm`
  auf – so lässt sich der Wecker per Sprache stoppen (kein Custom-Skill nötig).
- **Testmodus**: `async_start_test_alarm` / `async_cancel_test_alarm` armen einen
  Einmal-Wecker (`_test_target`) relativ zur aktuellen Zeit; er nutzt dieselbe
  Weck-Kette wie der echte Wecker und wird über `dac.stop_alarm` beendet. Ein
  gestoppter Testwecker darf den echten Wecker des Tages NICHT verbrauchen
  (nicht in `_stopped_days` eintragen).
- **Weck-Intervall**: `coordinator.loop_interval_minutes` (Option
  `CONF_LOOP_INTERVAL_MINUTES`, 1–60, Standard 5) steuert die Wiederholung bis
  zum Stopp.
- **Not-Aus**: `coordinator.max_ring_minutes` (Option `CONF_MAX_RING_MINUTES`,
  0–600, Standard 60, 0 = unbegrenzt) beendet einen nie gestoppten Wecker
  selbst (`_loop_tick` → `_ring_expired`). Zusätzlich räumt `_clear_stale_state`
  einen „ringing/stopped/dismissed"-Zustand vom Vortag auf (Licht aus, Loop
  aus) und `_reschedule_alarm` lehnt eine Neuplanung ab, solange der Wecker
  klingelt (`_state == STATE_RINGING`) – so kann kein „ringing" mit
  morgigem Ziel entstehen.
- **Aufräumen nach dem Wecken (wichtig, live verifiziert)**:
  - `dac.stop_alarm` schaltet die Weck-Lichter aus (`_async_turn_off_lights`)
    und beendet den Loop – auch der Not-Aus nutzt diesen Pfad.
  - Der kurze **Vorab-Wecker** auf dem Echo wird beim Stopp mitgelöscht
    (`AlexaBridge.async_clear_pre_alarm`, gemerkt in `_pre_alarm`); er steht
    NICHT im `input_text`-Helper. Ohne dieses Löschen klingelt der Echo nach
    „Wecker stoppen" Minuten später trotzdem.
  - Ein gestoppter **Testwecker** setzt `STATE_IDLE` (nicht `STATE_STOPPED`) und
    trägt sich nicht in `_stopped_days` ein – sonst verwirft
    `_reschedule_alarm` die echte Arbeitszeit und der nächste Wecker fällt auf
    die Standard-Zeit zurück.
  - Licht-Dienste werden mit `except Exception` abgefangen (`# noqa: BLE001`):
    ein fehlendes oder werfendes Licht darf den Weck-Loop nie abbrechen,
    bevor der Echo-Vorab-Wecker gesetzt wurde.
- Entfernte Optionen (`media_players`, `alarm_volume`, `wake_text`,
  `alexa_command_type`) sind bewusst gelöscht; `coerce_options()` filtert sie aus
  alten Config-Entries heraus (siehe `test_coerce_options_removed_keys_are_ignored`).

## Live-Instanz (Testumgebung des Nutzers)
- HA: `https://petryss.duckdns.org:8123` (DuckDNS + HTTPS, selbstsigniertes Zertifikat).
- HACS-Repo-ID von DAC: `1358438282`; Update per WebSocket
  (`hacs/repository/refresh` → `hacs/repositories/list` → `hacs/repository/download`).
- Wichtige Entitäten: Wecklichter `light.1/2/3`, Echo `media_player.max_echo_media`,
  Gate `input_boolean.wecker_aktiv`, Helper `input_text.gestellter_alexa_wecker`,
  Arbeitsbeginn `input_datetime.arbeitsbeginn`.
- Die frühere YAML-Automation `automation.nfc_weckersystem_komplett`
  (id `1785685720632`) wurde auf DAC-Dienste umgestellt: NFC-Tags → `dac.set_work_time`
  (Tag 1 = 06:00, Tag 2 = 07:00), Tag 4 → `dac.stop_alarm`, Arbeitsbeginn-Helfer →
  `dac.set_work_time`. Das alte Script `script.wecker_alexa_licht_schleife` ist nicht mehr nötig.
- Dashboard-API zum Speichern von Optionen: `POST /api/dac {"action":"save_settings",...}`.
  Panel-Aktionen heißen `test_start` / `test_cancel` (nicht `cancel_test`).

## Konventionen
- Kein Dauer-Polling im Panel: der Server ist Single Source of Truth, nach jeder
  Aktion wird neu geladen; nur Uhr/Countdown laufen lokal.
- Datums-ISO-Strings im Panel immer lokal bilden (`localIso()`), nie
  `toISOString()` (UTC-Verschiebung).
- Tests dürfen keine Mocks für echte Codepfade nutzen; HA-Testhelpers
  (`pytest_homeassistant_custom_component`) verwenden.

## Sicherheit
- Keine Tokens/Secrets im Repo oder in der Git-History ablegen.
