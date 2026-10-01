# DAC – Dynamic Alarm Clock ⏰

**Ein dynamisches Wecksystem für Home Assistant – als vollwertige HACS-Integration mit einem Dashboard (Home, Kalender, Einstellungen, Hilfe), durchsuchbarer Entitäten-Auswahl und optionalen echten Echo-Alexa-Weckern.**

DAC berechnet deine Weckzeit automatisch aus dem Arbeitsbeginn (z. B. per NFC-Tag gescannt),
weckt dich mit Licht und einem echten Wecker auf dem Echo im einstellbaren Intervall
(Standard 5 min) bis du ihn stoppst, respektiert Urlaub und Feiertage über einen Kalender
und erinnert dich abends, wenn du vergessen hast, deine Arbeitszeit zu setzen.

---

## ✨ Features

| Feature | Beschreibung |
|---|---|
| **Dynamischer Wecker** | Arbeitsbeginn setzen (NFC, Dashboard, Dienst oder Entität) → Weckzeit = Arbeitsbeginn − Offset |
| **Weck-Loop** | Licht an + neuer Echo-Wecker im einstellbaren Intervall (1–60 min, Standard 5), bis explizit gestoppt (Home Assistant, Panel oder Alexa) |
| **Fallback-Weckzeit** | Wurde nichts gesetzt, greift eine konfigurierbare Standard-Weckzeit (z. B. 06:00) – mit intelligenter Cutoff-Logik |
| **Urlaub & Feiertage** | Täglicher Scan (00:01) gegen einen eigenen Urlaubskalender und/oder externe Kalender; Keywords wie *Urlaub, Feiertag, Ferien, vacation, holiday* |
| **Reminder** | Tägliche Erinnerung (z. B. 20:30) via frei wählbarem `notify.*`-Dienst, wenn für morgen noch keine Arbeitszeit gesetzt wurde |
| **Ein Dashboard, mehrere Seiten** | Ein Sidebar-Eintrag „DAC“ (`/dac`) mit den Seiten **Home**, **Kalender**, **Einstellungen** und **Hilfe** – kein Einrichtungsassistent nötig |
| **Einfache Zeitwahl** | Native Zeitauswahl (`<input type="time">`) plus Schnellwahl-Chips – kein Zifferblatt-Rad, kein manuelles Tippen von `HH:MM` |
| **Echter Monatskalender** | Urlaubstage bequem im Monatsraster markieren (Einzel- und Bereichsauswahl per Shift-Klick), eigene und erkannte Tage auf einen Blick |
| **Kalender-Kopplung** | Die Kalender-Seite zeigt alle Home-Assistant-Kalender und deren Termine; ein Termin lässt sich mit einem Klick als DAC-Urlaubstag übernehmen |
| **Alexa-Geräte-Wecker** | Optional: echter Wecker auf dem Echo – Textbefehl mit „morgens"/„abends" (keine Rückfragen), gezieltes Löschen nur des DAC-eigenen Weckers, Vorab-Wecker im Weck-Loop |
| **Keine Ansagen** | DAC spielt **kein TTS** ab: Der Echo klingelt über seinen eigenen Wecker, Home Assistant schaltet nur das Licht – wie in der klassischen YAML-Automation |
| **Live-Entitäten-Suche** | Jedes Entitätsfeld **ist** ein Suchfeld: Tippen filtert sofort über Name, Entity-ID und **Bereich (Area)** – passende Domains zuerst, „auch gefunden" danach. So findest du deinen Echo, ohne den genauen Namen zu kennen |
| **Testmodus** | Direkt in die Home-Seite integriert: einmaliger Testwecker in X Minuten – gleiche Kette (Licht, Echo, Wiederholung), gleicher Stopp |
| **Stopp per Sprache** | Über eine Alexa-Routine („Wecker mit dem Namen *Wecker aus* klingelt“ → `dac.stop_alarm`) lässt sich der Wecker auch per Echo beenden |
| **Restpersistenz** | Wecker-Zustand überlebt Neustarts; ein Wecker, der während des Klingelns „verpasst" wurde, resumed |
| **Alles per UI** | Der Einrichtungsassistent fragt nichts ab; alle Optionen werden auf der Einstellungsseite gespeichert (Options-Flow bleibt als HA-nativer Fallback) |

## 📦 Installation

### HACS (empfohlen)

1. HACS → **Custom repositories** → Repository: `Dealwirth/DAC`, Kategorie: **Integration**
2. **DAC – Dynamic Alarm Clock** installieren
3. Home Assistant neu starten
4. *Einstellungen → Geräte & Dienste → Integration hinzufügen* → **DAC**

