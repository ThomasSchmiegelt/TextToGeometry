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

Der Dialog ist in **zwei Tabs** unterteilt:

| Tab | Inhalt |
|-----|--------|
| **LLM-Generierung** | Varianten-Quelle, Ziele, Material, Loop, Ergebnis |
| **Skill & Backend** | Skill-Auswahl + Parameter, Skill-Anlage, LLM-Backend |

Gemeinsame Elemente (unterhalb der Tabs):

- **Log-Fenster** — Fortschritt, Fehler, gemessene Werte.
- **Statuszeile** — aktuell verwendetes Backend + Modell.
- **Buttons**: `Schließen` · `Stop` · `Generieren` (bzw. `Bauen` im Skill-Tab).

### 3.1 Tab „LLM-Generierung"

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

### 3.2 Tab „Skill & Backend"

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
| **Backend** | `pi` (CLI) · `openai` (OpenAI-kompatibel) · `ollama` (nativ) |
| **Base-URL** | wird beim Backend-Wechsel automatisch neu vorbelegt |
| **Modell** | z. B. `qwen-gross:latest` |
| **API-Key** | Nur bei `openai`/`ollama` mit Authentifizierung relevant |
| **Verbindung testen** | Sendet einen Minimal-Prompt und meldet das Ergebnis im Log |

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
- **Sandbox**: LLM-generierter Code hat keine I/O, keine Netzwerkzugriffe,
  keine Subprocesses.
- **Deterministische Pfade**: Skills & Prüfregeln laufen ohne LLM — bei
  Sensitivität gegenüber Prompts zwingend diese Option wählen.
- **Local-only (Default)**: Ollama auf `localhost` — für OpenAI-kompatible
  externe Endpunkte den Netzwerkpfad selbst prüfen.

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
