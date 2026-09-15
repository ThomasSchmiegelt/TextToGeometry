<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary -->
# Auslassventil — geometrische Gestaltung

Skript: `kt_auslassventil.py`, gemeinsame Grundform in `kt_ventil.py`

## Was die Form bestimmt

Das Auslassventil ist das **heiße** Bauteil des Ventiltriebs. Durch es strömt
das verbrannte Gas ab; der Tellerrand erreicht 700 bis 800 °C, und die Wärme
kann nur über zwei Wege weg: über den **Sitz** in den Zylinderkopf, solange
das Ventil geschlossen ist, und über den **Schaft** in die Führung. Alles,
worin es sich vom Einlassventil unterscheidet, folgt daraus:

- **kleiner** — für das Ausschieben leistet der Kolben die Arbeit, die
  Fläche zählt weniger als beim Einlass. Ein kleinerer Teller ist zugleich
  weniger heiße Fläche.
- **dickerer Schaft** — er ist der Wärmeleiter zur Führung.
- **Tulpenform** statt geradem Kegel: die Unterseite ist hohl gewölbt, der
  Übergang zum Schaft langgezogen. Das bringt Material an den heißen
  Tellerrand und leitet die Wärme nach innen.
- **hohler, natriumgefüllter Schaft** bei hoher Belastung: der geschlossene
  Hohlraum ist zu etwa **60 % seines Volumens** mit metallischem Natrium
  gefüllt. Natrium schmilzt bei rund 98 °C, ist im Betrieb also flüssig, und
  die Massenkräfte beim Öffnen und Schließen schleudern es im Schaft auf und
  ab. Es schaufelt die Wärme vom Teller zur Führung — daher „gefüllt", nicht
  „voll": die fehlenden 40 % sind der Raum, den es zum Schwappen braucht.

Zum Hohlraum gehört eine Regel: die verbleibende **Bodendicke** am Ende des
Schafthohlraums darf einen Mindestwert nicht unterschreiten, sonst reißt der
Teller bei hoher Temperatur.

## Richtwerte

| Maß | Richtwert | Generator (D = 86, 4 Ventile) |
|---|---|---|
| Tellerdurchmesser, 2 Ventile | ≈ 0,38 · D | 32,7 mm |
| Tellerdurchmesser, 4 Ventile | ≈ 0,31 · D | 26,7 mm |
| Schaftdurchmesser | ≈ 0,075 – 0,085 · D | 6,9 mm (0,080 · D) |
| Sitzwinkel | 45° (teils 30° bei Auslass) | 45° |
| Sitzbreite | ≈ 2 mm (breiter als Einlass — Wärme) | — |
| Natriumbohrung | ≈ 0,5 – 0,6 · Schaft | 3,8 mm (0,55) |
| Füllgrad Natrium | ≈ 60 % des Hohlraums | nicht dargestellt |
| Verhältnis Auslass/Einlass | ≈ 0,85 | 0,86 |

Der Auslassteller ist kleiner **und** sein Schaft dicker. Wer den Schaft am
eigenen Teller misst, bekommt genau das Gegenteil heraus — deshalb ist der
Bezug hier wie beim Einlass die **Bohrung**.

## Was der Generator heute baut

`kt_auslassventil.baue(bohrung, ventile_je_zylinder, teller_d, schaft_d,
laenge, natriumgefuellt)` ruft `kt_ventil.baue()` mit `kegel_form = 2.0` und
`hohl_d = 0,55 · Schaft`:

- **Tulpenform**: der Übergang folgt `r(f) = rs + (rt − rs)·(1 − f)²` statt
  dem linearen Kegel — der Radius fällt zuerst schnell und dann flach aus.
  Nachgemessen ist der Tulpenkörper schlanker als der gerade Kegel bei
  gleichem Teller und Schaft (7728 gegen 8410 mm³).
- **Hohlschaft**: eine Bohrung, die nirgends nach außen durchbricht — sie
  beginnt im Teller und endet unter der Keilnut, denn dort drückt der
  Stößel. Der Körper bleibt **ein Solid mit zwei Schalen**; gemessen 6832
  gegen 9050 mm³ beim vollen Ventil. `removeSplitter()` lässt den Hohlraum
  stehen.
- Bleibt für die Wand zu wenig übrig, wird der Schaft voll gebaut statt dünn
  gerechnet — ein 0,3-mm-Rohr gibt es nicht.

## Was zu detaillieren ist

1. **Natriumfüllung als eigener Körper** mit 60 % Volumen — heute ist nur der
   Hohlraum da. Als zweiter Körper im selben Bauteil wäre sie darstellbar und
   ihr Volumen nachmessbar.
2. **Mindestbodendicke** über dem Hohlraum prüfen und ausweisen.
3. **Sitzbreite 2 mm** als eigene Fläche, breiter als beim Einlass.
4. **Panzerung der Sitzfläche** (Stellit) — als eigener Körper oder wenigstens
   als Kennwert.
5. **Übergangsradius** statt der Kegelstumpf-Kette: die Tulpe ist heute aus
   acht Kegelstümpfen zusammengesetzt und damit facettiert.

## Quellen

- [LinkedIn / V. N. Bhatnagar: *Sodium-Filled Exhaust Valves*](https://www.linkedin.com/pulse/sodium-filled-exhaust-valves-viraaj-neel-bhatnagar) — 60 % Füllgrad, Schmelzpunkt, Wirkprinzip
- [US 2949907 A: *Coolant-filled poppet valve and method of making same*](https://patents.google.com/patent/US2949907A/en) — Mindestbodendicke am Hohlraumende
- [US 4406046 A: *Process for the production of a sodium-filled valve*](https://patents.google.com/patent/US4406046A/en)
- [ScienceDirect: *The wear and fatigue behaviours of hollow head & sodium filled engine valve*](https://www.sciencedirect.com/science/article/abs/pii/S0301679X18303438)
- [kfz-tech.de: Ventilsitzwinkel](https://www.kfz-tech.de/Ventilsitzwinkel.htm)
