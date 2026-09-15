<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary -->
# Kurbelwelle — geometrische Gestaltung

Skript: `kt_kurbelwelle.py`, Winkeltabellen in `kt_bauformen.py`

## Was die Form bestimmt

Die Kurbelwelle ist kein Festigkeitsproblem allein, sondern vor allem ein
**Steifigkeitsproblem**: sie ist ein langer, mehrfach gekröpfter Träger, der
mit der Gaskraft schwingt. Drei Größen bestimmen ihre Steifigkeit:

1. **Länge** — also die Zapfenteilung, und die ist der Zylinderabstand.
2. **Zapfendurchmesser** — die Torsionssteifigkeit geht mit der **vierten
   Potenz** des Durchmessers.
3. **Zapfenüberdeckung** (crankpin overlap, CPO) — wie weit Hubzapfen und
   benachbarter Hauptlagerzapfen einander axial gesehen überdecken:

```
CPO = (Hauptlager-Ø + Hubzapfen-Ø − Hub) / 2
```

Eine **positive** Überdeckung heißt, dass Material des Hubzapfens direkt in
Material des Hauptlagerzapfens übergeht; die Wange muss dann weniger
übertragen. Wird CPO negativ — langer Hub, dünne Zapfen —, hängt der
Hubzapfen allein an der Wange, und die Welle wird weich.

Weitere Gestaltungspunkte:

- **Hohlkehlen** an den Zapfenübergängen sind die Dauerbruchstellen. Nach
  Graßmann ist der Hohlkehlenradius nicht konstant, sondern wächst mit dem
  Durchmesser.
- **Gegengewichte** gleichen die umlaufenden Massen aus. Sie sitzen nicht
  immer genau gegenüber ihrem Hubzapfen: bei einem kreuzebenigen 90°-V8 der
  Serienbauart fehlen sie am mittleren Hauptlager ganz, und die vorderen und
  hinteren sind dafür dicker.
- **Zapfenwinkel und Zündfolge** sind Bauformwissen, keine Formel — siehe
  `kt_bauformen.py` und dessen Docstring.

## Richtwerte

| Maß | Richtwert | Generator (D = 86, Hub 86) |
|---|---|---|
| Hubzapfen-Ø / D | ≈ 0,55 – 0,60 | 0,558 (48 mm) |
| Hauptlager-Ø / D | ≈ 0,60 – 0,68 | 0,628 (54 mm) |
| Wangendicke / D | ≈ 0,18 – 0,22 | 0,209 (18 mm) |
| Hauptlagerbreite / D | ≈ 0,28 – 0,33 | 0,302 (26 mm) |
| Zapfenüberdeckung CPO | > 0, je mehr desto steifer | 8,0 mm |
| Hubzapfenbreite | Pleuelbreite + Bund | 26 mm (R), 48 mm (V) |

Beim V-Motor teilen sich **zwei** Pleuel einen Hubzapfen; er ist deshalb
doppelt so breit, und die beiden Bänke stehen zwangsläufig um eine
Pleuelbreite gegeneinander versetzt (der **Bankversatz**).

Stimmen Bankwinkel und Zündabstand nicht überein, wird der Hubzapfen
**gesplittet** — die beiden Hälften stehen um `|720/z − Bankwinkel|`
zueinander verdreht. Ein 90°-V6 bekommt so 30°, ein 60°-V6 sechzig; V8/90°,
V10/72° und V12/60° brauchen keinen Versatz, weil ihr Bankwinkel gleich dem
Zündabstand ist.

## Was der Generator heute baut

`baue(bauform, hub, zylinderabstand, hauptlager_d, hubzapfen_d, hubzapfen_b,
hauptlager_b, wange_t, wange_b, gegengewicht, flansch_d, flansch_t,
steuertrieb_d, steuertrieb_l, v8_kreuzebene, bankwinkel)`:

- Hauptlagerzapfen, Wange, Hubzapfen, Wange — je Kröpfung, entlang +X.
- Die Zapfenteilung **ist** der Zylinderabstand: was über
  `Hauptlager + 2 Wangen + Hubzapfen` hinausgeht, wird auf die
  Hauptlagerbreite gelegt. Ein zu kleiner Abstand wird zurückgewiesen.
- Wange als Scheibe mit Radius `Kurbelradius + halber Hubzapfen + 2 mm`,
  auf der Zapfenseite beschnitten — das Gegengewicht.
- Gesplittete Hubzapfen als zwei Hälften mit dem Versatzwinkel.
- Steuertriebzapfen vorn, Schwungradflansch hinten.

## Was zu detaillieren ist

1. ✔ **Zapfenüberdeckung wird nachgewiesen**: `CPO > 0` steht in
   `kt_auslegung.pruefe()` und wird über alle zehn Bauformen und drei
   Baugrößen geprüft. Bei 86 × 86 sind es 8,0 mm.
2. **Hohlkehlen** an allen Zapfenübergängen — heute sind es scharfe Kanten.
3. **Ölbohrungen** vom Hauptlager zum Hubzapfen.
4. **Gegengewichte nach Bauform**: der kreuzebenige V8 hat am mittleren
   Hauptlager keines, die äußeren sind dicker. Heute bekommt jede Wange
   dasselbe Gewicht.
5. **Schwingungsdämpfer** am vorderen Wellenende.

## Quellen

- [*Contemporary Crankshaft Design* (PDF)](https://www.idc-online.com/technical_references/pdfs/mechanical_engineering/Contemporary_Crankshaft_Design.pdf) — CPO-Formel, Steifigkeitsparameter, Gegengewichte beim kreuzebenigen V8
- [Zeno / Lueger: *Kurbelwellen*](http://www.zeno.org/Lueger-1904/A/Kurbelwellen) — Hohlkehlenradien nach Graßmann
- [Springer: *Berechnung und Auslegung von Bauteilen*](https://link.springer.com/chapter/10.1007/978-3-322-96833-3_4)
