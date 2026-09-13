# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary

# TextToGeometry — Bedienungsanleitung

Eine FreeCAD-Workbench, die im Gespräch konstruiert: Sie sagen, was gebaut
werden soll, das Werkzeug legt ein Projekt an, klärt die Maße, erzeugt
wiederverwendbare Bauteil-Generatoren und baut sie ins Dokument.

Das Modell läuft dabei **lokal** (Ollama) oder über einen **API-Zugang**.

---

## 1. In fünf Minuten zum ersten Bauteil

1. FreeCAD starten, oben die Workbench **TextToGeometry** wählen.
2. In der Werkzeugleiste erscheint ein Eingabefeld. Dort tippen:

   ```
   baue eine lavalduese
   ```
   und Enter drücken.
3. Rechts klappt das Panel auf. Der Agent legt ein Projekt an, recherchiert und
   zeigt eine **Eingabemaske** mit den Maßen, die er braucht — vorbelegt mit
   seinen Vorschlägen.
4. Werte prüfen, **Übernehmen und weiter**.
5. Nach ein bis zwei Minuten steht der Körper im Dokument.

Läuft etwas schief, steht der Grund im Verlauf. Nichts wird heimlich gemacht:
Unter jeder Abschlussmeldung zeigt eine Zeile **„Tatsächlich:"**, was wirklich
ausgeführt wurde.

---

## 2. Installation

### Auf diesem Rechner

```sh
python3 install.py                                # findet die Mod-Ordner selbst
python3 install.py --freecad /pfad/zu/FreeCADCmd  # FreeCAD selbst fragen
python3 install.py --target /pfad/zu/FreeCAD/Mod
```

`--freecad` ist der sichere Weg: Der Installer startet die Binary kurz und
fragt sie nach ihrem Verzeichnis. Nur so werden AppImages, Snaps und portable
Installationen zuverlässig getroffen.

### Auf einen anderen Rechner

```sh
python3 install.py --paket --mit-skills     # -> TextToGeometry.zip
```

Das ZIP enthält den fertigen Ordner `TextToGeometry/` samt der Skills, die Sie
hier gelernt haben. Drüben entpacken und `install.py` starten — oder den Ordner
direkt in das `Mod/`-Verzeichnis legen.

### Voraussetzungen

| | |
|---|---|
| FreeCAD | 1.0 oder neuer |
| Modell | **entweder** Ollama lokal **oder** ein API-Zugang |
| gmsh | nur für Festigkeitsanalyse (Vernetzung) |
| CalculiX (`ccx`) | nur für Festigkeitsanalyse (Rechnung) |

Ohne Ollama: Tab **Backend** → `API / OpenAI-kompatibel`, Adresse und Schlüssel
eintragen, **Modelle laden**, Modell wählen, **Verbindung testen**.

---

## 3. Der geführte Ablauf (Tab „Start")

Sechs Schritte, von oben nach unten. Jeder zeigt, ob er erledigt ist:
**▶** = hier weiter, **✓** = fertig, **○** = kommt noch.

| Schritt | Was passiert |
|---|---|
| 1 · Projekt anlegen | Ordner für Auftrag, Maße, Bauteile, Prüfungen |
| 2 · Auftrag beschreiben | Sie sagen, was gebaut wird; das Modell gliedert es |
| 3 · Maße festlegen | offene Zahlen ausfüllen — gelten danach projektweit |
| 4 · Bauteile erzeugen | vorhandene Generatoren kopieren, fehlende lernen |
| 5 · Ins Dokument bauen | jeden Generator ausführen und ansehen |
| 6 · Prüfen | Verbindungen, Kollisionen, Festigkeit |

**Automatik**: Unten im Start-Tab beschreiben Sie das Vorhaben in einem Satz und
drücken **Automatik starten**. Der Agent arbeitet den ganzen Ablauf ab und fragt
nur nach, wo es ohne Sie nicht geht. Alles bleibt danach einzeln editierbar —
die Automatik ist eine Abkürzung, keine Einbahnstraße.

---

## 4. Die Tabs

| Tab | Wofür |
|---|---|
| **Start** | Geführter Ablauf, Automatik |
| **Dialog** | Das Gespräch. Anweisungen ans offene Dokument und ans Projekt |
| **Projekt** | Verzeichnis, Auftrag, `agent.d`, Bauteilliste, Gewichtung der Kriterien |
| **Skills** | **Vorhandene** Generatoren: auswählen, Parameter einstellen, bauen |
| **Lernen** | **Neue** Skills lernen, vorhandene verfeinern, von Hand anlegen |
| **Werkzeuge** | Makros, Add-ons und Python-Module dieser Installation |
| **Serie** | Variantenserien aus Tabelle oder SVG-Zeichnung, mit Zielwerten |
| **Backend** | Modell, Zugang, Denktiefe, Zeitlimit |

„Skills" und „Lernen" sind bewusst getrennt: Das eine ist Ihr Baukasten, das
andere die Werkstatt, in der neue Teile entstehen.

---

