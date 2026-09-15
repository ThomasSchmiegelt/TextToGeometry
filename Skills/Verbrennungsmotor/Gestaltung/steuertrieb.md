<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary -->
# Steuertrieb — geometrische Gestaltung

Skript: `kt_steuertrieb.py`

## Was die Form bestimmt

Der Steuertrieb hat genau **eine** Zusage: die Übersetzung **2:1**. Die
Nockenwelle muss sich halb so schnell drehen wie die Kurbelwelle, sonst
öffnen die Ventile im falschen Takt. Alles andere ist Ausführung — und
deshalb misst der Selbsttest nicht die Optik, sondern das
Zähnezahlverhältnis.

Zwei Bauarten:

- **Zahnradtrieb** — steif und dauerhaft, aber laut und teuer, und der
  Achsabstand ist durch `a = m · (z₁ + z₂) / 2` festgelegt. Ein Zwischenrad
  kehrt die Drehrichtung wieder um.
- **Kettentrieb** — der Regelfall im Pkw. Die Kette läuft auf den **äußeren
  Tangenten** zwischen benachbarten Rädern und umschlingt jedes Rad
  dazwischen.

Die Geometrie des Kettenrads ist genormt (Zahnform nach DIN 8196, Ketten
nach DIN 8187 / DIN 8188 / ISO 606). Das bestimmende Maß ist der
**Teilkreis**:

```
d = p / sin(π / z)
```

mit `p` Teilung und `z` Zähnezahl. Kontrolle an einem Katalogwert: ein
08B-1-Rad (p = 12,7 mm) mit 21 Zähnen hat `12,7 / sin(180°/21) = 85,2 mm` —
genau der Katalogwert. Die Rollen liegen auf dem Teilkreis; das Rad selbst
wird auf dem **Fußkreis** `d − d_Rolle` gezeichnet, sonst verschluckt es die
Rollen (gemessen: 100 % Durchdringung).

Der Rollendurchmesser gehört zur Teilung: 06B (p = 9,525) hat 6,35 mm, 08B
(p = 12,7) hat 8,51 mm — also rund **⅔ der Teilung**.

## Die eigentliche Auslegungsfrage bei DOHC

Bei einem DOHC-Kopf laufen **zwei** Nockenwellen, und beide hängen an
derselben Kette. Das Nockenrad hat die doppelte Zähnezahl des Kurbelrades und
ist damit rund doppelt so groß. Daraus folgt eine harte Grenze:

> Der Abstand der beiden Nockenwellen muss größer sein als der Fußkreis des
> Nockenrades — und der Fußkreis des Kurbelrades muss größer sein als seine
> eigene Bohrung.

Beide Bedingungen ziehen gegeneinander, denn `d₂ ≈ 2 · d₁`. Praktisch heißt
das: der Wellenabstand muss mindestens etwa das Doppelte des Kurbelzapfens
plus Wand betragen. Nachgemessen an einem R4 mit 86 mm Bohrung:

| Ventilwinkel | Abstand der Nockenwellen | 40-Zahn-Rad 3/8" (121 mm) |
|---|---|---|
| 0° | 37,2 mm | passt nicht — auch mit keiner Teilung |
| 6° | 77,9 mm | passt nicht |
| 8° | 100 mm | passt mit feinerer Teilung |
| 12° | 118,2 mm | passt |
| 20° | 170,5 mm | passt |

Der Ventilwinkel ist also nicht nur das Dach des Brennraums, sondern auch
das, was die beiden Nockenwellen auseinanderrückt. Ein DOHC-Kopf mit
parallelen Ventilen lässt sich nicht mit einer Kette über beide Wellen
bauen — der Generator sagt das mit Begründung, statt ineinandersteckende
Räder zu liefern.

## Richtwerte

| Maß | Richtwert | Generator |
|---|---|---|
| Übersetzung | genau 2:1 | 2:1, geprüft |
| Zähne Kurbelrad | 17 – 24 | 20 |
| Teilung (Normreihe) | 12,7 (08B) · 9,525 (06B) · 8,0 (05B) · 6,35 (25) | passend gewählt |
| Rollendurchmesser | Normtabelle: 8,51 / 6,35 / 5,0 / 4,0 | aus `ROLLEN` |
| Teilkreis | `p / sin(π/z)` | dieselbe Formel |
| Radkörper | auf Fußkreis `d − d_Rolle` | ✔ |
| Gliederzahl | gerade (kein Kröpfglied) | aufgerundet auf gerade |
| Modul Zahnradtrieb | 2 – 4 mm | 3,0 mm |

## Was der Generator heute baut

`baue(art, zaehne_kurbel, modul, teilung, breite, achsabstand, kurbel_d,
nocken_d, rollen_d, nocken_lagen, doc)`:

- **Zahnrad**: echte Evolventenverzahnung über das Add-on FCGear, ein Rad je
  Welle.
- **Kette**: ein Kettenrad je Welle auf dem Fußkreis, mit Bohrung; dazu die
  Kette als Folge von Rollen entlang ihrer Bahn.
- Die Bahn läuft über **beliebig viele** Räder: `_tangente()` liefert die
  äußere Tangente zweier Kreise aus `(C₂ − C₁) · n = −(r₂ − r₁)`,
  `_umlauf()` bringt die Räder in Umlaufreihenfolge, `_bahnlaenge()` misst
  die wirkliche Bahn — die Zweiradformel gilt ab dem dritten Rad nicht mehr.
- `auslegen_kette()` wählt die größte Normteilung, die zwischen die Wellen
  passt und deren Rad größer ist als seine eigene Bohrung.

## Was zu detaillieren ist

1. **Zähne statt Fußkreisscheibe**: das Kettenrad ist heute ein glatter
   Zylinder auf Fußkreisdurchmesser. Die Zahnlücken nach DIN 8196 wären der
   nächste Schritt und ließen sich aus Teilung und Rollendurchmesser
   erzeugen.
2. **Kettenglieder statt Rollen**: heute steht je Teilung eine Rolle, die
   Laschen fehlen.
3. **Spanner und Gleitschienen** — ohne sie ist der Leertrum in Wirklichkeit
   nicht zu führen.
4. **Zwischenrad beim Zahnradtrieb**: die Drehrichtungsumkehr ist im
   Docstring beschrieben, aber nicht gebaut; die Räder stehen auf ihren
   echten Achsabständen und kämmen dort nicht.
5. **Zahnkette (Silent Chain)** als Alternative — leiser und im Pkw üblich.

## Quellen

- [Wippermann: Kettenradscheiben für Rollenketten nach DIN 8187 / DIN 8188 — Zahngeometrie nach DIN 8196](https://www.wippermann.com/produkte/kettenraeder/kettenradscheiben)
- [kettentechnik.de: Einfach-Kettenräder 08B-1 nach DIN 8187 — Teilkreis- und Kopfkreismaße](https://www.kettentechnik.de/de/2011/09/12/einfach-kettenraeder-08b-1-din-8187/)
- [rhia: Rollenketten DIN 8187 — Teilungen und Rollendurchmesser](https://kettentechnik.rhia.de/index.php/de/rollenkette-din-8187)
