<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary -->
# Einlassventil — geometrische Gestaltung

Skript: `kt_einlassventil.py`, gemeinsame Grundform in `kt_ventil.py`

## Was die Form bestimmt

Beim Einlassventil zählt die **Fläche**: der Ladungswechsel ist die Grenze
der Füllung, und der Einlass hat gegen den Saugunterdruck zu arbeiten, nicht
gegen den vom Kolben erzeugten Ausschiebedruck. Deshalb ist es das größere
der beiden Ventile.

Zugleich ist es das **kühlere**: die einströmende Frischladung kühlt Teller
und Schaft. Es darf deshalb leicht gebaut werden — dünner Schaft, voller
(nicht hohler) Werkstoff, gerader Übergang vom Teller zum Schaft. Leichtigkeit
zählt unmittelbar, denn die Feder muss die Masse bei jeder Umdrehung zweimal
umkehren.

Die **Ventilzahl** ist eine Flächenrechnung: zwei Teller mit je 0,36 · D
haben zusammen mehr Öffnungsfläche als ein Teller mit 0,45 · D
(2 · 0,36² = 0,259 gegen 0,45² = 0,203, also +28 %). Genau deshalb gibt es
den Vierventiler; die kleineren Teller sind zudem leichter und vertragen
höhere Drehzahl.

## Richtwerte

| Maß | Richtwert | Generator (D = 86, 4 Ventile) |
|---|---|---|
| Tellerdurchmesser, 2 Ventile | ≈ 0,45 · D | 38,7 mm |
| Tellerdurchmesser, 4 Ventile | ≈ 0,36 · D | 31,0 mm |
| Schaftdurchmesser | ≈ 0,065 – 0,075 · D | 6,0 mm (0,070 · D) |
| Sitzwinkel | 45° | 45° |
| Sitzbreite | ≈ 1,5 mm | — (nicht ausgeführt) |
| Tellerrandhöhe | ≈ 0,04 – 0,06 · Teller | 3,0 mm (0,097) |
| Gesamtlänge | ≈ 0,5 · Blockhöhe + 40 mm | 152,8 mm |
| Ventilhub | ≈ 0,25 · Teller | 10 mm (0,32) |

Der Schaftdurchmesser wird bewusst an der **Bohrung** gemessen, nicht am
eigenen Teller: sonst käme beim Vergleich mit dem Auslassventil das Gegenteil
heraus, denn der Auslass hat den *kleineren* Teller und den *dickeren*
Schaft.

Am Schaftende sitzt eine **Keilnut**, in die zwei Ventilkeile greifen; sie
halten den Federteller. Die Schaftendfläche ist gehärtet, denn dort drückt
der Stößel.

## Was der Generator heute baut

`kt_einlassventil.baue(bohrung, ventile_je_zylinder, teller_d, schaft_d,
laenge)` ruft `kt_ventil.baue()` mit `kegel_form = 1.0` (gerader Kegel) und
`hohl_d = 0` (voller Schaft). Gebaut wird entlang +Z, Ursprung in der
Tellerunterkante:

- Sitzfase als Kegelstumpf, darüber der Tellerrand als Scheibe.
- Übergang Teller → Schaft als Kegel.
- Schaft, am Ende eine umlaufende Keilnut.

Anschlusspunkte `sitz` (Tellerunterkante, Achse −Z), `schaft` (Mitte,
Achse +Z, Art *welle*) und `schaft_ende` (oben, Art *flaeche*).

## Was zu detaillieren ist

1. ✔ **Sitzbreite** ist ein eigenes Maß: 1,5 mm am Einlass, 2,0 am Auslass
   (`SITZBREITE`), und der ausgewiesene Sitzdurchmesser folgt daraus.
2. ✔ **Tellerrandhöhe** liegt jetzt bei 0,05 · Teller (1,55 mm bei 31 mm)
   statt fest 3 mm; der Selbsttest prüft 0,04 … 0,06.
3. **Übergangsradius** Teller → Schaft statt des Kegels — der gerade Kegel
   ist strömungstechnisch die schlechtere Form und auch fertigungsfern.
4. **Ventilkeile und Federteller** als eigene Körper; heute ist nur die Nut
   da, in die sie greifen würden.
5. **Schaftführung**: das Gegenstück im Kopf fehlt, weil es keinen
   Zylinderkopf gibt.

## Gemessene Grenze

Bei sehr weitem Bankwinkel steht das Einlassventil fast waagerecht und taucht
am Kolbenrand ein. Nachgemessen an einem V8 mit **120° Bankwinkel**: die
Zylinderachse steht 60° aus der Senkrechten, das Einlassventil weitere 12°
nach innen — zusammen 48°, und sein Teller sitzt dann 96 mm neben der
Kolbenmitte statt über ihr. Die Durchdringung beträgt 2377 mm³ (25,8 % des
Ventils) und liegt am **Kolbenrand**, nicht in einer Ventiltasche; keine
Tasche kann sie decken.

Dasselbe tritt bei einem V10 mit 90° auf (Tabellenwert wäre 72°). Bei allen
üblichen Bankwinkeln — V8/90°, V10/72°, V12/60°, V6/60…90° — tritt es nicht
auf. Es ist damit eine Grenze der Auslegung und kein Fehler der Konstruktion:
ein 120°-V8 mit vier geneigten Ventilen je Zylinder braucht einen anderen
Brennraum.

## Quellen

- [WL Motorsport: *Ventile herstellen* — Benennung der Maße (L, D, d, Sitzwinkel, Sitzhöhe, Tellerrandhöhe, Gesamttellerstärke)](https://www.wlmotorsport.de/ventile-herstellen-spezial)
- [kfz-tech.de: Ventilsitzwinkel](https://www.kfz-tech.de/Ventilsitzwinkel.htm)
- [MS Motorservice: Ventilführungen](https://ms-motorservice.de/technipedia/post/ventilfuehrungen)