## 5. Rezepte

### Etwas am offenen Modell ändern

Im **Dialog** (Haken *Agent* darf an bleiben):

```
Ergänze eine Bohrung mit 10 mm Durchmesser in der Mitte.
```

Fehlt eine Angabe, fragt das Modell nach — entweder als Text oder als
Eingabemaske. Ohne Haken *Agent* arbeitet der Dialog einzelbefehlsweise, ohne
Projektbezug.

### Ein Bauteil als wiederverwendbaren Skill lernen

Tab **Lernen** → *Skill lernen*:

1. **Bauteil** benennen (z. B. `einlasskanal`), eigene **Angaben** ergänzen.
2. **Recherche** optional einschalten (Wikipedia und offenes Web).
3. **1. Analysieren** → Parametersatz und Rückfragen erscheinen.
4. Antworten, Parameter anpassen, **2. Skill erzeugen**.

Der Code wird geprüft, bevor er gespeichert wird: Er muss laden, mit den
Standardwerten bauen, positives Volumen liefern und darf keinen Parameter
ignorieren. Scheitert das, bekommt das Modell den Fehler zurück — bis zu
*Versuche* Mal.

Danach steht der Skill im Tab **Skills** und ist deterministisch: gleiche
Parameter, gleiches Ergebnis, ohne Modell.

### Alle fehlenden Bauteile auf einmal

Tab **Projekt** → *Skills des Projekts* → **Alle fehlenden lernen**. Die Skills
werden nacheinander abgearbeitet; scheitert einer, geht es mit dem nächsten
weiter. Jeder dauert einige Minuten.

### Einen vorhandenen Skill verbessern

