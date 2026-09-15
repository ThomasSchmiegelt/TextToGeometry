<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary -->
# Kolben — geometrische Gestaltung

Skript: `kt_kolben.py`

## Was die Form bestimmt

Der Kolben hat vier Funktionsbereiche, und jeder folgt einer anderen
Forderung:

- **Kolbenboden** — begrenzt den Brennraum, nimmt den Gasdruck auf und führt
  die Wärme ab. Er ist die thermisch höchstbeanspruchte Partie.
- **Ringpartie mit Feuersteg** — dichtet ab und steuert den Ölverbrauch. Der
  Feuersteg ist der Abstand von der Bodenkante zur Oberflanke der ersten
  Ringnut; er hält den ersten Ring aus der heißesten Zone heraus.
- **Kolbennabe** — nimmt den Kolbenbolzen auf. Zwischen den beiden Naben
  bleibt der Nabenabstand NA frei; dort läuft das kleine Pleuelauge.
- **Kolbenschaft** — führt den Kolben im Zylinder und hält das Kippen beim
  Anlagewechsel klein.

Das bestimmende Maß ist die **Kompressionshöhe** KH (Bolzenmitte bis
Feuerstegoberkante). Sie geht direkt in die Bauhöhe des Motors ein, und rund
80 % der Kolbenmasse liegen in ihrem Bereich. Kleiner ist besser — aber
Ringzahl, Ringstege, Bolzendurchmesser und Feuersteghöhe setzen eine untere
Grenze.

## Richtwerte

