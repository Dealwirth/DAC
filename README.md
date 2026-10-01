# DAC – Dynamic Alarm Clock ⏰

**Ein dynamisches Wecksystem für Home Assistant – als vollwertige HACS-Integration mit eigenem Seitenleisten-Panel, vollständiger Konfiguration auf der Seite und optionalen echten Echo-Alexa-Weckern.**

DAC berechnet deine Weckzeit automatisch aus dem Arbeitsbeginn (z. B. per NFC-Tag gescannt),
weckt dich mit Licht + Alexa/Echo-Media-Playern im 5-Minuten-Intervall, respektiert Urlaub
und Feiertage über einen Kalender und erinnert dich abends, wenn du vergessen hast,
deine Arbeitszeit zu setzen.

---

## ✨ Features

| Feature | Beschreibung |
|---|---|
| **Dynamischer Wecker** | Arbeitsbeginn setzen (NFC, Dashboard, Dienst oder Entität) → Weckzeit = Arbeitsbeginn − Offset |
| **Weck-Loop** | Licht an + TTS-Ansage auf Media-Playern, alle 5 Minuten, bis explizit gestoppt (z. B. Deaktivierungs-NFC-Tag) |
| **Fallback-Weckzeit** | Wurde nichts gesetzt, greift eine konfigurierbare Standard-Weckzeit (z. B. 06:00) – mit intelligenter Cutoff-Logik |
| **Urlaub & Feiertage** | Täglicher Scan (00:01) gegen einen eigenen Urlaubskalender und/oder externe Kalender; Keywords wie *Urlaub, Feiertag, Ferien, vacation, holiday* |
| **Reminder** | Tägliche Erinnerung (z. B. 20:30) via frei wählbarem `notify.*`-Dienst, wenn für morgen noch keine Arbeitszeit gesetzt wurde |
| **Seitenleisten-Panel** | Eigener „DAC“-Eintrag in der Seitenleiste – alle Einstellungen, Wecker, Urlaubskalender und Alexa direkt auf einer Seite (kein Einrichtungsassistent nötig) |
| **Schöne Zeitwahl** | Zeiten werden über ein Zeitrad (Stunden/Minuten) mit Schnellauswahl gewählt – kein manuelles Tippen von `HH:MM` |
| **Echter Monatskalender** | Urlaubstage bequem im Monatsraster markieren (Einzel- und Bereichsauswahl per Shift-Klick), eigene und erkannte Tage auf einen Blick |
| **Alexa-Geräte-Wecker** | Optional: echter Wecker auf dem Echo – Textbefehl mit „morgens"/„abends" (keine Rückfragen), gezieltes Löschen nur des DAC-eigenen Weckers, 2-Minuten-Vorab-Wecker im Weck-Loop |
| **Restpersistenz** | Wecker-Zustand überlebt Neustarts; ein Wecker, der während des Klingelns „verpasst" wurde, resumed |
| **Alles per UI** | Der Einrichtungsassistent fragt nichts ab; alle Optionen werden im Panel gespeichert (Options-Flow bleibt als HA-nativer Fallback) |

## 📦 Installation

### HACS (empfohlen)

1. HACS → **Custom repositories** → Repository: `Dealwirth/DAC`, Kategorie: **Integration**
2. **DAC – Dynamic Alarm Clock** installieren
3. Home Assistant neu starten
4. *Einstellungen → Geräte & Dienste → Integration hinzufügen* → **DAC**

### Manuell

`custom_components/dac/` aus diesem Repo nach `<config>/custom_components/dac/` kopieren und HA neu starten.

## 🧭 Das DAC-Panel (Seitenleiste)

Nach der Einrichtung erscheint **„DAC"** automatisch in der Seitenleiste
(`/dac`). Alles passiert auf dieser einen Seite:

- Große Uhr + Countdown bis zum Wecker
- **Arbeitsbeginn** per Zeitrad (Stunden/Minuten) oder Schnellauswahl setzen/zurücksetzen
- Modus: **Standard** / **Heute aus** / **Urlaub**
- **Alexa**: Wecker stellen/synchronisieren/löschen inkl. Live-Status des Echos
- **Einstellungen**: sämtliche Optionen (Zeiten, Offset, Notifier, Lichter, Player,
  Lautstärke, Weck-Ansage, Urlaubs-Schlagwörter, Alexa) direkt auf der Seite – ein Klick speichert
- **Urlaubskalender**: Monatsraster mit eigener und externer Urlaubserkennung

> Der Einrichtungsassistent fragt **nichts** ab: Integration hinzufügen genügt,
> danach alles im Panel einstellen. Für Puristen bleibt der klassische
> Options-Flow (Geräte & Dienste → DAC → Konfigurieren) erhalten.

