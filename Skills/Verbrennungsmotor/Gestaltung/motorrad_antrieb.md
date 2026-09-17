<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary -->
# Motorradantrieb: Primärtrieb, paralleles Getriebe, Kettenrad

Erzeugt von `kt_motor._getriebe_parallel` (`getriebe_lage="parallel"`),
vorgeführt in `Beispiele/motorrad_r4.py`.

## Was den Aufbau bestimmt

Beim längs eingebauten Automotor steht das Getriebe hinter dem Motor auf
derselben Achse. Quer im Motorradrahmen geht das nicht: dort ist die
Kurbelwellenachse die **Breite** des Fahrzeugs. Was axial hinausragt, ragt
seitlich heraus — und Fahrzeugbreite ist bei einem Motorrad kein Detail,
sondern Schräglagenfreiheit. Daraus folgt alles Weitere:

* Das Getriebe liegt **parallel** zur Kurbelwelle, hinter und unter ihr, und
  bleibt vollständig in der axialen Ausdehnung des Motors.
* Angetrieben wird es von einem **Zahnradpaar**, dem Primärtrieb. Dieses Paar
  ist zugleich die **Vorgelegestufe** — anders als beim Vorgelegegetriebe des
  Längsmotors (siehe `Tools/Gestaltung/vorgelegegetriebe.md`) braucht es
  keine eigene Antriebskonstante im Getriebe. Es genügt ein
  **Zweiwellengetriebe**: je Gang ein Radpaar.
* Der Abtrieb ist ein **Kettenrad**, kein Flansch.

Gesamtübersetzung:

    i = i_primär · (z_Losrad / z_Festrad)

Gemessen am 599-cm³-Vierzylinder: i_primär = 1,896, sechs Gänge von 6,69
bis 2,67.

## Der Primärachsabstand ist nicht frei

Er folgt **nicht** aus den Zähnezahlen, sondern aus dem, was zwischen den
beiden Achsen aneinander vorbeimuss:

    a_min = r_Kurbelwange + r_größtes_Getrieberad + Luft

mit `r_Kurbelwange = Kurbelradius + Hubzapfen_d/2 + 2`. Erst danach werden
die Zähnezahlen gewählt, bei festgehaltener Übersetzung:

    z_Summe = ceil(2·a_min/m),  z1 = z_Summe/(1+i),  z2 = z_Summe − z1

Mit einem frei gewählten Paar 22/42 kam ein Achsabstand von 40,0 mm heraus,
bei 42,0 mm Wangenradius: das Getriebelager stak zu **100 %** in der
Kurbelwelle. Aus der Bedingung folgen 48/91 und 86,9 mm — knapp über den
geforderten 86,7.

## Ein Motorrad hat keinen Schwungradflansch

Am hinteren Kurbelwellenende sitzt das **Primärritzel**, nicht das
Schwungrad. Der 110-mm-Flansch des Automotors steht genau dort, wo das
Ritzel hingehört — gemessen **88,7 %** Durchdringung. An seine Stelle tritt
ein **Zapfen** vom Durchmesser des Hauptlagers, lang genug für das Ritzel
und seine Anlage (`kt_kurbeltrieb.baue(flansch_d=…, flansch_t=…)`).

## Wo die Räder axial sitzen

Primärritzel und Primärrad stehen **hinten**, bündig mit dem
Kurbelwellenende; das Kettenrad steht **vorn**, so wie am Motorrad die
Kupplung rechts und die Kette links liegt. Beide sitzen axial **neben** dem
Getriebegehäuse — sonst läuft das Primärrad (Kopfkreis 116 mm) in die
Gehäusestirnwand. Die Wellen enden aber nur 8 mm hinter der Wand, also
braucht es je ein **Stück Welle** als Überhang; am wirklichen Motorrad trägt
genau dieser Überhang den Kupplungskorb beziehungsweise das Kettenrad.

Die **Abtriebswelle** endet dafür an der Gehäusewand. Ihr Ende läge sonst in
der Ebene des Primärrades, und das ist mit 114 mm Durchmesser deutlich
breiter als der Wellenabstand von 48 mm (gemessen 2,7 %). Am Motorrad hat
diese Welle dort auch nichts zu suchen.

## Zwei Maße, die erst der kurze Hub aufdeckt

Ein Motorradmotor ist kurzhubig (67 × 42,5 statt 86 × 86). Zwei feste Maße,
die bei 86 mm Bohrung zufällig passten, stimmen dort nicht mehr:

* **Das Gegengewicht** steht dem Hubzapfen gegenüber, zeigt im UT also
  geradewegs auf die Kolbenschürze. Frei ist dort
  `(Stichmaß − Kurbelradius) − Schafthöhe`: bei 86 × 86 sind das 83,3 mm
  gegen ein Gegengewicht von 69,0 — reichlich. Bei 67 × 42,5 sind es 34,4
  gegen 42,0, gemessen **4,3 %** Durchdringung mit Kolben 2.
  `kt_kurbeltrieb` deckelt es jetzt dort, wo Pleuellänge und Kolben bekannt
  sind.
* **Der Lagerzapfen der Nockenwelle** stand fest auf 28 mm. Im
  Tassenstößelmotor läuft er über denselben Stößeln wie die Nocken; was
  weiter herunterreicht als der Grundkreis, drückt in den Stößelboden. Bei
  86 mm Bohrung ist der Grundkreis 32 mm — der Zapfen bleibt darunter. Bei
  67 mm ist er 24,9, der 28er Zapfen also 1,55 mm zu tief: **2,7 %**.
  Zapfen und Schaft folgen jetzt dem Grundkreis (0,875 bzw. 0,75), was bei
  86 mm genau die alten 28 und 24 mm ergibt.

Beide Befunde lagen die ganze Zeit vor, waren aber vom jeweils größeren
verdeckt: `pruefe()` meldet nur die **größte** Durchdringung. Wer einen
Befund behebt, muss noch einmal messen.

## Was offen ist

* Die **Kupplung** sitzt beim Motorrad im Primärrad (Kupplungskorb auf der
  Eingangswelle), nicht zwischen Kurbelwelle und Getriebe.
  `Tools/kupplung.py` ist noch auf die Pkw-Anordnung mit Schwungrad
  ausgelegt; `mit_kupplung=True` und `getriebe_lage="parallel"` gehören
  deshalb noch nicht zusammen.
* Die **Kette** zum Hinterrad wird nicht dargestellt, nur ihr Rad.
* Das **Kurbelgehäuse** fehlt, wie beim ganzen Generator: Motor und Getriebe
  teilen sich beim Motorrad ein Gehäuse.
