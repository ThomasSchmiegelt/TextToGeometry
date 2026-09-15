<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary -->
# Pleuelstange — geometrische Gestaltung

Skript: `kt_pleuel.py`

## Was die Form bestimmt

Das Pleuel überträgt die Gaskraft vom Kolben auf die Kurbelwelle und läuft
dabei selbst auf und ab — es ist also zugleich hoch belastet und soll leicht
sein. Daraus folgt alles:

- Der **Schaft** wird auf **Knickung** ausgelegt, nicht auf Zug. Er knickt in
  zwei verschiedenen Ebenen verschieden: in der Schwenkebene (um die
  X-Achse) sind beide Augen gelenkig, quer dazu (Y-Achse) ist er
  eingespannt. Ein Doppel-T-Profil bringt genau diese Anisotropie: `Ixx`
  wird etwa **3 bis 3,5 mal** `Iyy` gewählt. Bei `Ixx = 4 · Iyy` wären beide
  Richtungen gleich sicher; man bleibt bewusst knapp darunter und legt gegen
  Knickung um die X-Achse aus.
- Die **Biegespannung** ist nicht dort am größten, wo die Gaskraft am größten
  ist: die Gaskraft wirkt nahe am oberen Totpunkt, die größte Biegung tritt
  bei einem Kurbelwinkel von **65° bis 70° nach OT** auf.
- Die **Augen** müssen formstabil sein, denn sie sind zugleich Lagerstellen.

Das **Stichmaß** (Abstand der Augenmitten) ist die eine Länge, die den
ganzen Kurbeltrieb bestimmt: aus ihm, dem Hub und der Kompressionshöhe folgt
die Blockhöhe.

## Richtwerte

**Schaftquerschnitt** (I-Profil, Maße in der Schaftmitte; `t` = Dicke von
Steg und Flansch):

```
B = 4 t        Breite  (über die ganze Länge konstant)
H = 5 t        Höhe    (veränderlich, siehe unten)
A = 11 t²      Querschnittsfläche
```

Die Höhe verjüngt sich zum Kolben hin und wächst zur Kurbel:

```
H1 = 0,75 … 0,90 · H     am kleinen Auge
H2 = 1,10 … 1,25 · H     am großen Auge
```

**Längenverhältnis** Pleuellänge zu Kurbelradius: `l / r = 4 … 5` nach dem
Maschinenelemente-Lehrbuch — das ist λ = r/l = 0,20 … 0,25. Der
Fahrzeugmotorenbau liegt kürzer, bei **λ ≈ 0,25 … 0,31** (l/r = 3,2 … 4),
weil die Bauhöhe zählt; der Generator nimmt λ ≈ 0,287 (Stichmaß = 1,75 · Hub).
Die Grenzen 0,20 … 0,35 prüft `kt_motor.pruefe()` nach.

**Lagerlängen** nach dem Lehrbuch, aus der zulässigen Lagerpressung:

```
großes Auge (Hubzapfen)  l = 1,25 … 1,50 · d,  p = 7 … 12,5 N/mm²
kleines Auge (Bolzen)    l = 1,50 … 2,00 · d,  p = 10,5 … 15 N/mm²
```

Diese Werte stammen aus der langsam laufenden Stationärmaschine. Der
schnelllaufende Fahrzeugmotor baut deutlich schmaler — dort ist das kleine
Auge rund **0,75 · Breite des großen**, und der Nabenabstand im Kolben
begrenzt es zusätzlich auf 0,20 … 0,35 · Bohrung. Der Generator folgt der
Fahrzeugpraxis; die Lehrbuchwerte stehen hier als Herkunft der Regel, nicht
als Vorgabe.

**Lagerschalen**: Stahlrücken mit dünner Laufschicht, etwa 0,75 mm
Weißmetall im großen Auge; im kleinen Auge eine Bronzebuchse von rund 3 mm
Wandstärke.

## Was der Generator heute baut

`baue(stichmass, hubzapfen_d, bolzen_d, breite, schaft_b, schaft_t,
auge_wand, klein_wand, spiel)`:

- Großes Auge als Scheibe mit `auge_wand` = 7 mm Wandstärke, Breite
  `breite`.
- Kleines Auge als Scheibe, Breite `0,75 · breite`, Wandstärke 5 mm.
- Schaft als Quader `schaft_t × schaft_b`, aus dem beidseitig eine Nut
  ausgeschnitten ist — ein **angedeutetes** I-Profil mit konstanter Höhe.
- Beide Bohrungen mit `spiel` = 0,06 mm Lagerspiel.

## Was zu detaillieren ist

1. **Echtes I-Profil nach B = 4t / H = 5t** statt des ausgeschnittenen
   Quaders, und zwar mit **veränderlicher Höhe**: 0,85 · H am kleinen Auge,
   1,15 · H am großen. Das ist die auffälligste Abweichung von der realen
   Form und zugleich leicht zu bauen (ein Profil an drei Stationen, dazwischen
   aufgespannt).
2. **Teilung des großen Auges** mit Deckel und zwei Schrauben. Heute ist das
   Auge ungeteilt, und damit ließe sich das Pleuel gar nicht montieren.
3. **Schmierbohrung** vom großen zum kleinen Auge im Schaft.
4. **Wandstärken aus dem Zapfendurchmesser** statt fest 7 und 5 mm — bei
   120 mm Bohrung ist das Auge sonst zu dünn.

## Quellen

- [Rohini College / ME8593 *Design of Machine Elements*, Kap. 5 „Design of the connecting rod" (PDF)](https://www.rcet.org.in/uploads/academics/rohini_44925101382.pdf) — I-Profil B = 4t, H = 5t, H1/H2, Lagerlängen, Lagerpressungen
- [Springer: *Pleuel* (Kapitelvorschau)](https://link.springer.com/content/pdf/10.1007/978-3-642-97181-5_4)
- [Motorlexikon: Pleuelstangenverhältnis](https://motorlexikon.de/index.php?S=lexikon&I=5516)
