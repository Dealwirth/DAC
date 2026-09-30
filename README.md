# DAC – Dynamic Alarm Clock ⏰

**Ein dynamisches Wecksystem für Home Assistant – als vollwertige HACS-Integration mit eigenem Dashboard, eigener Lovelace-Karte und optionalen echten Echo-Alexa-Weckern.**

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
| **Eigenes Dashboard** | „DAC Wecker"-Dashboard in der Seitenleiste (Lovelace-Storage) – fertig eingerichtet, voll editierbar |
| **Lovelace-Karte** | `custom:dac-wecker` als Lovelace-Ressource + fertiges „DAC Wecker"-Dashboard – automatisch registriert, in JEDEM Dashboard nutzbar |
| **Alexa-Geräte-Wecker** | Optional: echter Wecker auf dem Echo – Textbefehl mit „morgens"/„abends" (keine Rückfragen), gezieltes Löschen nur des DAC-eigenen Weckers, 2-Minuten-Vorab-Wecker im Weck-Loop |
| **Restpersistenz** | Wecker-Zustand überlebt Neustarts; ein Wecker, der während des Klingelns „verpasst" wurde, resumed |
| **Alles per UI** | Config-Flow + Options-Flow: Zeiten, Offset, Reminder, Notifier, Lichter, Player, Lautstärke |

## 📦 Installation

### HACS (empfohlen)

1. HACS → **Custom repositories** → Repository: `Dealwirth/DAC`, Kategorie: **Integration**
2. **DAC – Dynamic Alarm Clock** installieren
3. Home Assistant neu starten
4. *Einstellungen → Geräte & Dienste → Integration hinzufügen* → **DAC**

### Manuell

`custom_components/dac/` aus diesem Repo nach `<config>/custom_components/dac/` kopieren und HA neu starten.

## 🧭 Das DAC-Dashboard

Nach der Einrichtung erscheint **„DAC Wecker"** automatisch in der Seitenleiste:

- Große Uhr + Countdown bis zum Wecker
- Arbeitsbeginn per Zeileingabe setzen/zurücksetzen
- Modus: **Standard** / **Heute aus** / **Urlaub**
- Urlaubstage direkt in der Karte eintragen (eigener Kalender) oder löschen
- Roter Puls-Banner + Stop-Button, wenn der Wecker gerade klingelt

### 🃏 Lovelace-Karte für jedes Dashboard

Zusätzlich wird automatisch eine **Lovelace-Ressource** registriert und ein
fertiges Dashboard **„DAC Wecker"** (`/dac-wecker`) angelegt:

- Karte **„DAC Wecker“** (`custom:dac-wecker`) in jedem Dashboard über den
  Karten-Picker hinzufügen (unter *Benutzerdefinierte Karten*)
- Die Karte zeigt Uhr, Countdown, Status, Alexa-Wecker-Status,
  Arbeitsbeginn-Eingabe, Modus-Umschalter und die Urlaubsverwaltung
- Das Auto-Dashboard ist ein normaler Startpunkt – vollständig editierbar,
  deine Änderungen werden nie überschrieben

> Nutzt du Lovelace im YAML-Modus? Dann ergänze die Ressource manuell:
> `url: /dac/static/dac-card.js`, `type: module`.

### 🎨 Design

Die Karte ist im **Amazon-/Alexa-Look** gehalten: dunkles „Squid-Ink"-Blau
(`#232f3e`), Akzent in Alexa-Orange (`#ff9900`) und der typischen
Amazon-Ember-Schrift. Passend zum jeweiligen Status wechselt der Kopfbereich
die Farbe (ruhig/blau bei geplant, rot-orange pulsierend beim Klingeln,
grün im Urlaub, grau bei deaktiviert/gestoppt).

## ⚙️ Konfiguration (Options-Flow)

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
| Weck-Lautstärke | `0.5` | 0.0–1.0 |
| Alexa-Geräte-Wecker | `aus` | Echten Wecker zusätzlich auf dem Echo stellen (alexa_media) |
| Echo media_player | – | Welcher Echo-Player die Alexa-Befehle erhält (leer = Weck-Player) |
| input_text-Helfer | `input_text.gestellter_alexa_wecker` | Speichert den von DAC gesetzten Alexa-Wecker |
| input_boolean-Helfer | `input_boolean.wecker_aktiv` | Gate für den 2-Minuten-Vorab-Wecker im Weck-Loop |
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
3. **Weck-Loop**: Beim Klingeln schaltet DAC die Lichter und stellt alle
   5 Minuten einen neuen **2-Minuten-Vorab-Wecker** auf dem Echo – solange
   `input_boolean.wecker_aktiv` an ist.
4. **Deaktivierung (Tag 4)**: Stoppt den Loop, schaltet den Helfer aus und
   setzt den gespeicherten Wecker-Text zurück.

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

73 Tests decken die komplette Weck-Logik ab: Offset-Berechnung, Mitternachts-Wrap,
Fallback-/Cutoff-Semantik inkl. Oversleep-Schutz, Weck-Loop, Dismiss, Vacation-Check,
Reminder, Persistenz, Alexa-Bridge (morgens/abends, gezieltes Löschen, Vorab-Wecker),
Lovelace-Ressourcen-/Dashboard-Registrierung (inkl. Element-/Typ-Abgleich),
Config-/Options-Flow und Service-Registrierung.

## 📄 Lizenz

MIT – siehe [LICENSE](LICENSE).
