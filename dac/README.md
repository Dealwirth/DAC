# DAC – Dynamic Alarm Clock (Home Assistant App)

Ein dynamischer Wecker für Home Assistant – als **App (Add-on)**, installierbar
direkt aus dem App-Store, mit eigener Oberfläche im Home-Assistant-Look
(Alexa-Farben), Dashboard-Sensoren per MQTT und einem **echten Wecker auf dem
Amazon Echo**.

## Was DAC macht

DAC rechnet aus deinem **Arbeitsbeginn** und einem **Offset** die Weckzeit aus:

```
Arbeitsbeginn 06:45  −  Offset 60 min  =  Weckzeit 05:45
```

Abends stellst du nur deine Arbeitszeit (z. B. per Handy, NFC-Tag oder im
Dashboard). DAC übernimmt den Rest:

* **Weckt mit Licht** – schaltet die gewählten Lampen ein.
* **Echter Echo-Wecker** – DAC stellt auf dem Echo einen *echten* Gerätealarm.
  Der klingelt auch dann, wenn Home Assistant aus ist.
* **Weck-Loop** – solange du nicht stoppst, wiederholt DAC Licht und Echo-Wecker
  im eingestellten Intervall (Standard 5 Minuten).
* **Not-Aus** – nach N Minuten stoppt DAC sich selbst (0 = unbegrenzt).
* **Urlaub & Feiertage** – findet DAC im Kalender ein Stichwort wie *Urlaub*
  oder *Feiertag*, bleibt der Wecker aus.
* **Abend-Erinnerung** – hast du bis zur Erinnerungszeit keine Arbeitszeit
  gesetzt, schickt DAC eine Nachricht und sagt es optional leise auf dem Echo.
* **Ohne Arbeitszeit** – es greift die Standard-Weckzeit.

## Installation

1. **Einstellungen → Apps → App-Store**
2. Oben rechts auf die drei Punkte → **Repositories**
3. Diese URL hinzufügen:
   `https://github.com/Dealwirth/DAC`
4. **DAC – Dynamic Alarm Clock** installieren und starten.
5. In der Seitenleiste erscheint **DAC**.

Die App nutzt **Ingress**: Du brauchst keinen Port, keinen Token und keine
zusätzliche Anmeldung – die Oberfläche läuft innerhalb von Home Assistant.

## Einrichtung in 3 Schritten

1. **Echo wählen** (Reiter *Einstellungen → Amazon Alexa*): die
   `media_player`-Entität deines Echo auswählen. Dafür wird die
   [alexa_media](https://github.com/alandtse/alexa_media_player)-Integration
   benötigt.
2. **Lampen wählen** (*Licht beim Wecken*): welche Lampen beim Wecken angehen.
3. **Speichern** – fertig. Auf dem Reiter *Wecker* stellst du abends nur noch
   deine Arbeitszeit.

## Dashboard-Karten

Für ein schönes Dashboard veröffentlicht DAC (optional, per MQTT) fertige
Sensoren. Danach funktioniert diese Karte direkt:

```yaml
type: entities
title: DAC Wecker
entities:
  - sensor.dac_naechster_wecker
  - sensor.dac_status
  - sensor.dac_modus
  - sensor.dac_arbeitsbeginn
  - sensor.dac_weckzeit
  - sensor.dac_urlaub
  - sensor.dac_restzeit_minuten
```

Die Karten-Vorlagen stehen auch im Reiter **Hilfe** der App.

## Alexa-Sprachsteuerung (optional)

Damit du den Wecker auch per Sprache stoppen kannst:

1. In der Alexa-App eine Routine anlegen.
2. Auslöser: *„Wecker mit dem Namen … klingelt"* → Name `Wecker aus`
   (oder einen eigenen Namen, der in den Einstellungen unter *Wecker-Name*
   hinterlegt ist).
3. Aktion: Smart-Home-Gerät → das von DAC angelegte Skript
   (oder eine Automation, die `dac.stop_alarm` aufruft).

## Fehlersuche

* **Echo klingelt nicht** – Prüfen, ob der `media_player` richtig gewählt ist
  und ob die alexa_media-Integration läuft. Die App zeigt den zuletzt
  gestellten Wecker unter *Status → Echo*.
* **Wecker klingelt zur falschen Zeit** – Zeitzone der App übernehmen lassen
  (geschieht automatisch beim Start) und Offset prüfen.
* **Kein Licht** – Sind die Lampen ausgewählt und erreichbar?
* **Protokoll** – Einstellungen → Apps → DAC → *Protokoll*.

## Deinstallation

Die App im App-Store deinstallieren. Der gespeicherte Zustand liegt unter
`/data` und wird mit der App entfernt.
