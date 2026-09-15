<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary -->
# Nockenwelle — geometrische Gestaltung

Skript: `kt_nockenwelle.py`

## Was die Form bestimmt

Die Nockenwelle ist das einzige Bauteil des Motors, dessen Form unmittelbar
eine **Funktion über der Zeit** ist. Jeder andere Körper ist ein Querschnitt,
der eine Kraft trägt; der Nocken **ist** die Ventilerhebungskurve, in Metall
gelegt. Aus dieser Kurve folgt alles Weitere: Geschwindigkeit,
Beschleunigung, die nötige Federkraft, die Auswanderung auf dem Stößel.

Die Kurve zerfällt in drei Abschnitte:

- **Grundkreis** — das Ventil ist zu. Sein Durchmesser bestimmt, wie steif
  die Welle an dieser Stelle ist und wie weit sie über dem Stößel liegen
  muss: die Achshöhe ist `Blockhöhe + Ventillänge + Stößelhöhe +
  Grundkreisradius`.
- **Flanken** — Öffnen und Schließen. Ihre Steilheit ist die
  Ventilgeschwindigkeit; ihr Krümmungswechsel die Beschleunigung, und die
  muss die Feder aufbringen.
- **Spitze** — der Vollhub. Die Erhebung über dem Grundkreis **ist** der
  Ventilhub. Das ist die Zusage dieses Bauteils, und der Selbsttest misst
  sie nach: größter Radius minus Grundkreisradius muss der Hub sein.

Zwei Dinge, die keine Formel sind, sondern Auslegung:

- Die Nockenwelle dreht **halb so schnell** wie die Kurbelwelle. Aus 180°
  Kurbelwinkel werden 90° Nockenwinkel.
- Die **Spreizung** ist die Lage des Nockenscheitels, gemessen in Grad
  Kurbelwinkel nach dem oberen Totpunkt — üblich 100 bis 115°. Ohne sie
  stünde ein Zylinder im OT mit voll geöffnetem Einlassventil; nachgemessen
  durchdrangen sich Kolben und Ventil dann zu 51,7 %. Die Spreizung ist kein
  Korrekturfaktor, sondern der Grund, warum es sie gibt.

Beim **Flachstößel** — und der Tassenstößel ist einer — ist der Hub *nicht*
der radiale Abstand in Stößelrichtung, sondern die **größte Projektion** der
ganzen Nockenkontur auf diese Richtung. Der Berührpunkt wandert seitlich aus.
Mit dem radialen Maß gerechnet blieb eine Durchdringung von 4,8 % zwischen
Welle und Stößel: die Welle saß zu tief.

## Richtwerte

| Maß | Richtwert | Generator (D = 86) |
|---|---|---|
| Grundkreisdurchmesser | ≈ 0,33 – 0,40 · Bohrung | 32,0 mm (0,372) |
| Ventilhub / Grundkreisradius | ≈ 0,5 – 0,7 | 0,625 |
| Nockenbreite | ≈ 0,8 – 1,0 · Ventilteller-Ø ÷ 2,5 | 12,0 mm |
| Wellenschaft-Ø | < Grundkreis, ≈ 0,7 · Grundkreis | 24,0 mm (0,75) |
| Lagerzapfen-Ø | ≈ 0,85 · Grundkreis | 28,0 mm |
| Lager | eines je zwei Nocken, plus eines am Ende | ✔ |
| Antriebszapfen-Ø | = Bohrung des Kettenrades | 26,0 mm |
| Flankenwinkel (halbe Öffnung) | 50 – 70° Nockenwinkel | 60° |

Der Öffnungswinkel allein sagt wenig: zwei Wellen mit gleichem
Öffnungswinkel können völlig verschiedene Steuerzeiten haben. Erst
Öffnungswinkel **und** Spreizung beschreiben die Welle.

## Was der Generator heute baut

`baue(winkel, grundkreis_d, hub, nocken_b, abstand, orte, lager_d, lager_b,
welle_d, antrieb_d, antrieb_l, flanke)`:

- Durchgehender Schaft entlang +X.
- Je Nocken ein Profil aus 48 Stützpunkten: Grundkreis plus eine Erhebung,
  die über `flanke` Grad zu beiden Seiten der Spitze mit einem
  **Kosinusverlauf** aufgebaut wird — glatt und ohne Knick am Übergang:

  ```
  r(a) = rg + h · 0,5 · (1 + cos(π · d / fl))   für |d| < fl
  r(a) = rg                                      sonst
  ```
- `orte` gibt jedem Nocken seine x-Lage. Mit gleichmäßiger Teilung bekam ein
  Vierventiler acht Nocken im Zylinderabstand und eine 822 mm lange Welle
  statt 224 mm.
- Lagerzapfen vor dem ersten und nach jedem zweiten Nocken, eines am Ende.
- Antriebszapfen vorn, Achse −X.

## Was zu detaillieren ist

1. **Rampen**: real beginnt und endet die Erhebung mit einer flachen
   Anlauframpe, die das Spiel sanft aufnimmt. Der Kosinusverlauf geht
   stattdessen mit waagerechter Tangente in den Grundkreis über — glatt, aber
   ohne Rampe.
2. **Ruckfreies Profil**: der Kosinus hat am Übergang einen Sprung in der
   dritten Ableitung. Ein Polynom- oder Polydyne-Profil wäre der nächste
   Schritt und ließe sich am selben Ort einsetzen.
3. ✔ **Auswanderung wird ausgewiesen**: `auswanderung()` liefert
   `max|dh/dφ|`, die Kennwerte führen sie und `stoessel_mindest_d`, und
   `kt_auslegung` legt den Tassendurchmesser danach aus (siehe
   [tassenstoessel.md](tassenstoessel.md)).
4. **Hohlwelle** mit Ölkanal statt Vollmaterial.
5. **Axiallager** — heute ist die Welle in X nicht festgelegt.

## Quellen

- [Wikipedia: Nockenwelle](https://de.wikipedia.org/wiki/Nockenwelle)
- [gaenssle.de: Nockenprofil-Berechnung — Grundkreis, Hub, Öffnungswinkel und Steuerzeiten](http://www.gaenssle.de/NocDyno01G.htm)
- [gaenssle.de: Nockenform und Nockenberechnung](http://www.gaenssle.de/NocInteres01.htm)
