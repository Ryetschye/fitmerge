# fitmerge – zwei FIT-Aktivitäten zu einer zusammenführen

`fitmerge.py` fügt zwei nacheinander aufgezeichnete Garmin-Aktivitäten zu **einer** Aktivität zusammen – so,
als wäre zwischendurch nicht gespeichert worden. Ergebnis: eine Session, ein Lap pro Teil, dazwischen eine
Timer-Pause. Entwickelt und geprüft mit Dateien eines **Garmin Edge 1050** (Firmware 33.13, FIT-Profil 21.218).

Stand: 24.10.2026

---

## Inhalt des Repos

| Datei | Zweck | Abhängigkeiten |
|---|---|---|
| `fitmerge.py` | Das eigentliche Werkzeug: führt zwei FIT-Dateien zusammen | nur Python-Standardbibliothek |
| `validate.py` | Prüft ein Merge-Ergebnis gegen die beiden Originale (inkl. Regressionstest) | `fitdecode`, `garmin-fit-sdk` |
| `compare.py` | Vergleicht beliebige Ergebnisdateien mit den Originalen (z. B. fitmerge vs. FIT File Repair Tool) | `fitdecode`, `garmin-fit-sdk` |
| `cumulative.py` | Findet Laufsummen-Felder und zeigt die Distanz an der Nahtstelle | `fitdecode` |
| `analyze.py` | Überblick einer FIT-Datei: Header, Message-Zählung, Reihenfolge | `fitdecode` |
| `events.py` | Kernfelder von activity/session/lap/split/event/time_in_zone | `fitdecode` |
| `fields.py` | Alle Felder eines Message-Typs aus drei Dateien nebeneinander | `fitdecode` |
| `devinfo.py` | Developer-Data-IDs und Feldbeschreibungen (Connect-IQ-Felder) | `fitdecode` |
| `inspect2.py` | Rohfelder ausgewählter Message-Typen mit Feldnummer und Basistyp | `fitdecode` |

---

## Schnellstart

Voraussetzung: Python 3 (getestet mit 3.14.6) unter Windows mit PowerShell 7. Für `fitmerge.py` selbst ist nichts zu
installieren.

### 1. Repo holen

```powershell
git clone https://github.com/Ryetschye/fitmerge.git
```

Alle folgenden Aufrufe von `python …` laufen im geklonten Ordner `fitmerge`.

### 2. Originale aus Garmin Connect holen

Für **beide** Teilaktivitäten: Aktivität öffnen → Zahnrad → *Original exportieren*. Garmin liefert eine ZIP mit
`<Aktivitäts-ID>_ACTIVITY.fit`. Entpacken und als `teil1.fit` (früherer Teil) bzw. `teil2.fit` ablegen –
Arbeitsverzeichnis: Download-Ordner, `ERSTE_ID` und `ZWEITE_ID` durch die Namen der beiden ZIP-Dateien ersetzen:

```powershell
Expand-Archive .\ERSTE_ID.zip .\teil1; Expand-Archive .\ZWEITE_ID.zip .\teil2; Move-Item .\teil1\*.fit .\teil1.fit; Move-Item .\teil2\*.fit .\teil2.fit
```

### 3. Zusammenführen

```powershell
python fitmerge.py $HOME\Downloads\teil1.fit $HOME\Downloads\teil2.fit $HOME\Downloads\merged.fit
```

