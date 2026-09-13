# SPDX-License-Identifier: LGPL-2.1-or-later

# TextToGeometry — Dokumentation

Diese Dokumentation beschreibt, **was das Tool macht, wie es funktioniert und wie
man es verwendet**. Die technische Referenz (API, Dateien, Tests) steht in der
`README.md`.

---

## 1. Was ist TextToGeometry?

TextToGeometry ist eine FreeCAD-Arbeitshilfe (Workbench), die **natürliche Sprache
in 3D-Geometrie übersetzt**. Man beschreibt eine Form in Worten — z. B.

> *„ein Flansch, Außendurchmesser 80, Bohrung 40, Dicke 12, 4x M8 auf 60 BDK"*

— und die Workbench lässt eine **lokal laufende KI** (LLM) daraus FreeCAD-Code
(`Part`-API) generieren, führt den Code in einer **Sandbox** aus und legt die
entstandenen Körper direkt in das aktive FreeCAD-Dokument.

Kernprinzipien:

- **Lokal & offline-fähig** — kein Cloud-Dienst; das LLM läuft über Ollama,
  ein kompatiblen HTTP-Endpunkt oder die pi-CLI (alle wählbar im Dialog).
- **Bestätigbar** — die generierten Körper erscheinen als gewöhnliche FreeCAD-
  Objekte und können normal weiterbearbeitet werden (Parametrisierung, Messen,
  Export).
- **Zwei Generationspfade**:
  - *LLM-Pfad*: frei, flexibel, iterativ (mit Feedback-Schleife) — für neue
    Geometrien.
  - *Skill-Pfad*: deterministisch, parametrisiert, ohne LLM — für wiederverwendbare,
    wiederholbare Konstruktionsbausteine (z. B. die mitgelieferte
    Fachwerkbrücke).

---

## 2. Architecture (Kurzfassung)

```
Dialog (T2GCommand.py)
   │
   ├─ LLM-Pfad ──► T2GCore.run_backend()
   │                 │  (pi CLI  |  OpenAI-kompatibel  |  Ollama-nativ)
   │                 ▼
   │            LLM liefert ein ```python```-Block
   │                 │
   │                 ▼
   │            T2GCore.exec_code_in_sandbox()
   │                 (erlaubt nur: import Part, FreeCAD, math)
   │                 │
   │                 ▼
   │            result = [Part.Shape, ...]
   │                 │
   │                 ▼
   │             Messung (Volumen / Masse / Bounding-Box)
   │                 │
   │                 ├─ Ziel erfüllt      → [OK]
   │                 └─ Ziel nicht erfüllt → Feedback an LLM (max. N Iterationen)
   │
   └─ Skill-Pfad ──► T2GSkills.SkillEngine.build(name, params)
                      │  (reiner Python-Code aus Skills/<name>/<name>.py)
                      ▼
                    Part.Shape-Liste  +  Prüfregeln
                    (Kollision / Konnektivität)
```

Beide Pfade landen als **FreeCAD-Objekte im Dokument** — ab dort ist das Tool
unkritisch, man bleibt voll in FreeCAD.

### Sandbox-Regeln

- Erlaubte Imports: `Part`, `FreeCAD`, `math` (Whitelist).
- Keine Datei-, Netzwerk- oder Prozesszugriffe.
- Der Code muss eine Top-Level-Variable `result` setzen (Liste von
  `Part.Shape`; einzelnes Shape wird akzeptiert, mehrere werden ggf. als
  Compound gemessen).
- Verletzungen werden als klare Fehlermeldungen zurückgegeben.

---

## 3. Benutzeroberfläche (Dialog)

Das Panel ist in **sechs Tabs** unterteilt — vorher lagen alle Gruppen
untereinander auf zwei Seiten, was im angedockten Zustand (~420 px breit) die
Zeilen ineinanderschob:

| Tab | Inhalt |
|-----|--------|
| **Dialog** | Anweisungen am offenen Dokument, mit Rückfragen |
| **Projekt** | Projektverzeichnis, Auftrag, `agent.d`, Skills, Paarvergleich |
| **Eingabe** | Varianten-Quelle (Freitext, SVG, CSV, XLSX, Spreadsheet, Einfügen) |
| **Ziele** | Ziele/Toleranzen, Material, Loop, Ergebnis/CSV |
| **Skills** | Skill-Auswahl + Parameter, **Skill lernen**, Skill-Designer |
| **Backend** | LLM-Backend, Modell, Zeitlimit, Verbindungstest, Ollama-Start |

