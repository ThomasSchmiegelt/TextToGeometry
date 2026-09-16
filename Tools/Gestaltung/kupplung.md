<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary -->
# Kupplung — geometrische Gestaltung

Skript: `Tools/kupplung.py`

## Was die Form bestimmt

Die Kupplung trennt und überträgt. Aus dem Übertragen folgt ihre Größe:

```
M = z · μ · F_N · r_m          r_m = (D_a + D_i) / 4
```

`z` ist die Zahl der **Reibflächen** — eine Scheibe reibt auf **beiden**
Seiten, also z = 2; zwei Scheiben geben z = 4. `μ` liegt beim trockenen
organischen Belag bei rund 0,3.

Die Anpresskraft geht mit der Fläche (∝ D²), der Reibradius mit D — also
geht das Moment mit **D³**. Daraus folgt beides:

- Der Belagdurchmesser wächst mit der dritten Wurzel des Moments:
  `D_a = 215 mm · (V_H / 2000 cm³)^(1/3)`
- Die **zweite Scheibe** macht den Belag um `2^(1/3) = 0,794` kleiner, weil
  sie die Zahl der Reibflächen verdoppelt.

Genau das ist der Grund, warum große Motoren zwei Scheiben bekommen und
keinen Riesenbelag: eine 310-mm-Scheibe wiegt zu viel und dreht zu träge
hoch, zwei 246er tun dasselbe. Nachgerechnet am 6-Liter-V12:

| | eine Scheibe | zwei Scheiben |
|---|---|---|
| Belag außen | 310 mm | **246 mm** |
| Reibflächen | 2 | **4** |
| mittlerer Reibradius | 127,9 mm | 101,5 mm |
| Schwungraddurchmesser | 360 mm | 285 mm |

Der Generator entscheidet selbst: über 280 mm Belagdurchmesser geht er auf
zwei Scheiben.

## Der Aufbau

```
Schwungrad ── Scheibe 1 ── [Zwischenplatte ── Scheibe 2] ── Druckplatte
   │                                                            │
Kurbelwellen-                                            Membranfeder
flansch,                                                        │
Anlasserzahnkranz                              Kupplungsdeckel, Ausrücklager
```

- Das **Schwungrad** sitzt am Kurbelwellenflansch, trägt den
  Anlasserzahnkranz und hat mittig eine **abgesetzte Aussparung**: außen für
  die Nabe der Kupplungsscheibe, innen der Sitz für das Pilotlager der
  Getriebeeingangswelle.
- Die **Kupplungsscheibe** läuft mit ihrer Nabe auf der Verzahnung der
  Getriebeeingangswelle — **axial verschiebbar**, sonst ließe sie sich nicht
  lösen — und trägt beidseits Reibbeläge.
- Der **Torsionsdämpfer**: Federn zwischen Nabe und Belagträger nehmen die
  Drehschwingungen auf, beim V12 die Zündstöße. Sie sitzen in
  **ausgestanzten Fenstern** in Träger und Nabenflansch.
- Die **Membranfeder** ist eine geschlitzte Tellerfeder. Die Schlitze machen
  aus dem Rand die Ausrückzungen; die Bauart hält ihre Kraft über einen
  großen Weg nahezu konstant, also bleibt die Anpresskraft auch bei
  verschlissenen Belägen gleich. Das ist der Grund, warum keine
  Schraubenfedern verwendet werden.
- Das **Ausrücklager** drückt die Zungen nach innen und trennt.

## Was die Prüfung gezeigt hat

- Die **Dämpferfedern** stecken ohne Fenster zu 33 % im Belagträger.
- Die **Scheibennabe** stak zu 20 % im Schwungrad, solange dieses keine
  Aussparung hatte.

Beides ist Geometrie, die im echten Bauteil selbstverständlich da ist und im
Modell erst auffällt, wenn man misst.

## Was offen bleibt

- **Belagfederung** (Segmente zwischen den Belägen für sanftes Anfahren).
- Die Membranfeder ist ein glatter geschlitzter Kegel, keine gewölbte Feder
  mit Kennlinie.
- **Ausrückmechanik** (Hebel, Nehmerzylinder) fehlt.
- Die Verzahnungen von Nabe und Anlasserzahnkranz sind glatt dargestellt.

## Quellen

- [Wikipedia: Einscheibentrockenkupplung — Aufbau, Membranfeder, axial verschiebbare Nabe](https://de.wikipedia.org/wiki/Einscheibentrockenkupplung)
- [tec.Lehrerfreund: Kupplungen (2) — Kraftfluss Schwungrad → Scheibe → Getriebewelle](https://www.lehrerfreund.de/technik/1s/kupplungen-2/3216)
- [auto-motor-und-sport: Trockenkupplungssysteme](https://www.auto-motor-und-sport.de/motoren/trockenkupplungssysteme-an-pkw/)
- [DE 196 10 699 A1: Kupplungsscheibe einer Einscheiben-Trockenkupplung](https://patents.google.com/patent/DE19610699A1/de)