- Reihenfolge der Argumente: **zuerst der zeitlich frühere Teil**, dann der spätere, dann die Ausgabedatei.
- Eine vorhandene Ausgabedatei wird ohne Rückfrage überschrieben.
- Bei Erfolg erscheint `wrote <Ausgabedatei>`; bei nicht unterstützten Dateien bricht das Skript mit einer
  Fehlermeldung ab und schreibt nichts (siehe [Grenzen](#grenzen-und-fehlermeldungen)).

### 4. Optional: Ergebnis prüfen

Einmalig eine virtuelle Umgebung für die Prüfskripte anlegen:

```powershell
python -m venv .venv; .\.venv\Scripts\python -m pip install fitdecode garmin-fit-sdk
```

Prüfen:

```powershell
.\.venv\Scripts\python validate.py $HOME\Downloads\merged.fit $HOME\Downloads\teil1.fit $HOME\Downloads\teil2.fit
```

Erwartet:

- `sdk is_fit: True integrity: True` und `sdk errors: []` – das offizielle Garmin-FIT-SDK liest die Datei fehlerfrei
- `records identical to A+B (running totals excluded): True`
- `record timestamps strictly increasing: True`
- `REGRESSION PASS`
- In der Tabelle am Ende nur die gewollten Abweichungen (Duplikate entfernt, siehe [Was das Tool macht](#was-das-tool-macht))

Hinweis: Die venv nicht unter einem sehr langen Pfad anlegen – Windows bricht `python -m venv` bei Pfaden über
260 Zeichen mit `WinError 206` ab.

### 5. Hochladen

1. In Garmin Connect **zuerst beide Teilaktivitäten löschen**. Die zusammengeführte Datei trägt die Kennung
   (Seriennummer + Erstellzeit) und den Startzeitpunkt von Teil 1 und würde sonst als Duplikat abgelehnt.
2. Garmin Connect → *Daten importieren* → zusammengeführte `.fit` hochladen.
3. Falls Strava automatisch synchronisiert: die beiden alten Aktivitäten **in Strava separat löschen** – Löschungen in
   Garmin Connect werden nicht an Strava weitergegeben.

Der Upload in Garmin Connect und Strava ist Stand 24.10.2026 **nicht verifiziert**.

---

## Was das Tool macht

### Grundprinzip

`fitmerge.py` arbeitet auf dem rohen FIT-Datenstrom. Jede Message beider Dateien wird **Byte für Byte** übernommen –
inklusive aller proprietären Garmin-Messages und der Developer-Felder von Connect-IQ-Apps (z. B. CORE-Körpertemperatur,
Ruuvi-Sensor). Neu berechnet werden nur die Zusammenfassungen und die Laufsummen in Teil 2. Nichts wird geschätzt oder
geglättet.

### Ergebnisstruktur

| Bestandteil | Ergebnis |
|---|---|
| `file_id`, `file_creator` | von Teil 1 |
| `activity` | eine; Fahrzeit = Summe beider Teile |
| `session` | eine; alle Kennzahlen aus beiden Teilen neu berechnet (Regeln unten) |
| `lap` | zwei: Lap 0 = Teil 1 (Auslöser `manual`), Lap 1 = Teil 2 (Auslöser `session_end`) |
| `event` | Timer-Stopp am Ende von Teil 1, Timer-Start am Anfang von Teil 2 – wie bei einer pausierten Aufzeichnung |
| `record` | alle Messpunkte beider Teile; `distance` und `accumulated_power` laufen in Teil 2 weiter |
| `split` | alle Splits beider Teile, durchnummeriert |
| `split_summary` | je Split-Typ zusammengefasst |
| `time_in_zone` | Session: Zonenzeiten addiert; Laps/Splits: Verweise auf die neuen Indizes angepasst |
| Physiologie-Zusammenfassung (Msg 140) | von Teil 2, Höhenmeter/Ø-Leistung/Ø-Puls auf beide Teile angepasst |
| Einstellungsblock (`user_profile`, `sport`, `zones_target`, `device_settings`, `training_settings`, Msg 141/147/394) | fehlt er in Teil 1, wird der aus Teil 2 an die in Edge-Dateien übliche Stelle vorgezogen und steht einmal in der Datei; haben beide Teile einen, bleiben beide an ihrer Stelle |
| Developer-Deklarationen | von Teil 1 (Obermenge); identische Wiederholungen aus Teil 2 entfallen |
| Recovery-HR-Marker | nur der von Teil 2 (Ende der Gesamtaktivität) |

### Rechenregeln der Session-Werte

| Regel | Felder (Auswahl) |
|---|---|
| Summe | Distanz, Fahrzeit, Kurbelumdrehungen, Kalorien, Höhenmeter hoch/runter, Arbeit, Stehzeit, Steh-Anzahl, Training Load, metabolische Kalorien |
| Maximum | max. Puls/Leistung/Trittfrequenz/Geschwindigkeit/Temperatur/Atemfrequenz/Kerntemperatur, Training Effect (aerob und anaerob), Nordost-Ecke der Bounding Box |
| Minimum | min. Temperatur/Atemfrequenz/Kerntemperatur, Südwest-Ecke der Bounding Box |
| Nach Fahrzeit gewichteter Mittelwert | Ø Puls, Ø Leistung, Ø Trittfrequenz, Ø Temperatur, Ø Kerntemperatur, Ø Atemfrequenz, Drehmomenteffektivität, Tretrundheit, PCO, Ø VAM |
| Gewichteter Mittelwert auf dem Kreis | Power-Phase-Winkel (damit 355° und 5° nicht 180° ergeben) |
| Gewichteter Mittelwert mit Seitenflag | Links/Rechts-Balance |
| Neu berechnet | Ø Geschwindigkeit = Distanz / Fahrzeit |
| Neu berechnet | Normalized Power, Intensity Factor, TSS: aus den effektiven Zeiten hinter den TSS-Werten beider Teile (NP über die 4. Potenz kombiniert, IF = NP / FTP, TSS = t · IF² / 36) |
| Startwerte | Startzeit und Startposition von Teil 1 |
| Endwerte | Endposition von Teil 2 |
| Gesamtzeit | Start Teil 1 bis Ende Teil 2, **inklusive** der Pause dazwischen |

Die Gesamtzeit von Lap 1 enthält die Pause vor dem Neustart – genau so schreibt der Edge selbst Laps nach einem manuellen
Stopp und Neustart (siehe [Erkenntnisse](#erkenntnisse)). Die Summe der Lap-Gesamtzeiten ergibt damit die Session-Gesamtzeit.

### Weitere Korrekturen

- **Laufsummen in den Messpunkten:** `distance` und `accumulated_power` in Teil 2 werden um den letzten Wert von Teil 1
  versetzt. Ohne das springt die Distanz an der Nahtstelle auf 0 zurück und Strava sähe nur die Strecke von Teil 2.
- **Pausen-Splits:** Splits, die Teil 1 nach dem Stopp bis zum Speichern weitergeschrieben hat, werden so gekürzt, dass sie
  nicht in Teil 2 hineinragen.
- **Einheitliche Zeitstempel:** Der Edge stempelt alle Zusammenfassungs-Messages mit dem Aktivitätsstart; Lap 1 und ihre
  Zonenzeiten bekommen deshalb ebenfalls den Start von Teil 1.

### Prüfungen beim Einlesen

- Dateikennung `.FIT` und Datei-CRC beider Eingaben
- Keine komprimierten Zeitstempel-Header (nicht unterstützt)
- Teil 2 muss nach Teil 1 beginnen
- Jede Eingabe enthält genau eine activity, session, lap und Physiologie-Zusammenfassung
- Alle Split-Typen von Teil 2 müssen auch in Teil 1 vorkommen

Die Ausgabedatei erhält einen korrekten 14-Byte-Header mit Header-CRC und eine neue Datei-CRC.

---

## Grenzen und Fehlermeldungen

| Situation | Verhalten |
|---|---|
| Mehr als zwei Teile | Nicht unterstützt. Ein Ergebnis lässt sich nicht erneut als Teil 1 verwenden, weil es zwei Laps hat. |
| Teil mit mehreren Laps (Lap-Taste gedrückt, Auto-Lap) | Abbruch mit `expected exactly one message 19, found N` |
| Teile in falscher Reihenfolge | Abbruch mit `second file must start after the first one` |
| Beschädigte Datei | Abbruch mit `file CRC mismatch` |
| Andere Geräte als Edge 1050 | Nicht getestet. Das Tool erwartet das Edge-Layout (Zusammenfassung **vor** der ersten `timestamp_correlation`-Message). Andere Layouts brechen in der Regel ab (z. B. `expected exactly one message 34, found 0` oder eine Python-Fehlermeldung); ein Ergebnis aus solchen Dateien vor dem Upload unbedingt mit `validate.py` prüfen. |
| Komprimierte Zeitstempel | Abbruch mit `compressed timestamp headers are not supported` |
| Split-Typ nur in Teil 2 | Abbruch mit `split types only in second file: [...]` |

Annahmen, die man kennen sollte:

- **Training Effect und Training Load** berechnet Garmin mit einem proprietären Verfahren (Firstbeat), das sich nicht
  nachbauen lässt. Das Tool setzt den Training Effect auf den höheren der beiden Werte und den Training Load auf die Summe
  (damit die Wochenbelastung gleich bleibt).
- **NP/IF/TSS** sind aus den beiden Teilwerten kombiniert, nicht aus den Einzelmesspunkten neu berechnet. Im Beispiel unten
  ergibt das 25,7 statt der Summe der Teil-TSS von 25,1.
- **Undokumentierte Garmin-Felder** (Session-Felder 138, 178, 188, 202, 205–207; Teile der Physiologie-Zusammenfassung)
  werden nach beobachtetem Verhalten behandelt (Summe bzw. gewichteter Mittelwert). Ihre Bedeutung ist nicht bekannt.
- **Gesamtzeit** schließt die Pause zwischen den Teilen ein. Garmin Connect zeigt damit z. B. 2:09 h Gesamtzeit bei 31 min
  Fahrzeit – so, wie es der Edge bei einer durchgehend pausierten Aufzeichnung auch tun würde.

---

## Hilfsskripte im Detail

Alle mit `.\.venv\Scripts\python <skript> …` im Repo-Ordner aufrufen.

| Aufruf | Ausgabe |
|---|---|
| `validate.py <merged> <teil1> <teil2>` | SDK-Integrität, Messpunkt-Vergleich, Regressionstest Laufsummen, Message-Zählung mit Abweichungen |
| `compare.py <teil1> <teil2> <kandidat> [<kandidat> …]` | Je Kandidat: Header, file_id, Message-Typen, fehlende Typen, Session/Lap-Werte, verlorene und geänderte Messpunkt-Felder |
| `cumulative.py <teil1> <teil2> <merged> <fixed>` | Laufsummen-Kandidaten, Distanz an der Nahtstelle in beiden Ergebnissen, fehlende Messpunkte, Geschwindigkeitsabweichung, Developer-Felder |
| `analyze.py <datei> [--full]` | Header, Zusammenfassungs-Messages, Message-Zählung, Zeitraum der Messpunkte, Reihenfolge der Messages |
| `events.py <datei>` | Kernfelder aller activity/session/lap/split/split_summary/time_in_zone/event-Messages |
| `fields.py <message> <teil1> <teil2> <referenz>` | Erste Message des Typs aus drei Dateien nebeneinander, z. B. `fields.py session …` |
| `devinfo.py <datei> [<datei> …]` | Developer-Data-IDs (App-ID, Version), Feldbeschreibungen, Definitionen mit Developer-Feldern, Dateiende |
| `inspect2.py <datei> [<typ>,<typ>…]` | Rohfelder der genannten Typen (z. B. `unknown_140,developer_data_id`), Anzahl komprimierter Zeitstempel, Anfang/Ende der Message-Folge |

`cumulative.py` und `fields.py` sind für das Beispiel unten geschrieben (feste Argumentanzahl, Nahtstelle wird über die
erste Stunde 17 gesucht) und eher als Vorlage zu verstehen.

---

## Erkenntnisse

### Beispiel: Pendelfahrt mit Zwischenstopp (22.10.2026)

| | Teil 1 | Teil 2 | Zusammengeführt |
|---|---|---|---|
| Zeitraum | 15:29:26–15:41:19 UTC | 17:16:46–17:38:36 UTC | 15:29:26–17:38:36 UTC |
| Distanz | 4,65 km | 5,62 km | 10,27 km |
| Fahrzeit | 11:01 | 19:53 | 30:54 |
| Gesamtzeit | 11:54 | 21:50 | 2:09:10 |
| Höhenmeter hoch / runter | 6 / 89 | 91 / 10 | 97 / 99 |
| kcal | 94 | 186 | 280 |
| Ø / max. Puls | 89 / 115 | 111 / 152 | 103 / 152 |
| Ø Leistung / NP | 119 / 143 W | 133 / 184 W | 128 / 173 W |
| TSS / IF | 6,2 / 0,594 | 18,9 / 0,764 | 25,7 / 0,717 |
| Messpunkte | 666 | 1201 | 1867 |

Ablauf laut Dateien: In Teil 1 wurde um 15:41:27 manuell gestoppt, gespeichert aber erst um 17:16:22 (Teil 1 enthält bis
dahin Pausen-Splits); um 17:16:46 begann Teil 2.

Prüfergebnis der zusammengeführten Datei: Garmin-FIT-SDK `integrity: True`, keine Lesefehler; alle 1867 Messpunkte
unverändert bis auf die versetzten Laufsummen; Zeitstempel streng aufsteigend; Regressionstest bestanden.

### Aufbau der Edge-1050-Dateien

- Die Zusammenfassung (activity, session, laps, splits, split_summary) steht **am Dateianfang**, vor der ersten
  `timestamp_correlation`-Message. Danach folgt der Datenstrom (Events, Geräteinfos, Messpunkte, HRV usw.).
- Alle Zusammenfassungs-Messages tragen als Zeitstempel den **Aktivitätsstart**, nicht ihr Ende.
- Nach einem **manuellen Stopp und Neustart** beginnt ein neuer Lap; dessen Gesamtzeit enthält die Pause davor.
  Belegt durch eine durchgehend aufgezeichnete Referenzaktivität vom 20.10.2026 (1 Session, 3 Laps): Lap 3 startet
  19:15:35, gefahren wurde bis 19:30:33, die Gesamtzeit beträgt aber 4845 s – sie enthält die Pause nach dem Stopp um
  18:09:19. Die Summe der Lap-Gesamtzeiten ergibt exakt die Session-Gesamtzeit (803,6 + 649,3 + 4845,1 = 6298,1 s).
- Ausnahme in derselben Referenz: Die lange Pause von 15:39 bis 17:59 fehlt in der Gesamtzeit. Vermutlich war das Gerät in
  dieser Zeit ausgeschaltet (nicht belegt).
- Pro Messpunkt schreibt der Edge eine proprietäre Begleit-Message (Nr. 534) und laufend HRV-Messages.
- Laufsummen in den Messpunkten: `distance` und `accumulated_power`.
- Developer-Felder stammen von zwei Connect-IQ-Apps mit gleichen Indizes in beiden Teilen (Index 0: CORE-Temperatur,
  Index 1: Ruuvi). Teil 1 hat zusätzlich Index 2 (nur ein Geräteinfo-Feld in der Session).

### Vergleich mit dem FIT File Repair Tool

Das FIT File Repair Tool importiert die Dateien in seine Access-Datenbank, rechnet dort neu (laut Log u. a.
*Reset Power Statistics Values*, *ReconstructSpeedValues*, *ResetDistanceValues*, *RecalcValuesSession*) und exportiert eine
neue FIT-Datei. Ergebnis des Vergleichs für das Beispiel oben:

| | fitmerge.py | FIT File Repair Tool |
|---|---|---|
| Höhenmeter hoch / runter | 97 / 99 ✓ | 91 / 10 ✗ (nur Teil 2) |
| Fahrzeit | 30:54 (Gerätewert) | 31:06 (aus Anzahl der Messpunkte) |
| Fahrzeit im activity-Datensatz | 30:54 ✓ | 2:09:09 ✗ (Gesamtzeit eingetragen) |
| Training Load | 50 (Summe) | 40,5 (nur Teil 2) |
| Messpunkte | 1867 | 1866 (letzter fehlt) |
| Geschwindigkeit pro Messpunkt | Gerätewerte | 1847 Werte neu berechnet (Abweichung im Median 0,05 m/s) |
| Ø Leistung Lap 1 | 119 W (Gerätewert) | 114 W (nach Tool-Einstellung neu berechnet) |
| Distanz in Teil 2 fortgeschrieben | ✓ (seit Korrektur) | ✓ |
| Zeit in Zonen, Splits, ClimbPro | vorhanden | fehlen |
| HRV-Messages | 2428 | 2262 |
| Geräteinfos | 32 | 6 |
| Proprietäre Garmin-Messages | alle | größtenteils entfernt |
| Developer-Felder (CORE, Ruuvi) | vorhanden | vorhanden |
| Garmin-SDK-Integrität | ✓ | ✓ |

Fazit: fitmerge.py liefert die vollständigere und originalgetreuere Datei. Das Repair Tool ist universeller (viele
Formate, Reparatur beschädigter Dateien), verändert aber Messwerte und verwirft Daten.

### Behobener Fehler: Distanz in Teil 2 begann bei null

Die erste Version übernahm die Messpunkte von Teil 2 unverändert. Dadurch fiel `distance` an der Nahtstelle von
4645,92 m auf 3,88 m zurück (ebenso `accumulated_power` von 78 480 auf 92); der letzte Messpunkt zeigte 5,6 statt 10,3 km.
Garmin Connect liest die Gesamtwerte aus der Session (dort korrekt), Strava liest die Distanz aus den Messpunkten.

Aufgefallen ist das erst beim Vergleich mit dem Repair Tool, das die Distanz fortgeschrieben hatte.

**Warum die Prüfung den Fehler nicht fand:** `validate.py` prüfte, ob alle Messpunkte byte-gleich zu den Originalen sind –
für Laufsummen ist genau das falsch, und ein Abgleich des letzten Distanzwerts mit der Session-Distanz fehlte.

**Regressionstest (in `validate.py`):** `distance` und `accumulated_power` dürfen in der ganzen Datei nie fallen, Teil 2
muss um den Endwert von Teil 1 versetzt sein, und der letzte Distanzwert muss der Session-Distanz entsprechen. Die
fehlerhafte Datei fällt durch (`REGRESSION FAIL`), die korrigierte besteht (`REGRESSION PASS`).

### Offene Punkte

- Upload der zusammengeführten Datei in Garmin Connect und Strava nicht verifiziert.
- Nur mit Edge-1050-Dateien getestet.
- Die Beispieldateien sind nicht Teil des Repos (Aktivitätsdaten bleiben lokal, siehe `.gitignore`).

---

## Lizenz

MIT – siehe [LICENSE](LICENSE).
