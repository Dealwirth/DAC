# AGENTS.md – DAC – Dynamic Alarm Clock

## Projekt
Home Assistant Custom Integration (`custom_components/dac`), verteilt via HACS.
Repo: https://github.com/Dealwirth/DAC

## Umgebung
- Python 3.13, Home Assistant 2026.2.3 (Test-Matrix in `.github/workflows/ci.yml`).
- Tests: `python -m pytest tests -q` (116 Tests). Konfiguration in `pytest.ini`.
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
- Entfernte Optionen (`media_players`, `alarm_volume`, `wake_text`,
  `alexa_command_type`) sind bewusst gelöscht; `coerce_options()` filtert sie aus
  alten Config-Entries heraus (siehe `test_coerce_options_removed_keys_are_ignored`).

## Konventionen
- Kein Dauer-Polling im Panel: der Server ist Single Source of Truth, nach jeder
  Aktion wird neu geladen; nur Uhr/Countdown laufen lokal.
- Datums-ISO-Strings im Panel immer lokal bilden (`localIso()`), nie
  `toISOString()` (UTC-Verschiebung).
- Tests dürfen keine Mocks für echte Codepfade nutzen; HA-Testhelpers
  (`pytest_homeassistant_custom_component`) verwenden.

## Sicherheit
- Keine Tokens/Secrets im Repo oder in der Git-History ablegen.
