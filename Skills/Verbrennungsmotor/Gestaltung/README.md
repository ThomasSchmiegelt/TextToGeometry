<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary -->
# Geometrische Gestaltung der Bauteile

Je Bauteil eine Datei: **wovon seine Form abhängt**, welche Richtwerte der
Motorenbau dafür kennt, was der Generator heute daraus macht und was beim
Detaillieren als Nächstes ansteht.

| Bauteil | Datei | Skript |
|---|---|---|
| Kolben | [kolben.md](kolben.md) | `kt_kolben.py` |
| Pleuelstange | [pleuel.md](pleuel.md) | `kt_pleuel.py` |
| Kurbelwelle | [kurbelwelle.md](kurbelwelle.md) | `kt_kurbelwelle.py` |
| Einlassventil | [einlassventil.md](einlassventil.md) | `kt_einlassventil.py` |
| Auslassventil | [auslassventil.md](auslassventil.md) | `kt_auslassventil.py` |
| Ventilfeder | [ventilfeder.md](ventilfeder.md) | `kt_ventilfeder.py` |
| Tassenstößel mit HVA | [tassenstoessel.md](tassenstoessel.md) | `kt_stoessel.py` |
| Nockenwelle | [nockenwelle.md](nockenwelle.md) | `kt_nockenwelle.py` |
| Steuertrieb | [steuertrieb.md](steuertrieb.md) | `kt_steuertrieb.py` |
| Motorradantrieb | [motorrad_antrieb.md](motorrad_antrieb.md) | `kt_motor.py` |

Die übergreifenden Maße — jene, die **zwei Bauteile teilen** — stehen nicht
hier, sondern in `kt_auslegung.py`. Diese Dateien beschreiben, was ein
Bauteil für sich ausmacht.

`motorrad_antrieb.md` fällt aus der Reihe: es beschreibt kein Bauteil,
sondern eine **Anordnung** — Primärtrieb, parallel liegendes Getriebe und
Kettenrad. Sie steht hier, weil sie zwei Bauteile verändert hat, die es
sonst nur im Automotor gibt: die Kurbelwelle verliert ihren
Schwungradflansch, und zwei feste Maße mussten dem kurzen Hub folgen.

## Wie die Zahlen hier zu lesen sind

Fast alle Richtwerte sind auf den **Kolbendurchmesser D** (= Bohrung)
bezogen. Das ist keine Willkür: die Bohrung bestimmt die Kolbenfläche, die
Kolbenfläche mal Gasdruck die Kraft, und die Kraft bestimmt jeden Querschnitt
im Kurbeltrieb. Ein Motor lässt sich deshalb über einen weiten Bereich
maßstäblich vergrößern, und genau das prüft `kt_auslegung.selbsttest()` von
70 bis 120 mm Bohrung nach.

Wo eine Quelle einen **Bereich** angibt, steht dabei, wo der Generator
darin liegt. Wo er außerhalb liegt, steht das ebenfalls — das sind die
Stellen, an denen weitergearbeitet wird.

## Was hier absichtlich fehlt

Werkstoffe, Fertigung, Oberflächen, Toleranzen und Festigkeitsrechnung. Der
Generator baut Geometrie; was er baut, soll maßlich stimmen und zusammen
passen. Eine Aussage über Haltbarkeit trifft er nicht und soll er nicht
vortäuschen.