Jeder Tab ist scrollbar: schmale Docks scrollen, statt die Eingabefelder zu
stauchen.

Gemeinsame Elemente (unterhalb der Tabs):

- **Protokoll** — Fortschritt, Fehler, gemessene Werte (Trenner verschiebbar).
- **Statuszeile** — aktuell verwendetes Backend + Modell.
- **Buttons**: `Schließen` · `Stop` · `Generieren` (bzw. `Bauen` im Skill-Tab).

### 3.1 Tabs „Eingabe" und „Ziele"

#### Varianten-Quelle
Sechs Quellen, aus denen Varianten gelesen werden:

| Quelle | Beschreibung |
|--------|--------------|
| **Freitext** | Ein Prompt = eine Variante. |
| **Zeichnung (SVG)** | 2D-Frontansicht mit `<desc>`-Spezifikation (maschinell lesbar). |
| **CSV** | Zeile 1 = Kopf, weitere Zeilen = Varianten. |
| **XLSX** | Gleiches Schema, optional Sheetname. |
| **Spreadsheet** | Ein FreeCAD-Spreadsheet-Objekt im aktiven Dokument. |
| **Einfügen** | Tabelle direkt in ein Textfeld geklebt (`,`/Tab/`;`-getrennt). |

#### Ziele / Toleranzen (optional)
Zeilenbasierte Zielwerte pro Variante:

- **Masse** in g, **Volumen** in mm³, **Kante** in mm (x, y, z) — jeweils mit
  Operator `==`, `<=` oder `>=` und optionaler Toleranz.