Tab **Lernen** → *Skill verfeinern*. Oben im Tab **Skills** den Skill wählen,
den Auftrag beschreiben („Übergang zum Ventilsitz kegelig"), starten. Die
bisherige Fassung wird als `.bak` gesichert; scheitert die Prüfung, bleibt sie
unverändert.

### Ein Zahnrad — ohne etwas zu lernen

Ist das Add-on `freecad.gears` installiert, steht es im Tab **Werkzeuge**.
Auswählen, **Ausführen**. Im Dialog geht auch:

```
befehl: FCGear_InvoluteGear
```

Der Agent kennt die Werkzeugliste und benutzt lieber ein vorhandenes Add-on,
als etwas nachzubauen.

### Eigene Makros und Python-Module einbinden

Makros aus FreeCADs Makro-Ordner erscheinen automatisch. Eigene Python-Pakete
binden Sie über **Python-Ordner hinzufügen …** ein; die öffentlichen Funktionen
werden dann als Werkzeuge angeboten und lassen sich mit Argumenten aufrufen
(`d=25.4; name=Platte`). Der Pfad wird gemerkt.

### Verbindungen prüfen

Ist das Paket `connection_detection` eingebunden (Tab **Werkzeuge**, oder unter
`~/ai-workspace/connection_detection`), prüft

```
verbindungen:
```

das offene Dokument und meldet Teile und Verbindungskandidaten.

### Festigkeitsanalyse

```
Führe eine Festigkeitsanalyse durch: unten fest, oben 500 N, Stahl.
```

Flächen werden über Bounding-Box-Seiten benannt (`zmin`, `xmax`, …). Vernetzt
wird mit gmsh, gerechnet mit CalculiX. Fehlt `ccx`, entstehen Aufbau und Netz
trotzdem, und das Protokoll sagt, dass nicht gerechnet wurde.

### Variantenserie

Tab **Serie**: Tabelle (CSV/XLSX/Spreadsheet/eingefügt) oder SVG-Zeichnung als
Quelle, Zielwerte (Masse, Volumen, Kantenmaße) mit Toleranz, Material für die
Dichte. Verfehlt eine Variante ihr Ziel, gehen die Messwerte als Rückmeldung
ins nächste Modell-Gespräch — bis zu *N* Iterationen je Variante.

---

## 6. Backend einstellen

| Feld | Bedeutung |
|---|---|
| **Backend** | `Ollama (nativ)` lokal · `API` für gehostete Modelle · `pi CLI` |
| **pi-Provider** | nur bei pi: `ollama`, `openai`, `anthropic`, `google`, … |
| **Base-URL** | z. B. `https://api.openai.com/v1` |
| **Modell** | **Modelle laden** holt die Liste vom Server |
| **API-Key** | `sk-…`; **Zugang merken** speichert ihn in FreeCADs Einstellungen |
| **Denktiefe** | wie gründlich das Modell vor kurzen Schritten nachdenkt |
| **Zeitlimit** | je Modellantwort (Standard 900 s) |

**Denktiefe**, gemessen an `qwen-gross` für einen Agentenschritt:

| aus | niedrig | hoch | automatisch |
|---:|---:|---:|---:|
| 1,2 s | 2,0 s | 3,9 s | 8,4 s |

„Niedrig" ist der Standard und reicht für die Schritte des Agenten. **Code für
Skills und Werkzeuge denkt immer gründlich**, unabhängig von dieser
Einstellung — Sie verschlechtern die Geometrie also nicht, wenn Sie den Regler
herunterdrehen.

*Denken zeigen* blendet die Überlegungen des Modells in den Verlauf ein; im
Protokoll unten stehen sie ohnehin immer.

---

## 7. Wenn etwas klemmt

| Meldung | Bedeutung |
|---|---|
| „Der Agent hat nur beschrieben statt gehandelt" | Das Modell hat erzählt statt eine Aktion auszugeben. Es wird aufgefordert; nach drei Versuchen bricht der Lauf mit einem konkreten Vorschlag ab. |
| „Nichts gebaut – fordere die Ausführung an" | Die Abschlussmeldung behauptet Geometrie, im Dokument ist aber nichts entstanden. |
| „Frage wiederholt – verweise auf die Antwort" | Dieselbe Rückfrage kam zweimal; Ihre Antwort wird zurückgespielt. |
| „Ollama nicht erreichbar" | Tab **Backend** → **Ollama starten**, oder auf API umstellen. |
| „pi-CLI nicht gefunden" | `T2G_PI_BIN` setzen oder ein anderes Backend wählen. |
| „Disallowed import" | Der erzeugte Code wollte ein nicht erlaubtes Modul benutzen. Erlaubt sind `Part`, `FreeCAD`, `math`. |
| „Solver CalculiX ist nicht installiert" | `sudo apt install calculix-ccx` — Aufbau und Netz stehen trotzdem. |
| Nichts passiert beim Klick | Steht die Gruppe außerhalb des Sichtbereichs? Die Befehle scrollen sie inzwischen heran. |

**Stop** im Dialog hält nach dem laufenden Schritt an. Ein laufender
Modellaufruf lässt sich nicht mitten in der Antwort abbrechen — FreeCAD bleibt
dabei aber bedienbar.

---

## 8. Wo was gespeichert wird

```
<Projektordner>/
    projekt.json                  Auftrag, Parameter, Kriterien, Graph, Verlauf
    agent.d/00-auftrag.md         was gebaut wird
            10-anforderungen.md   Kriterien, Gewichte, Konsistenz
            20-skills.md          welches Bauteil existiert, welches fehlt
            30-werkzeuge.md       Hilfsprogramme
            40-parameter.md       alle vereinbarten Maße
            50-abhaengigkeiten.md was nachzuziehen ist, mit Diagramm
    skills/<name>/<name>.py       kopierte und gelernte Generatoren
    tools/<name>.py               Rechenhilfen
    bewertung/paarvergleich.csv   Gewichtungsmatrix
```

- **`agent.d/` wird erzeugt.** Änderungen gehören in die Felder des Panels,
  nicht in die Markdown-Dateien — sie werden sonst überschrieben.
- **Der Verlauf wird laufend gespeichert.** Beim nächsten FreeCAD-Start öffnet
  sich das zuletzt benutzte Projekt von selbst; wird das Gespräch lang,
  verdichtet das Modell den älteren Teil zu Stichpunkten.
- **Gelernte Skills** liegen neben der *installierten* Workbench, nicht im
  Quellordner. `install.py --paket --mit-skills` nimmt sie mit.
- **Ein neues Projekt setzt alles zurück** — Verlauf, Masken, Lernfelder.

### Der Abhängigkeitsgraph

Jede Zeile `abhaengigkeit: ventil_d_ein;brennraum;nutzt` bedeutet: Ändert sich
`ventil_d_ein`, muss `brennraum` nachgezogen werden. Ändern Sie einen Wert,
markiert die Workbench die betroffenen Bauteile als „zu pruefen". Das Diagramm
in `50-abhaengigkeiten.md` zeigt das Ganze.

---

## 9. Grenzen — ehrlich gesagt

- **Das Modell erzählt gern.** Ein 27B-Modell behauptet manchmal, etwas gebaut
  zu haben. Dagegen laufen mehrere Prüfungen (siehe „Tatsächlich:"-Zeile), aber
  es kostet Runden. Ein größeres Modell über den API-Zugang hilft spürbar.
- **Die Sandbox schützt vor Versehen, nicht vor Absicht.** Erzeugter Code darf
  nur `Part`, `FreeCAD` und `math` importieren und kommt nicht an Dateien oder
  Netzwerk. Gegen ein *absichtlich* bösartiges Modell ist eine
  Python-Sandbox dieser Art nicht dicht — bei fremden Endpunkten FreeCAD besser
  isoliert betreiben.
- **Geprüft wird die Kette, nicht das Urteil.** Die Festigkeitsrechnung wurde
  gegen die geschlossene Lösung verifiziert (0,6 % Abweichung). Ob Lastannahme
  und Netzfeinheit für Ihr Bauteil taugen, bleibt Ingenieursarbeit.
- **Zeit.** Ein Skill zu lernen dauert mit einem lokalen 27B-Modell 2–5 Minuten.
  Das ist die Modellgeschwindigkeit, nicht die Workbench.