### Manuell

`custom_components/dac/` aus diesem Repo nach `<config>/custom_components/dac/` kopieren und HA neu starten.

## 🧭 Das DAC-Dashboard (Seitenleiste)

Nach der Einrichtung erscheint **ein** Eintrag in der Seitenleiste: **„DAC“** (`/dac`).
Oben wechselst du zwischen vier Seiten:

### 🏠 Home – Steuerung

- Große Uhr + Countdown bis zum Wecker
- **Arbeitsbeginn** per nativer Zeitauswahl oder Schnellwahl-Chips setzen/zurücksetzen
- **Testmodus**: Testwecker in X Minuten starten/abbrechen – gleiche Kette wie der echte Wecker
- Modus: **Standard** / **Heute aus** / **Urlaub**
- **Alexa**: Wecker stellen/synchronisieren/löschen inkl. Live-Status des Echos und Stopp-Wort

### 📅 Kalender – Urlaub & HA-Kopplung

- **Urlaubskalender**: Monatsraster mit eigener und externer Urlaubserkennung;
  Tage anklicken (Shift-Klick für einen Bereich) und mit einem Namen speichern
- **Home-Assistant-Kalender**: Liste aller Kalender mit ihrer Rolle
  (DAC-Urlaub / Urlaub-Feiertag) und die **echten Termine** aus den gekoppelten
  Kalendern. Jeder Termin lässt sich mit einem Klick **als DAC-Urlaubstag übernehmen** –
  so ist der DAC-Kalender mit deinen HA-Kalendern gekoppelt.

### ⚙️ Einstellungen – alle Optionen

- Drei aufgeräumte Gruppen (Zeiten & Weckzyklus, Geräte & Benachrichtigung, Alexa)
- **Live-Entitäten-Suche**: Jedes Feld **ist** ein Suchfeld. Tippen filtert sofort
  über **Name, Entity-ID und Bereich (Area)**; Treffer aus den passenden Domains
  stehen zuerst, andere Domains erscheinen unter „auch gefunden". Echo-Player sind
  mit 🔊 markiert. So findest du z. B. deinen Echo über „Echo" oder „Küche",
  ohne den genauen Entity-Namen zu kennen.
- Gewählte Einträge erscheinen als Chips über dem Feld und lassen sich dort
  mit einem Klick wieder entfernen.
- Ein Button speichert alles.

### ❓ Hilfe – Einrichtung & Dienste

- Kurzanleitung in fünf Schritten
- **Alexa einrichten** ohne den genauen Namen zu kennen (Schritt für Schritt)
- Übersicht aller `dac.*`-Dienste

> Der Einrichtungsassistent fragt **nichts** ab: Integration hinzufügen genügt,
> danach alles im Dashboard einstellen. Für Puristen bleibt der
> klassische Options-Flow (Geräte & Dienste → DAC → Konfigurieren) erhalten.

### 🎨 Design

HA-Design trifft Amazon/Alexa: dunkles „Squid-Ink"-Blau (`#232f3e`),
Alexa-Orange (`#ff9900`) als Akzent und die typische Amazon-Ember-Schrift.
Der Kopfbereich wechselt passend zum Status die Farbe (ruhig/blau bei geplant,
rot-orange pulsierend beim Klingeln, grün im Urlaub, grau bei deaktiviert/gestoppt).

## ⚙️ Konfiguration

Alle Optionen werden auf der Seite **Einstellungen** im DAC-Dashboard (`/dac`)
gespeichert; der klassische Options-Flow (Geräte & Dienste → DAC → Konfigurieren)
bietet dieselben Felder.