- **Freitext-Ziel** wird das Modell direkt weitergegeben
  (z. B. *„kantenübergänge entgraten"*).

Bei Verfehlung meldet FreeCAD die **abgemessenen Werte** an das LLM zurück
(Feedback-Schleife), bis das Ziel passt oder die max. Iterationen erreicht sind.

#### Material
Preset-Dichten (Stahl, Aluminium, Kupfer, Kunststoff, Holz, Titan) oder eigener
Wert — wirkt ausschließlich auf **Masse-Ziele**.

#### Loop (Sweep + Feedback)
- **Max. Feedback-Iterationen pro Variante** (Default 3, Bereich 1–20).
- Checkbox: „Zielverfehlungen + Messwerte als Feedback an das Modell
  zurückgeben" (empfohlen).

#### Ergebnis
- **CSV-Export**: eine Zeile pro Variante mit Parametern, gemessenen Werten,
  Zielverfehlungen und Status.

### 3.2 Tabs „Skills" und „Backend"

#### Skill (deterministischer Generator)
- Kombobox mit allen verfügbaren Skills (geladen aus `Skills/*/`).
- **Parameter-Formular**: erscheint beim Skill-Wechsel, Defaults vorausgefüllt,
  min/max wird durch den Spinbox-Wertebereich durchgesetzt.
- **Bauen**: führt `build(params)` aus, legt alle Solids im Dokument ab und
  wertet die Prüfregeln aus:
  - **Kollision** (mögliche Überlappung)
  - **Konnektivität** (getrennte Körper)
- **↻** lädt das Skill-Verzeichnis neu (z. B. nach Anlage eines neuen Skills).

#### Skill-Designer
Neuen Skill ohne Editor:

1. **Name** und **Beschreibung** eingeben.
2. **Parameter** als Zeilen: `name;label;einheit;default;min;max`.
3. **build(params)-Code** (Python, erlaubte Imports wie in der Sandbox).
4. **Speichern unter …** → Skill ist sofort in der Kombobox verfügbar.

Der Designer führt einen **Syntaktik- und Sandbox-Test** durch, bevor gespeichert
wird (Name, Parameter, Abhängigkeiten, Kollisionen mit bestehenden Namen).

#### LLM / Backend
| Feld | Beschreibung |
|------|--------------|
| **Backend** | `ollama` (nativ, Standard) · `openai` (API, OpenAI-kompatibel) · `pi` (CLI) |
| **pi-Provider** | nur bei `pi`: `ollama` (lokal), `openai`, `anthropic`, `google`, `openrouter`, … |
| **Base-URL** | wird beim Backend-Wechsel automatisch neu vorbelegt |
| **Modell** | Auswahlliste, per **Modelle laden** direkt vom Server geholt |
| **API-Key** | nur bei externen `openai`-Endpunkten relevant |
| **Verbindung testen** | prüft Erreichbarkeit und sendet einen Minimal-Prompt — für **jedes** Backend |
| **Ollama starten** | startet den lokalen Server (systemd-Unit oder `ollama serve`) |
| **Status** | z. B. „Ollama erreichbar: 20 Modell(e) · Modell vorhanden" |

**pi mit einer API**: pi kennt seine Provider selbst und braucht keine
Base-URL – nur `--provider`, `--model` und den Schlüssel. Wählen Sie „pi", dann
den Provider, laden Sie die Modelle (`pi --list-models`) und tragen Sie bei
einem gehosteten Provider den API-Schlüssel ein. Für `ollama` als pi-Provider
bleibt alles lokal.

**Denktiefe**: Wie gründlich das Modell vor der Antwort nachdenkt – für die
kurzen Schritte des Agenten. Gemessen an `qwen-gross` für einen Agentenschritt:

| Einstellung | Dauer | erzeugte Token |
|-------------|------:|---------------:|
| aus | 1,2 s | 25 |
| niedrig (Standard) | 2,0 s | 72 |
| hoch | 3,9 s | 190 |
| automatisch | 8,4 s | 140 |

„Niedrig" reicht für einen Aktionsblock völlig. **Unabhängig davon denkt der
Code für Skills, Werkzeuge und Sweep-Geometrie immer gründlich** („hoch"), und
das Verdichten des Verlaufs gar nicht – dort zählt Genauigkeit bzw. Tempo, nicht
die Einstellung. Weitergereicht wird sie als `think` (Ollama), `--thinking`
(pi) und `reasoning_effort` (API-Anbieter, nur wenn ausdrücklich gewählt).

**Denken zeigen**: Der Schalter im Dialog blendet die Überlegungen des Modells
in den Verlauf ein; im Protokoll unten stehen sie ohnehin immer. Sie stammen aus
`message.thinking` (Ollama), `reasoning_content` (viele API-Anbieter) oder den
`thinking`-Blöcken des pi-Streams.

**Nichts blockiert die Oberfläche**: Modell-Abfragen, Verbindungstests,
Ollama-Start und Recherche laufen in Hintergrund-Threads. FreeCAD bleibt auch
während eines mehrminütigen pi-Aufrufs bedienbar.

Beim Öffnen wählt das Panel das Backend selbst (`T2GCore.detect_backend()`):
antwortet Ollama auf `localhost:11434`, wird **Ollama (nativ)** vorbelegt, sonst die
pi-CLI, falls deren Binary gefunden wird (PATH, `T2G_PI_BIN`, `~/.npm-global/bin`,
`~/.local/bin`, `/usr/local/bin`). Damit funktioniert die Workbench auch, wenn
FreeCAD nicht über `start.sh` gestartet wurde.

---

## 3.3 Tab „Dialog" – Arbeiten am offenen Dokument

Hier beschreibt man, was mit dem **bereits vorhandenen** Modell geschehen soll.
Das Modell bekommt vor jeder Anweisung den Dokumentinhalt (Objektnamen, Labels,
Volumen, Bounding-Boxen) und die aktuelle Auswahl.

| Anweisung | Ergebnis |
|-----------|----------|
| „Ergänze eine Bohrung mit 10 mm Durchmesser in der Mitte." | Geometrie des gewählten Körpers wird ersetzt |
| „Ergänze eine Bohrung." | **Rückfrage** nach Durchmesser und Lage |
| „Lege ein neues Bauteil mit dem Namen Grundplatte an, 100×60×8." | neues `Part::Feature` |
| „Baue Klotz und Grundplatte in eine Baugruppe ein." | `Assembly::AssemblyObject` mit `App::Link`s |
| „Führe eine Festigkeitsanalyse durch: unten fest, oben 500 N." | FEM-Analyse, Solver, Werkstoff, Randbedingungen, gmsh-Netz |

**Rückfragen**: Fehlt eine Angabe, die die Geometrie wesentlich bestimmt,
antwortet das Modell mit einer Frage statt mit Code. Die Antwort wird im selben
Feld eingegeben; der Verlauf bleibt erhalten („mach sie 12 mm" versteht das
Modell also). „Verlauf zurücksetzen" beginnt neu.

**Gedächtnis und Speichern**

- Der Gesprächsverlauf steht im Prompt – der Agent fragt nicht erneut, was Sie
  schon beantwortet haben.
- Wird er zu lang, **verdichtet** ihn das Modell selbst zu Stichpunkten
  („Baugruppe: 6 Teile …", „bohrung = 86 mm", „Auslasskanal kürzer als
  Einlasskanal"). Die jüngsten Zeilen bleiben wörtlich stehen.
- Jede Chatzeile, jeder Parameter und jede Abhängigkeit wird sofort in
  `projekt.json` geschrieben. Beim nächsten FreeCAD-Start öffnet sich das
  zuletzt benutzte Projekt von selbst, der Verlauf steht wieder im Fenster und
  die verdichtete Fassung darüber. Es geht nichts verloren.

**Reihenfolge**: Bei einer Baugruppe legt der Agent zuerst die Struktur an
(`Assembly::AssemblyObject` mit einem Platzhalter je Bauteil), dann die globalen
Parameter, dann die Skills – und baut jeden fertigen Skill sofort ins Dokument,
damit Sie ihn beurteilen können.

**Sicherheit**: Der erzeugte Code fasst das Dokument nicht selbst an. Er ruft
eine kleine API auf (`shape`, `info`, `names`, `selected`, `add`, `replace`,
`part`, `assembly`, `fem`, `note`), die die Wünsche nur **protokolliert**; das
Anwenden macht die Workbench im GUI-Thread. Die Import-Whitelist der Sandbox
gilt unverändert.

**FEM**: Flächen werden über Bounding-Box-Seiten benannt (`zmin`, `xmax`, …),
weil das Modell die FreeCAD-Flächennummern nicht kennen kann. Vernetzt wird mit
**gmsh**, gerechnet mit **CalculiX (ccx)**. Die Workbench sucht `ccx` in `PATH`,
`~/.local/bin`, `~/.local/ccx/usr/bin` und `/usr/bin` und trägt den gefundenen
Pfad in die FEM-Einstellungen von FreeCAD ein, damit auch die FEM-Workbench
dieselbe Binary benutzt. Fehlt `ccx`, werden Aufbau und Netz trotzdem erzeugt
und im Protokoll steht, dass nicht gerechnet wurde.

Installation, systemweit oder ohne root:

```sh
sudo apt install calculix-ccx
# oder ohne root:
apt-get download calculix-ccx libspooles2.2t64
dpkg -x calculix-ccx_*.deb ~/.local/ccx && dpkg -x libspooles2.2t64_*.deb ~/.local/ccx
# Wrapper ~/.local/bin/ccx setzt LD_LIBRARY_PATH auf ~/.local/ccx/usr/lib/x86_64-linux-gnu
```

**Belastbarkeit der Ergebnisse**: An einer Stahlsäule 20×20×100 mm (unten fest,
500 N oben) liefert CalculiX 1,258 MPa und 0,000589 mm gegen die Handrechnung
σ = F/A = 1,250 MPa und δ = F·L/(A·E) = 0,000595 mm — 0,6 % bzw. 1,0 %
Abweichung; die doppelte Last verdoppelt beide Werte. Das prüft die Kette
Randbedingungen → Netz → Solver, nicht die Güte eines beliebigen Modells: Netz
und Lastannahmen bleiben Sache des Anwenders.

---

## 3.4 Tab „Projekt" – ein Vorhaben statt eines Einzelteils

Ein Projekt hält alles zusammen, was zu einem Konstruktionsauftrag gehört:

```
<projekt>/
    projekt.json                  Zustand (gehört T2GProject)
    agent.d/00-auftrag.md         was gebaut wird, aus dem Dialog
            10-anforderungen.md   Kriterien, Gewichte, Konsistenz
            20-skills.md          welcher Skill existiert, welcher fehlt
            30-werkzeuge.md       Hilfsprogramme
    skills/<name>/<name>.py       kopierte oder gelernte Generatoren
    tools/<name>.py               Hilfscode
    bewertung/paarvergleich.csv   die Matrix, in jeder Tabellenkalkulation lesbar
```

**Ablauf**

1. **Neu anlegen** – Verzeichnis, Titel, Struktur.
2. Vorhaben beschreiben, **Projekt planen**. Das Modell liefert in einem Zug:
   Auftrag, offene Rückfragen, benötigte **Skills**, sinnvolle **Werkzeuge** und
   die **Kriterien**, die miteinander in Konflikt geraten. Alle Felder bleiben
   editierbar – das ist ein Vorschlag, kein Urteil.
3. **Übernehmen + agent.d schreiben** – Zustand gespeichert, `agent.d/` erzeugt.
4. **Skills**: Jeder Bedarf wird gegen die installierten Skills geprüft.
   *Vorhandene kopieren* holt die wirklich passenden ins Projekt,
   *Fehlenden lernen →* übergibt den ersten offenen an den Lern-Dialog, mit dem
   Projektkontext als Vorgabe.

   Die Namensprüfung ist bewusst streng bei der ersten Silbe: `auslasskanal`
   gilt **nicht** als `einlasskanal` (eine reine Zeichenähnlichkeit läge bei
   0,75 und hätte den falschen Generator kopiert). Ähnliche Namen werden
   genannt, aber nicht automatisch übernommen.
5. **Paarvergleich**: Für jedes Kriterienpaar – wie viel wichtiger ist A als B?
   Skala nach Saaty (9 = absolut, 7, 5, 3, 1 = gleich, dann 1/3 … 1/9).
   *Vorschlag vom Modell* füllt die Zeilen samt Begründung im Protokoll vor,
   Sie korrigieren, *Auswerten* rechnet.

**Wie die Gewichte entstehen**: Zeilenweises geometrisches Mittel der Matrix,
normiert. Das **Konsistenzverhältnis** CR = CI/RI zeigt, ob sich die Urteile
widersprechen (CR ≤ 0,10 ist die übliche Grenze). Darüber benennt das Panel die
Urteile, die am schlechtesten zu den Gewichten passen.

Bei genau **drei** Kriterien verteilt sich ein Widerspruch rechnerisch
gleichmäßig auf alle drei Paare – dort lässt sich kein Schuldiger benennen, ab
vier Kriterien schon. Das Panel weist darauf hin.

Auftrag und gewichtete Kriterien gehen als Kontext in die Lern- und
Dialogschritte ein (`Project.as_prompt_block()`) – das unterscheidet ein Projekt
von einem bloßen Ordner.

---

## 3.5 Skill lernen (komplexe Bauteile)

Für Bauteile, die ein einzelner Prompt nicht trifft (z. B. „Einlasskanal"):

1. **Bauteil** benennen, eigene **Angaben** ergänzen.
2. **Recherche** (standardmäßig **aus**): Ist sie an, geht der Bauteilname an die
   Wikipedia-API; jede benutzte Quelle wird im Panel angezeigt. Zusätzlich kann
   eine URL angegeben werden. Ist sie aus, verlässt nichts den Rechner.
3. **1. Analysieren** → das Modell schlägt einen **Parametersatz** vor
   (`name;label;einheit;default;min;max`, frei editierbar) und stellt **offene
   Fragen**.
4. Fragen beantworten, Parametertabelle anpassen.
5. **2. Skill erzeugen** → das Modell schreibt `build(params)`. Geprüft wird:
   Syntax, Ladbarkeit, Bau mit den Standardwerten, positives Volumen, dass kein
   Parameter ignoriert wird, dazu die Prüfregeln. Scheitert etwas, bekommt das
   Modell den Fehlertext zurück (bis *Versuche*).
6. Der Skill landet unter `Skills/<name>/<name>.py` und ist sofort in der
   Skill-Liste — ab dann deterministisch und ohne LLM.

Maß- und Winkelparameter werden als **Gleitkomma** angelegt, nur echte
Stückzahlen (Einheit `-`) als Ganzzahl — sonst ließe sich ein vom Modell mit
`45` vorgeschlagener Durchmesser später nicht auf 67,5 mm stellen.

Gelernte Skills liegen neben der **installierten** Workbench
(`~/.local/share/FreeCAD/v1-1/Mod/TextToGeometry/Skills/`), nicht im
Entwicklungsordner.

---

## 3.6 Weitergeben und auf anderen Rechnern installieren

**Auf diesem Rechner in eine andere FreeCAD-Installation**

```sh
python3 install.py                                  # sucht alle Mod-Ordner
python3 install.py --freecad /pfad/zu/FreeCADCmd    # FreeCAD selbst fragen
python3 install.py --target /pfad/zu/FreeCAD/Mod    # Pfad selbst angeben
python3 install.py --list                           # nur anzeigen
python3 install.py --uninstall
```

`--freecad` ist der zuverlässigste Weg: Der Installer startet die Binary kurz
und fragt `FreeCAD.getUserAppDataDir()`. Nur so werden AppImages, Snaps,
portable Installationen und ein gesetztes `FREECAD_USER_HOME` sicher getroffen —
die Plattformpfade sind nur eine Vermutung.

In FreeCADs eigener Python-Konsole genügt:

```python
exec(open("/pfad/zu/TextToGeometry/install.py").read()); main([])
```

**Auf einen anderen Rechner**

```sh
python3 install.py --paket --mit-skills     # -> TextToGeometry.zip
```

Das ZIP enthält den fertigen Ordner `TextToGeometry/`. Drüben:

```sh
unzip TextToGeometry.zip -d /tmp/t2g
python3 /tmp/t2g/TextToGeometry/install.py
```

Oder den entpackten Ordner einfach in das `Mod/`-Verzeichnis der dortigen
FreeCAD-Installation legen. Danach FreeCAD neu starten.

**Was mitgeht und was nicht**

- Mit `--mit-skills` werden die **gelernten** Skills eingesammelt. Sie liegen
  neben der *installierten* Workbench, nicht im Quellordner — ohne diesen
  Schalter bliebe der mühsam gelernte Einlasskanal zurück.
- Sicherungskopien (`*.py.bak`) bleiben auf dem Rechner.
- **Projekte** werden nicht mitgepackt: Die liegen dort, wo Sie sie angelegt
  haben (Standard `~/T2G-Projekte`). Kopieren Sie den Projektordner separat; er
  ist in sich vollständig (`projekt.json`, `agent.d/`, `skills/`, `tools/`,
  `bewertung/`).
- **API-Zugang**: Adresse, Modell und (wenn „Zugang merken" gesetzt war)
  Schlüssel stehen in FreeCADs Einstellungen und gehen **nicht** mit ins Paket.
  Auf dem Zielrechner einmal neu eintragen.

**Ohne Ollama auf dem Zielrechner**: Tab „Backend" → `API / OpenAI-kompatibel`,
Base-URL und Schlüssel eintragen, „Modelle laden", Modell wählen. Die
Backend-Erkennung nimmt beim Start lokales Ollama, sonst den gespeicherten
API-Zugang.

---

## 4. Skills im Detail

Skills sind **deterministische, parametrisierte Generatoren**. Im Unterschied
zum LLM-Pfad gibt es:

- keine Latenzzeit (reiner Python-Code, keine Modell-Abruf),
- vollständige Reproduzierbarkeit (gleiche Parameter → gleiche Geometrie),
- eingebaute Prüfregeln (Kollision, Konnektivität) als **Hinweise** im Log.

### Datei-Struktur

```
Skills/
└── bruecke/
    └── bruecke.py        ← T2G_SKILL-Dict + def build(params)
```

### Beispiel: `bruecke.py` (verkürzt)

```python
T2G_SKILL = {
    "name": "bruecke",
    "description": "Parametrische Fachwerkträger-Brücke mit Piastern, Fahrbahn "
                   "und Fachwerk (vertikale Stiele + Diagonalen).",
    "parameters": [
        ("span",     "Gesamtlänge",            "mm",  2000,  100,  50000),
        ("pier_h",   "Piast-Höhe",             "mm",  1100,  100,  10000),
        ("truss_h",  "Träger-Höhe",            "mm",   300,   50,   5000),
        ("n_vert",   "Anzahl Stiele",          "-",     5,    1,     50),
        ("deck_t",   "Fahrbahn-Dicke",         "mm",   100,   10,   500),
        ("deck_w",   "Fahrbahn-Breite",        "mm",   400,   50,   2000),
        ("pier_w",   "Pier-Breite",            "mm",   150,   20,   1000),
        ("pier_d",   "Pier-Tiefe",             "mm",   150,   20,   1000),
        ("member_w", "Stab-Breite (Fachwerk)", "mm",    40,    5,    200),
        ("member_d", "Stab-Tiefe (Fachwerk)",  "mm",    40,    5,    200),
    ],
    "dependencies": ["Part", "FreeCAD", "math"],
    "rules": ["collision", "connectivity"],
}

def build(params):
    # ... erzeugt 13 Solids: 2 Piers, Fahrbahn, Stiele, Obergurte, Diagonalen
    return shapes
```

### Aufruf

**Im Dialog:** Skill *bruecke* wählen → ggf. Parameter anpassen → **Bauen**.
Die 13 Körper erscheinen im Dokument, Kollisionen/Disconnected-Body-Warnungen
stehen im Log.

**Programmierisch:**

```python
import T2GSkills
eng    = T2GSkills.get_engine("Skills")
shapes, vals, issues = eng.build("bruecke", {"span": 2500})
# shapes: list[Part.Shape]
# vals:   dict mit allen (Default-)Werten
# issues: list[str] — Hinweise aus Kollision/Konnektivität
```

### Neue Skills schreiben

Minimales Gerüst (eigener Ordner `Skills/meingeraet/meingeraet.py`):

```python
T2G_SKILL = {
    "name": "meingeraet",
    "description": "Kurze Beschreibung.",
    "parameters": [
        ("l", "Länge", "mm", 100, 1, 10000),
        ("w", "Breite", "mm", 50, 1, 5000),
    ],
    "dependencies": ["Part", "FreeCAD"],
    "rules": ["collision"],
}

def build(params):
    l, w = params["l"], params["w"]
    body = Part.makeBox(l, w, 10)
    return [body]
```

Danach `./start.sh sync` (oder FreeCAD neu laden) und im Dialog wählen.
Der Designer im Dialog kann das Ganze ebenfalls übernehmen (inkl. Syntaxprüfung).

---

## 5. LLM-Backend im Detail

Die Workbench spricht **drei Protokolle**:

| Backend | Transport | Beispiel-URL |
|---------|-----------|--------------|
| `pi` | CLI (`-p`, non-interactive) | `~/.npm-global/bin/pi` |
| `openai` | HTTP REST, `POST /chat/completions` | `http://host:11434/v1` (Ollama OpenAI-Modus) |
| `ollama` | HTTP REST, `POST /api/chat` | `http://localhost:11434` |

`T2GCore._t2g_api_call()` normalisiert die URL (entfernt ein evtl. vorhandenes
`/v1`-Suffix bei `ollama`), baut die korrekte Anfrage und parst den Antwort-
Token. `T2GCore.run_api()` / `generate_via_api()` liefern `(code, shapes)`.

**Konfiguration im Dialog** (Tab *Skill & Backend → LLM / Backend*) gilt für
die nächste Sitzung; die Defaults pro Backend sind:

```
openai:  http://localhost:11434/v1
ollama:  http://localhost:11434
pi:      (Binär-Pfad, via T2G_PI_BIN oder PATH)
```

---

## 6. Typische Workflows

### 6.1 Einzelne Freitext-Variante
1. Freitext schreiben, ggf. Material + Ziel wählen.
2. **Generieren** → Körper erscheint im Dokument.

### 6.2 Varianten-Sweep (z. B. 5 Boxen mit steigenden Maßen)
1. CSV/XLSX/Einfügen mit Kopfzeile + Datendaten.
2. Ziel setzen (z. B. *Masse <= 5 g*, *Kante x >= 40 mm*).
3. Iteration 3, Feedback an.
4. **Generieren** → alle Varianten nacheinander, mit Messung & ggf. Korrektur.
5. CSV-Export für die Nachbereitung.

### 6.3 2D-Zeichnung → 3D (SVG)
1. SVG-Vorderansicht mit `<desc>`-Spezifikation (Einheiten, Coordinates-Mapping,
   Elementliste mit Maßen) vorbereiten — Vorlage: `Resources/drawings/bridge.svg`.
2. Tab *LLM-Generierung → Zeichnung (SVG)*, Pfad setzen, **Zeichnung laden**
   (die `<desc>`-Spezifikation wird angezeigt).
3. Ggf. Material/Ziele, **Generieren**.

Der LLM erzeugt daraus eine strukturierte Build-Funktion (Boxen für Quer-/Längs-
bauteile, `bar()`-Helper für Diagonalen), die die Sandbox ausführt.

### 6.4 Wiederverwendbare Bauteile als Skill
1. Parameterliste definieren (Name, Einheit, Range, Default).
2. `build(params)` schreiben — rein geometrisch, ohne LLM.
3. Im Dialog speichern (Designer) oder direkt Datei anlegen.
4. `./start.sh sync` → Skill steht im Kombobox zur Verfügung.

---

## 7. Testen & Qualitätssicherung

| Test | Zweck | Laufzeit |
|------|-------|----------|
| `test_core.py` | Sandbox, Code-Extraktion, Drawing-Spec-Parser (13 Tests) | < 2 s |
| `test_ext.py`  | Ziele, Messung, Tabellen-Reader, Sweep, CSV (14 Tests) | < 2 s |
| `test_skills.py` | Params, Engine, `create_skill`, Rules (14 Tests) | < 2 s |
| `test_chat.py` | Dialogmodus: Kontext, Protokoll, Rückfragen, Ops (26 Tests) | < 2 s |
| `test_learn.py` | Recherche + Skill-Lernen, Validierung (26 Tests) | < 2 s |
| `test_project.py` | Projektstruktur, AHP-Rechnung, Skill-Zuordnung (39 Tests) | < 2 s |
| `e2e_freecad.py` | E2E: 1 Prompt → Part (echtes Modell erforderlich) | ~ 30 s |
| `e2e_sweep_freecad.py` | E2E: Varianten-Sweep (echtes Modell) | ~ 90 s |
| `e2e_bridge_drawing.py` | E2E: 2D-Brücke → 3D (echtes Modell) | ~ 60 s |

```sh
./start.sh test            # alle headless tests (FreeCADCmd)
python3 test_core.py       # direkt, ohne FreeCAD
```

---

## 8. Sicherheit

- **Keine Secrets im Code**: API-Keys werden nur im Dialog gehalten (Password-
  Field), nie auf Disk geschrieben.
- **Sandbox**: LLM-generierter Code läuft mit einer Import-Whitelist
  (`Part`, `FreeCAD`, `math`, `Units`, `Materials`) und ohne `open`, `eval`,
  `exec`, `compile`, `globals`, `vars`, `getattr`. Dokumentänderungen laufen
  nie im generierten Code selbst, sondern werden protokolliert und von der
  Workbench im GUI-Thread angewendet.

  **Grenze, offen gesagt**: Das schützt zuverlässig vor *Versehen* – ein Modell,
  das versehentlich `os` importiert oder eine Datei schreiben will, scheitert.
  Es ist **keine** Absicherung gegen ein absichtlich bösartiges Modell: In
  CPython lässt sich über Attributpfade an Funktionsobjekten grundsätzlich
  ausbrechen. Wer ein nicht vertrauenswürdiges Modell einsetzt, sollte FreeCAD
  in einem Container oder unter einem eigenen Benutzer laufen lassen. Bei einem
  lokalen Ollama-Modell, das Sie selbst gewählt haben, ist das Risiko gering;
  bei einem fremden API-Endpunkt gilt dieselbe Überlegung wie bei jedem
  Fremdcode.
- **Deterministische Pfade**: Skills & Prüfregeln laufen ohne LLM — bei
  Sensitivität gegenüber Prompts zwingend diese Option wählen.
- **Local-only (Default)**: Ollama auf `localhost` — für OpenAI-kompatible
  externe Endpunkte den Netzwerkpfad selbst prüfen.
- **Webrecherche ist opt-in**: ohne Haken im Lern-Dialog geht kein Byte ins
  Netz. Mit Haken wird ausschließlich der Bauteilname an die Wikipedia-API
  geschickt (plus eine optionale, selbst eingetragene URL); nur `http`/`https`
  sind erlaubt, die Antwort wird auf Größe begrenzt und als reiner Text
  weiterverarbeitet. Alle benutzten Quellen stehen sichtbar im Panel.
- **Gelernte Skills sind normaler Python-Code**, den ein Modell geschrieben hat:
  Vor dem Speichern wird er in der Skill-Sandbox (erlaubte Importe: `math`,
  `Part`, `FreeCAD`) ausgeführt und gebaut. Ein Blick in die erzeugte Datei vor
  dem produktiven Einsatz bleibt trotzdem ratsam.

---

## 9. Grenzen des Tools

- Das LLM **erfindet nicht**: Es kann `Part`-Befehle generieren, die keine
  realen, herstellbaren Bauteile ergeben — man prüft die Geometrie selbst.
- Die Sandbox erlaubt **keine parametrischen Features** (Sketcher, Part-Design)
  — nur `Part`-API-Level-Aufrufe.
- Die Zielprüfung misst **nur Volumen / Masse / Bounding-Box** — feinere
  Geometrieprüfungen (z. B. Abstände, Konturen) müssen manuell erfolgen.
- **Nicht für** CAD-Präzision: Das Tool ist ein **Generations-Entwurfswerkzeug**,
  kein Ersatz für eine parametrische CAD-Pipeline.

---

## 10. Glossar

| Begriff | Bedeutung |
|---------|-----------|
| **Varianten** | Verschiedene Instanzen derselben Geometrie (aus Tabelle/Prompt). |
| **Ziel** | Eine messbare Eigenschaft (Masse/Volumen/Kante), die erfüllt sein muss. |
| **Feedback-Schleife** | Abgemessene Werte + Verfehlungs-Gründe → LLM → neue Version. |
| **Skill** | Deterministisches, parametrisiertes Build-Modul unter `Skills/`. |
| **Sandbox** | Isolierte Ausführungsumgebung mit Import-Whitelist. |
| **pi-CLI** | Coding-Agent-CLI (earendil-works) als LLM-Brücke. |
