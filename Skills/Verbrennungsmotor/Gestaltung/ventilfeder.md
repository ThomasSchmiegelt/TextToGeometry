<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary -->
# Ventilfeder — geometrische Gestaltung

Skript: `kt_ventilfeder.py`

## Was die Form bestimmt

Die Ventilfeder hat eine einzige Aufgabe: das Ventil **dem Nocken folgen
lassen**. Sie muss bei jeder Drehzahl stark genug sein, die Massenkräfte des
Ventiltriebs zu überwinden — sonst hebt das Ventil vom Nocken ab
(„Ventilflattern"). Ihre Auslegung hängt deshalb an zwei Dingen, die nicht in
ihr selbst stecken: am **Nockenprofil** (aus ihm folgt die Beschleunigung)
und an der **Höchstdrehzahl**.

Geometrisch folgt daraus:

- Die **Federrate** ergibt sich aus vier Maßen und einem Werkstoffwert:

  ```
  c = G · d⁴ / (8 · D_m³ · n)
  ```

  mit `G` Schubmodul, `d` Drahtdurchmesser, `D_m` mittlerer
  Windungsdurchmesser, `n` federnde Windungen. Die vierte Potenz beim Draht
  ist der Hebel: 10 % dickerer Draht sind 46 % mehr Rate.
- Der **Bauraum** ist eng: Außendurchmesser vom Ventilteller und vom
  Nachbarventil begrenzt, Einbaulänge von der Höhe des Kopfes.
- Die Feder darf bei **maximalem Ventilhub** nicht auf Block gehen; als
  Richtwert bleibt mindestens **1,0 mm Restfederweg**.

Die Blocklänge ist `n_ges · d` — bei 6 tragenden plus 2 angelegten Windungen
und 3,6 mm Draht also rund 29 mm.

## Richtwerte

| Maß | Richtwert | Generator (Teller 31 mm) |
|---|---|---|
| Außendurchmesser | ≈ 0,80 – 0,90 · Tellerdurchmesser | 27,0 mm (0,87) |
| Drahtdurchmesser | ≈ 0,10 – 0,13 · Außendurchmesser | 3,6 mm (0,133) |
| Wickelverhältnis D_m/d | 5 – 8 | 6,5 |
| federnde Windungen | 4 – 7 | 6 |
| Einbaulänge | ≈ 0,25 – 0,30 · Ventillänge | 42 mm |
| Restfederweg bei Vollhub | ≥ 1,0 mm | 3,2 mm ✔ |
| Sicherheit, wechselnde Last | S ≥ 1,5 … 2,0 | nicht gerechnet |

Die Federrate und die Sicherheit sind **Festigkeitsgrößen**; der Generator
baut Geometrie und weist sie nicht aus. Was er prüft, ist das Geometrische
daran: dass die Feder bei Vollhub nicht auf Block geht.

## Was der Generator heute baut

`baue(einbaulaenge, aussen_d, draht_d, windungen, schaft_d, teller_d,
teller_t, hub, glaette)` liefert **zwei Körper**: die Feder und den
Federteller.

Die Wendel entsteht **nicht** aus einem Sweep entlang einer Helix. Der Versuch
damit gab einen Außendurchmesser von 35,4 mm statt 27 — bei rechnerisch
richtigem Volumen. Gebaut wird stattdessen aus geraden Drahtstücken mit
Kugeln an den Stößen, acht Stücke je Windung.

Auch das Verschmelzen der Endwindung ist heikel: eine Fusion ließ 5392 mm³
auf 953 zusammenfallen. Deshalb steht dort eine Volumenprüfung, und wenn sie
nicht hält, bleiben es getrennte Körper.

Der Anschlusspunkt `oben` sitzt am Federteller und wird **gleichläufig**
angedockt: Tellerkante und Ventilschaftende zeigen beide nach oben, die Feder
hängt darunter. Gegenläufig gepaart stünde sie über dem Ventil (gemessen
z 382…424 statt 336…378).

## Was zu detaillieren ist

1. **Federrate ausweisen** — sie folgt aus Maßen, die ohnehin da sind, und
   macht die Feder vergleichbar. Eine Kraft-Weg-Angabe bei Einbaulänge und
   bei Vollhub wäre der nächste Schritt.
2. **Angelegte und geschliffene Endwindungen**: heute läuft die Wendel mit
   konstanter Steigung durch. Real sind die letzten beiden Windungen
   angelegt und plan geschliffen, sonst sitzt die Feder nicht.
3. **Ventilkeile** als eigene Körper zwischen Teller und Schaftnut.
4. **Progressive oder konische Feder** — heute zylindrisch mit konstanter
   Steigung.
5. **Doppelfeder** (innen/außen) für hohe Drehzahlen.

## Quellen

- [techeld.de: Federrechner nach DIN 2089 — Federrate, Sicherheiten](https://techeld.de/industrieheld/maschinenbau/federrechner/)
- [Wikipedia: Ventilfeder](https://de.wikipedia.org/wiki/Ventilfeder)
- [Schrick: Ventilfedern und Federteller](https://schrick.com/Ventiltrieb/Ventilfeder-Ventilfederteller/Ventilfedern/)
- [Motorlexikon: Ventilfeder — Restfederweg, Auslegung nach Nockenprofil und Drehzahl](https://motorlexikon.de/index.php?S=lexikon&I=6850)