### 🎨 Design

HA-Design trifft Amazon/Alexa: dunkles „Squid-Ink"-Blau (`#232f3e`),
Alexa-Orange (`#ff9900`) als Akzent und die typische Amazon-Ember-Schrift.
Der Kopfbereich wechselt passend zum Status die Farbe (ruhig/blau bei geplant,
rot-orange pulsierend beim Klingeln, grün im Urlaub, grau bei deaktiviert/gestoppt).

## ⚙️ Konfiguration

Alle Optionen werden direkt im Panel gespeichert; der klassische Options-Flow
(Geräte & Dienste → DAC → Konfigurieren) bietet dieselben Felder.

| Option | Standard | Bedeutung |
|---|---|---|
| Standard-Weckzeit | `06:00` | Fallback, wenn keine Arbeitszeit gesetzt wurde |
| Offset (Minuten) | `60` | So lange vor Arbeitsbeginn wird geweckt |
| Reminder-Uhrzeit | `20:30` | Täglicher Status-Check |
| Reminder-Text | „⏰ DAC: …" | `{alarm_time}` wird durch die Standard-Weckzeit ersetzt |
| Notifier | `notify.notify` | Beliebiger `notify.*`-Dienst (WhatsApp, Mobile App, …) |
| Weck-Lichter | – | `light.*`-Entitäten, die beim Wecken angehen |
| Media-Player | – | `media_player.*` (z. B. Echo), erhalten TTS + Lautstärke |
| Urlaubs-Kalender | – | Externe Kalender für Vacation-Check (zusätzlich zum eigenen) |
| Urlaubs-Schlagwörter | `urlaub, urlaubstag, feiertag, ferien, freizeitausgleich, vacation, holiday` | Wörter, die einen Kalendertag als Urlaub/Feiertag markieren |
| Weck-Ansage | „Guten Morgen! …" | TTS-Text, der beim Wecken abgespielt wird |
| Weck-Lautstärke | `0.5` | 0.0–1.0 |
| Alexa-Geräte-Wecker | `aus` | Echten Wecker zusätzlich auf dem Echo stellen (alexa_media) |
| Echo media_player | – | Welcher Echo-Player die Alexa-Befehle erhält (leer = Weck-Player) |
| input_text-Helfer | `input_text.gestellter_alexa_wecker` | Speichert den von DAC gesetzten Alexa-Wecker |
| input_boolean-Helfer | `input_boolean.wecker_aktiv` | Gate für den 2-Minuten-Vorab-Wecker im Weck-Loop (DAC schaltet ihn selbst) |
| Alexa-Befehlstyp | `custom` | `custom` = reiner Textbefehl (empfohlen, wie in der klassischen YAML-Automation), `tts` = gesprochen |
| Vorab-Wecker | `2` min | Der Echo-Wecker klingelt so viele Minuten vor der Weckzeit |

### Fallback-/Cutoff-Logik

- Standard-Weckzeit heute noch nicht vorbei → gilt heute.
- Standard-Weckzeit vorbei, **vor** der Reminder-Zeit → nichts geplant (du wirst noch erinnert).
- Standard-Weckzeit vorbei, **nach** der Reminder-Zeit (Cutoff) → Standard-Weckzeit für morgen.
- Arbeitszeit-Scans nach dem Cutoff gelten automatisch für **morgen**.
- **Oversleep-Schutz:** Sobald die Reminder-Zeit erreicht ist, wird der
  Standard-Wecker verbindlich für den nächsten Tag scharf geschaltet –
  selbst wenn du die Erinnerung ignorierst, verschläfst du nicht.

## 🛠️ Dienste (Services)

### `dac.set_work_time`

```yaml
service: dac.set_work_time
data:
  time: "08:00"        # Arbeitsbeginn
  # day: "2026-09-07"  # optional: expliziter Tag
  # clear: true        # optional: manuelle Zeit zurücksetzen
```

Perfekt für NFC-Tags (**Helfer → Tag** → Automation):

```yaml
automation:
  - alias: "NFC-Tag: Arbeitszeit setzen"
    triggers:
      - trigger: tag
        tag_id: 1234abcd-...
    actions:
      - action: dac.set_work_time
        data:
          time: "08:00"

  - alias: "NFC-Tag: Wecker ausschalten"
    triggers:
      - trigger: tag
        tag_id: 5678efgh-...
    actions:
      - action: dac.stop_alarm
```

### `dac.stop_alarm`

Stoppt die laufende Weck-Schleife (Media-Player werden gestoppt).

### `dac.dismiss_for_today`

```yaml
service: dac.dismiss_for_today
data:
  # day: "2026-09-07"  # optional, sonst heutiger/kommender Tag
```