Hauptabmessungen von Leichtmetallkolben, Viertakt-Ottomotor Pkw
(MAHLE, *Kolben und motorische Erprobung*, Kapitel 2 „Kolben-Gestaltungs­
richtlinien", Tabelle 2.1):

| Maß | Otto 4-Takt Pkw | Diesel 4-Takt Pkw | Generator (D = 86) |
|---|---|---|---|
| Durchmesser D | 65 – 105 mm | 65 – 95 mm | 40 – 200 mm |
| Gesamtlänge GL/D | 0,6 – 0,7 | 0,8 – 0,95 | 0,652 ✔ |
| Kompressionshöhe KH/D | 0,30 – 0,45 | 0,5 – 0,6 | 0,372 ✔ |
| Bolzendurchmesser BO/D | 0,20 – 0,26 | 0,3 – 0,4 | 0,256 ✔ |
| Höhe Feuersteg | 2 – 8 mm (4–10 % D) | 6 – 12 mm | 5,2 mm (0,060) ✔ |
| Höhe 1. Ringsteg St/D | 0,040 – 0,055 | 0,055 – 0,1 | 0,045 ✔ |
| Nuthöhe 1. Kolbenring | 1,0 – 1,75 mm | 1,75 – 3,5 mm | 1,5 mm ✔ |
| Schaftlänge SL/D | 0,4 – 0,5 | 0,5 – 0,65 | — |
| Nabenabstand NA/D | 0,20 – 0,35 | 0,25 – 0,35 | 0,241 ✔ |
| Bodendicke s/D | 0,06 – 0,10 | 0,14 – 0,23 | 0,081 ✔ |

Weitere Punkte aus derselben Quelle:

- **Bolzenspiel** bei schwimmender Lagerung 0,002 – 0,005 mm (Mindestspiel);
  beim Schrumpfpleuel 0,006 – 0,012 mm. Die Spielvergrößerung warm gegenüber
  kalt ist rund `0,001 · Bolzendurchmesser`.
- **Laufspiel zum Zylinder**, kalt, gemessen an einem Beispielkolben:
  Feuersteg 0,21 mm in Bolzenachsrichtung und 0,23 mm quer dazu, Schaft oben
  0,2 / 0,1 mm, Schaft unten 0,1 / 0,05 mm. Der Kolben ist also **nicht
  rund** und nicht zylindrisch: die Ringpartie hat mehr Spiel als der Schaft,
  und quer zur Bolzenachse anders als längs.
- **Desachsierung**: die Bolzenachse liegt um einen kleinen Betrag neben der
  Kolbenlängsachse. Das ändert den Anlagewechsel des Schafts an der
  Zylinderwand und senkt Laufgeräusch und Kavitationsgefahr.
- Der **Kolbenboden** kann flach, erhaben oder vertieft sein; seine Form
  hängt von Zahl und Lage der Ventile ab. Die Ventiltaschen sind Teil davon.

## Was der Generator heute baut

`baue(bohrung, kompressionshoehe, bolzen_d, schafthoehe, boden_t, ringe,
ringnut_h, ringnut_t, laufspiel, pleuel_b, ventiltaschen)`:

- Grundkörper: ein Zylinder vom Schaftende bis zum Boden, Ursprung in der
  Bolzenmitte, Durchmesser `bohrung − laufspiel`.
- Drei Ringnuten unter dem Boden, Nuthöhe 1,5 mm, Nuttiefe 2,0 mm.
- Hohler Schaft mit einem Schlitz der Breite `pleuel_b` zwischen den
  Bolzennaben.
- Bolzenbohrung quer durch.
- Ventiltaschen als Mulden im Boden, **senkrecht zur Ventilachse** gekippt.

## Umgesetzt aus dieser Recherche

1. **Gesamtlänge** von 0,93 auf **0,652 · D** — die untere Länge ist jetzt
   0,28 · D statt 0,558. Der alte Wert war Dieselmaß und kostete bei kleiner
   Bohrung die Freiheit der Kurbelwange: bei 70 mm Bohrung streifte sie den
   Schaft (4,0 % Durchdringung).
2. **Feuersteg als eigenes Maß** (`feuersteg`, 0,060 · D) — vorher war er mit
   der Bodendicke identisch. Der Selbsttest misst nach, dass die erste
   Ringnut genau einen Feuersteg unter der Bodenkante liegt.
3. **Ringstege als eigenes Maß** (`ringsteg`, 0,045 · D = 3,9 mm) statt der
   doppelten Nuthöhe (2 × 1,5 = 3 mm, also 0,023 · D). Der erste trägt den
   vollen Gasdruck, die folgenden sind 20 % schmaler.
4. **Nabenabstand** auf 0,241 · D: die Breite des kleinen Pleuelauges wird
   jetzt an der Bohrung gemessen (0,235 · D) statt als 0,75 · Pleuelbreite
   und steht in `kt_auslegung` — ein Maß für Kolben und Pleuel.
5. **Desachsierung** (`desachsierung`, 0,01 · D). Dabei kam heraus, dass sie
   nur mit der Kinematik zusammen stimmt: der Bolzen sitzt im Kolben
   außermittig, **also muss er um denselben Betrag neben der Zylinderachse
   liegen**, damit der Kolben auf ihr läuft. `kt_kinematik.pleuelrichtung()`
   nimmt dafür einen Stützpunkt. Ohne ihn wanderte der ganze Kolben von der
   Bankachse weg (gemessen −128,0 | 129,1 statt |y| = |z|).

## Was offen bleibt

- **Schaftform**: Ovalität und Balligkeit sind nicht abgebildet.
- **Kolbenringe** als eigene Körper — heute sind nur die Nuten da.
- **Kühlkanal** und **Ringträger** für die Dieselausführung.
- Die **Ventiltasche** kippt bei 120° Bankwinkel zur falschen Seite, weil die
  Verdrehung des Kolbens um seinen Bolzen zwischen den Bänken umschlägt.

## Quellen

- [MAHLE / Springer: *Kolben-Gestaltungsrichtlinien*, Kap. 2 (Leseprobe, PDF)](https://beckassets.blob.core.windows.net/product/readingsample/15907662/9783658095574-c1.pdf)
- [kfz-tech.de: Kolbenmaße (Laufspiele)](https://www.kfz-tech.de/Biblio/Kurbeltrieb/Kolbenmasse.htm)
- [Köhler/Flierl: *Verbrennungsmotoren — Motormechanik, Berechnung und Auslegung des Hubkolbenmotors* (Inhaltsverzeichnis)](https://www.gbv.de/dms/ilmenau/toc/578071274.PDF)
