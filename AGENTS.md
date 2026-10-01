# AGENTS.md – DAC – Dynamic Alarm Clock

## Projekt
Home Assistant Custom Integration (`custom_components/dac`), verteilt via HACS.
Repo: https://github.com/Dealwirth/DAC

## Umgebung
- Python 3.13, Home Assistant 2026.2.3 (Test-Matrix in `.github/workflows/ci.yml`).
- Tests: `python -m pytest tests -q` (83 Tests). Konfiguration in `pytest.ini`.
- Lint: `python -m pyflakes custom_components/dac/*.py tests/*.py`.
- JS-Syntaxcheck: `node --check custom_components/dac/www/dac-panel.js`.

## Architektur (wichtig)
- **Konfiguration liegt komplett im Sidebar-Panel** (`www/dac-panel.js`, registriert
  in `frontend.py` über `panel_custom`, Pfad `/dac`). Der Config-Flow stellt keine
  Fragen und legt nur einen Entry mit `default_options()` an.
- `settings.py` ist die Single Source of Truth für Optionen: `default_options()`,
  `EDITABLE_KEYS`, `coerce_options()`, `build_settings_schema()`, `vacation_keywords()`.
  Neue Optionen immer hier ergänzen (plus `translations/{en,de}.json` und Panel-JS).
- `http_api.py` (`DacApiView`, `/api/dac`) ist die API des Panels (GET=Zustand,
  POST=Aktionen). Urlaubstage liegen als Ganztages-Events im `calendar.py`-Store.
- `coordinator.py` liest Optionen aus **`entry.data` UND `entry.options`** (gemerged) –
  beide Speicherwege (Panel und Options-Flow) müssen identisch funktionieren.
- `logic.py` ist HA-frei und unit-testbar; `alexa.py` kapselt die Echo-Wecker
  (Textbefehl mit Befehlstyp `custom`/`tts`, gezieltes Löschen nur des eigenen
  Weckers, Gate-Steuerung `input_boolean.wecker_aktiv`, Vorab-Wecker im Loop).
  Das Gate setzt DAC selbst (an beim Planen/Klingeln, aus beim Stoppen) – es ist
  ein Sicherheitsnetz, keine Voraussetzung.

## Konventionen
- Kein Dauer-Polling im Panel: der Server ist Single Source of Truth, nach jeder
  Aktion wird neu geladen; nur Uhr/Countdown laufen lokal.
- Datums-ISO-Strings im Panel immer lokal bilden (`localIso()`), nie
  `toISOString()` (UTC-Verschiebung).
- Tests dürfen keine Mocks für echte Codepfade nutzen; HA-Testhelpers
  (`pytest_homeassistant_custom_component`) verwenden.

## Sicherheit
- Keine Tokens/Secrets im Repo oder in der Git-History ablegen.