Deaktiviert den Wecker für den Tag (z. B. spontaner freier Tag).

### `dac.set_alexa_alarm` / `dac.clear_alexa_alarm`

```yaml
service: dac.set_alexa_alarm   # berechneten Wecker zusätzlich auf den Echo legen
service: dac.clear_alexa_alarm # NUR den von DAC gesetzten Echo-Wecker löschen
```

So funktioniert der Alexa-Geräte-Wecker:

1. **Stellen**: „stelle einen Wecker auf 05:00 Uhr **morgens**“ – die 24h-Zeit
   wird automatisch um „morgens“/„abends“ ergänzt, Alexa fragt nie nach.
2. **Gezieltes Löschen**: Gespeichert im Helfer
   `input_text.gestellter_alexa_wecker`. Bei Tagwechsel, Zeitänderung oder
   Deaktivierung wird exakt nur dieser Wecker gelöscht
   („lösche den Wecker um 06:00 Uhr“) – **manuelle Alexa-Wecker bleiben unberührt**.
3. **Weck-Loop**: Beim Klingeln schaltet DAC die Lichter, stellt den Gate-Helfer
   `input_boolean.wecker_aktiv` selbst auf **an** und legt alle 5 Minuten einen
   neuen **Vorab-Wecker** auf dem Echo – so klingelt der Echo auch dann, wenn
   Home Assistant ausfällt.
4. **Deaktivierung (Tag 4)**: Stoppt den Loop, schaltet den Gate-Helfer aus,
   löscht nur den DAC-eigenen Echo-Wecker und setzt den gespeicherten
   Wecker-Text zurück.

### Verhältnis zur klassischen YAML-Automation

Die Integration bildet die bewährte „NFC Weckersystem"-Automation ab und
übernimmt sie vollständig – eine eigene Automation ist **nicht mehr nötig**:

| YAML | DAC |
|---|---|
| Tag 1/2 → feste Weckzeit + Alexa-Wecker | `dac.set_work_time` (Zeit frei wählbar) bzw. Panel |
| Tag 3 → Benachrichtigung | täglicher Reminder |
| Tag 4 → Wecker aus | `dac.stop_alarm` (Löscht Echo-Wecker, Gate aus) |
| `input_datetime.arbeitsbeginn` → −1 h | Offset-Option + `dac.set_work_time` / `time.dac_arbeitsbeginn` |
| `script.wecker_alexa_licht_schleife` | eingebauter 5-Minuten-Weck-Loop (Licht + TTS) |
| Alexa „lösche den Wecker um …" | `dac.clear_alexa_alarm` (nur der eigene Wecker) |
| `media_content_type: custom` | Option **Alexa-Befehlstyp** = `custom` |

Die NFC-Tags selbst hängen weiterhin an den DAC-Diensten (siehe unten), z. B.
Tag 1 → `dac.set_work_time` mit `time: "05:00"`, Tag 4 → `dac.stop_alarm`.

> Einmalig nötig: die Helfer `input_text.gestellter_alexa_wecker` und
> `input_boolean.wecker_aktiv` anlegen (oder eigene in den Optionen wählen)
> und die **Alexa Media Player**-Integration installieren.

## 🧩 Entitäten

| Entität | Zweck |
|---|---|
| `sensor.dac_next_alarm` | Nächste berechnete Weckzeit (Timestamp) + Attribute: Status, Arbeitsbeginn, Offset, Modus … |
| `select.dac_modus` | Modus: Standard / Heute aus / Urlaub |
| `time.dac_arbeitsbeginn` | Arbeitsbeginn direkt per UI setzen (wie der Service) |
| `calendar.dac_urlaubskalender` | Eigener, editierbarer Urlaubskalender (UI-Kalender-Editor kompatibel) |

## 🧪 Entwicklung

```bash
py -m venv .venv
.venv/Scripts/python -m pip install -r requirements_test.txt   # Linux/Mac: .venv/bin/python
.venv/Scripts/python -m pytest tests -v
```

90 Tests decken die komplette Weck-Logik ab: Offset-Berechnung, Mitternachts-Wrap,
Fallback-/Cutoff-Semantik inkl. Oversleep-Schutz, Weck-Loop, Dismiss, Vacation-Check,
Reminder, Persistenz, Alexa-Bridge (morgens/abends, Befehlstyp, gezieltes Löschen,
Vorab-Wecker, Gate-Steuerung), Options-Schema/-Normalisierung, HTTP-API
(Panel-Aktionen, Urlaubs-CRUD), Seitenleisten-Panel-Registrierung,
Config-/Options-Flow und Service-Registrierung.

## 📄 Lizenz

MIT – siehe [LICENSE](LICENSE).