| Option | Standard | Bedeutung |
|---|---|---|
| Standard-Weckzeit | `06:00` | Fallback, wenn keine Arbeitszeit gesetzt wurde |
| Offset (Minuten) | `60` | So lange vor Arbeitsbeginn wird geweckt |
| Weck-Wiederholung | `5` min | Alle so viele Minuten (1–60) wird erneut geweckt, bis gestoppt wird |
| Testwecker nach | `1` min | Vorbelegung für den Testmodus (klingelt in X Minuten) |
| Reminder-Uhrzeit | `20:30` | Täglicher Status-Check |
| Reminder-Text | „⏰ DAC: …" | `{alarm_time}` wird durch die Standard-Weckzeit ersetzt |
| Urlaubs-Schlagwörter | `urlaub, urlaubstag, feiertag, ferien, freizeitausgleich, vacation, holiday` | Wörter, die einen Kalendertag als Urlaub/Feiertag markieren |
| Weck-Lichter | – | `light.*`-Entitäten, die beim Wecken angehen |
| Urlaubs-Kalender | – | Externe Kalender für den Vacation-Check (zusätzlich zum eigenen) |
| Notifier | `notify.notify` | Beliebiger `notify.*`-Dienst (WhatsApp, Mobile App, …) |
| Alexa-Geräte-Wecker | `aus` | Echten Wecker auf dem Echo stellen (alexa_media) |
| Echo | – | Welcher `media_player` die Alexa-Befehle erhält (per Suche wählen) |
| input_text-Helfer | `input_text.gestellter_alexa_wecker` | Speichert den von DAC gesetzten Echo-Wecker |
| input_boolean-Helfer | `input_boolean.wecker_aktiv` | Gate für den Vorab-Wecker im Weck-Loop (DAC schaltet ihn selbst) |
| Vorab-Wecker | `2` min | Der Echo-Wecker klingelt so viele Minuten vor der Weckzeit |
| Stopp-Wort | `Wecker aus` | Name der Echo-Wecker; Auslöser für die Alexa-Stopp-Routine |

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

Stoppt die laufende Weck-Schleife (Licht) und löscht den Echo-Wecker.
**Genau dieser Dienst wird von der Alexa-Stopp-Routine aufgerufen**,
damit der Wecker auch per Sprache beendet werden kann.

### `dac.start_test_alarm` / `dac.cancel_test_alarm`

```yaml
service: dac.start_test_alarm
data:
  minutes: 1        # optional, sonst die eingestellte Testdauer

service: dac.cancel_test_alarm   # bricht einen noch nicht klingelnden Test ab
```

Der Testwecker nutzt exakt dieselbe Kette wie der echte Wecker (Licht,
Echo-Vorab-Wecker) und wird über `dac.stop_alarm`, den Panel-Button oder
das Alexa-Stopp-Wort beendet.

### Wecker per Alexa stoppen (ohne Custom-Skill)

1. In der Alexa-App eine Routine anlegen, z. B. **„DAC Stopp“**.
2. Auslöser: **„Wecker klingelt“ → Wecker mit dem Namen `Wecker aus`** (das Stopp-Wort aus den Einstellungen).
3. Aktion: **Smart-Home-Gerät → DAC → Wecker stoppen** (ruft `dac.stop_alarm` auf).

DAC benennt jeden Echo-Wecker, den es stellt, mit genau diesem Stopp-Wort. Beim
Klingeln des Echo-Weckers löst die Routine aus und beendet die Weck-Schleife –
so reicht „Alexa, Wecker aus“ bzw. das Betätigen des Weckers am Echo, um DAC zu stoppen.

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
3. **Weck-Loop**: Beim Klingeln schaltet DAC die Lichter und legt im
   eingestellten Intervall (Standard 5 Minuten) einen neuen **Vorab-Wecker** auf
   dem Echo – so klingelt der Echo auch dann, wenn Home Assistant ausfällt.
   DAC spielt **keine Ansage** ab; der Echo klingelt über seinen eigenen Wecker.
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
| `script.wecker_alexa_licht_schleife` | eingebauter Weck-Loop (Licht + Echo-Wecker im Intervall) |
| Alexa „lösche den Wecker um …" | `dac.clear_alexa_alarm` (nur der eigene Wecker) |

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

116 Tests decken die komplette Weck-Logik ab: Offset-Berechnung, Mitternachts-Wrap,
Fallback-/Cutoff-Semantik inkl. Oversleep-Schutz, Weck-Loop mit einstellbarem
Intervall, Testmodus (Armen/Klingeln/Abbruch/Stopp), Dismiss, Vacation-Check,
Reminder, Persistenz, Alexa-Bridge (morgens/abends, echter Geräte-Wecker ohne TTS,
gezieltes Löschen, Vorab-Wecker, Gate-Steuerung, Stopp-Wort), Options-Schema und
-Normalisierung, HTTP-API (Panel-Aktionen inkl. Testmodus, durchsuchbare
Entitäts-Liste mit Bereich/Echo-Markierung, Kalender-Liste und -Import,
Urlaubs-CRUD), Registrierung des Dashboards, Panel-JS (Seiten, Live-Suche –
die Suchfunktion wird direkt in Node ausgeführt), Config-/Options-Flow und
Service-Registrierung.

## 📄 Lizenz

MIT – siehe [LICENSE](LICENSE).
