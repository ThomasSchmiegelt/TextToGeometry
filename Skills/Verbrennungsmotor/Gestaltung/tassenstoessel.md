<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary -->
# Tassenstößel mit hydraulischem Ventilspielausgleich — geometrische Gestaltung

Skript: `kt_stoessel.py`

## Was die Form bestimmt

Der Tassenstößel sitzt **direkt zwischen Nocken und Ventilschaft**. Das ist
der kürzeste denkbare Ventiltrieb: keine Hebel, keine Stoßstangen, wenig
bewegte Masse, hohe Drehzahlfestigkeit. Der Preis ist, dass die
Nockenwellenachse **genau über der Ventilachse** liegen muss — anders als
beim Schlepphebel, wo die Welle seitlich versetzt steht. Genau das prüft
`kt_motor.pruefe()` als „Fluchtung" nach.

Der **Durchmesser** der Tasse folgt nicht aus dem Ventil, sondern aus dem
**Nocken**. Bei einem Flachstößel wandert der Berührpunkt seitlich aus,
während der Nocken abrollt. Die Auswanderung ist die Ableitung des Hubes nach
dem Nockenwinkel:

```
e_max = max |dh / dφ|        (φ im Bogenmaß)
```

Die Tasse muss mindestens `2 · e_max` breit sein, sonst läuft der Nocken über
ihre Kante. Das ist die eigentliche Auslegungsregel dieses Bauteils — und sie
ist aus dem eigenen Nockenprofil **ausrechenbar**, nicht aus einer Tabelle zu
nehmen.

Der **hydraulische Ausgleich** (HVA) sitzt im Boden der Tasse: Öl drückt über
eine Bohrung mit Rückschlagventil einen kleinen Kolben aus, bis das
Ventilspiel verschwunden ist. Beim Öffnen schließt das Rückschlagventil, der
Ölpolster trägt, und ein enger Ringspalt lässt ihn langsam nachgeben
(„Leck-Down"). Geometrisch heißt das: ein Ausgleichskolben mit Verstellweg,
eine Ölbohrung und der Ringspalt.

## Richtwerte

| Maß | Richtwert | Generator (D = 86) |
|---|---|---|
| Tassendurchmesser | ≥ 2 · max\|dh/dφ\|, üblich 0,33 – 0,40 · Bohrung | 33,0 mm (0,384) |
| Bauhöhe | ≈ 0,8 – 1,0 · Tassendurchmesser | 26,0 mm (0,79) |
| Bodendicke (Nockenlauffläche) | ≈ 3 – 5 mm | 4,0 mm |
| Mantelstärke | ≈ 2 – 3 mm | 2,5 mm |
| Ausgleichskolben-Ø | ≈ 0,45 – 0,55 · Tasse | 16,0 mm (0,48) |
| Verstellweg HVA | ≈ 3 – 5 mm | 4,0 mm |
| Ölbohrung | ≈ 2 – 4 mm | 3,0 mm |

Die Tasse wird oft mit leicht **balliger** Lauffläche und um einen kleinen
Betrag **außermittig** zum Nocken gebaut, damit sie sich im Betrieb dreht und
gleichmäßig verschleißt. Beides fehlt im Modell.

## Was der Generator heute baut

`baue(tassen_d, hoehe, boden_t, wand, hva_d, hva_weg, oelbohrung_d,
ventil_d)` liefert **zwei Körper**: die Tasse und den Ausgleichskolben.

- Tasse: Topf mit Boden oben (Nockenlauffläche) und offenem Mantel nach
  unten.
- Ausgleichskolben im Boden, um `hva_weg` verstellbar dargestellt.
- Ölbohrung im Mantel.
- Anschlusspunkte `nocken` (Boden oben, Art *flaeche* — dort läuft der
  Nocken) und `ventil` (unten, Art *flaeche*, Kennmaß = Schaftdurchmesser
  des Ventils).

Das Kennmaß `ventil_d` ist kein Bauteilmaß, sondern die Probe: **je
Ventilsorte** wird ein eigenes Stößelmuster gebaut, weil Ein- und
Auslassventil verschieden dicke Schäfte haben (6,0 gegen 6,9 mm bei 86 mm
Bohrung). Mit einem gemeinsamen Muster meldete die Paarungsprüfung zu Recht
„Kennmaß 6,9 gegen 6,0 mm".

## Was zu detaillieren ist

1. ✔ **Der Durchmesser folgt jetzt dem Nockenprofil**:
   `kt_nockenwelle.auswanderung()` rechnet `max|dh/dφ|` numerisch aus, und
   `kt_auslegung` nimmt `max(0,384 · D, 2 · Auswanderung + 0,06 · D)`. Bei
   10 mm Hub und 60° Flanke sind das 15,0 mm Auswanderung und damit 30 mm
   Mindesttasse — der Kosinusverlauf gibt geschlossen `hub · π / (2 · fl)`,
   und der Selbsttest misst die Zahl gegen diesen Ausdruck.
2. **Ballige Lauffläche** und **Außermittigkeit** zum Nocken, damit sich die
   Tasse dreht.
3. **Ringspalt und Rückschlagventil** des HVA als Geometrie.
4. **Ölversorgungsnut** außen am Mantel.

## Quellen

- [Wikipedia: Tassenstößel](https://de.wikipedia.org/wiki/Tassenst%C3%B6%C3%9Fel)
- [Wikipedia: Hydrostößel — Rückschlagventil, Ringspalt, Wirkweise](https://de.wikipedia.org/wiki/Hydrost%C3%B6%C3%9Fel)
- [Wikipedia: Ventilsteuerung](https://de.wikipedia.org/wiki/Ventilsteuerung)
- [nockenwellensaetze.de: PD-Motoren — Tassenstößel und Ventilspiel](https://www.nockenwellensaetze.de/pd-motoren-tassenstosel-und-ventilspiel/)
