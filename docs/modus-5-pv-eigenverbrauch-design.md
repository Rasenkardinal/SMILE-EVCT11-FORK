# HA-Lademodus 5: PV-Eigenverbrauch und Fahrzeugladung

**Status:** Erste Regelung umgesetzt (Abschnitt 5.2), Praxistest ausstehend
**Stand:** 13.10.2026
**Zielintegration:** AlphaESS Wallbox Bridge, G2T-Wallbox

## 1. Projektziel

Der Home-Assistant-Lademodus 5 soll in der dunklen Jahreszeit den
PV-Eigenverbrauch maximieren und die Einspeisung ins Netz minimieren. Die
Fahrzeugladung soll dafür verfügbare lokale Energie aufnehmen und mit dem
Hausakku zusammenspielen. Ein begrenzter Netzbezug ist zulässig, aber kein
Selbstzweck und darf nicht beliebig hoch werden. Anders als bei der klassischen
Überschussladung muss nicht erst ein vollständig geladener Hausakku oder eine
Netzeinspeisung vorliegen, bevor das Fahrzeug lädt.

Modus 5 ist eine **eigene Betriebsart der Home-Assistant-Integration**, kein
neuer AlphaESS-API-Modus. Für die Wallbox wird weiterhin der AlphaESS-Modus 4
„Benutzerdefinierte Ladeleistung“ verwendet. Der bisherige AlphaESS-Modus 1
„Langsamladung“ dient als Fallback zur klassischen Überschussregelung.

## 2. Ausgangslage und gewünschtes Verhalten

Bei der klassischen Überschussladung (HA-/AlphaESS-Modus 1) wird die
Fahrzeugladung an Überschuss beziehungsweise Einspeisung angepasst. Das
vermeidet Netzbezug, kann aber dazu führen, dass verfügbare lokale Energie
zunächst vollständig in den Hausakku fliesst und das Auto erst später oder gar
nicht lädt. Modus 5 soll die Nutzung lokaler Energie zwischen Fahrzeugladung
und Hausakku so abstimmen, dass unnötige Einspeisung vermieden wird, ohne den
Netzbezug aus den Augen zu verlieren.

Für Modus 5 gilt dagegen:

- Hauptziel ist hoher lokaler Eigenverbrauch bei möglichst geringer
  Netzeinspeisung; Fahrzeug und Hausakku werden dabei gemeinsam betrachtet.
- Das Fahrzeug soll verfügbare Energie aufnehmen können, bevor sie unnötig
  eingespeist wird. Oberhalb einer konfigurierten SOC-Untergrenze darf der
  Hausakku die Fahrzeugladung unterstützen und sich dafür entladen.
- Ein gewisser Netzbezug ist zur Erreichung des Eigenverbrauchsziels erlaubt,
  wird aber anhand des tatsächlichen Netzflusses begrenzt und geregelt.
- Der Grenzwert für Netzbezug ist eine Schutz-/Nebenbedingung, nicht das
  eigentliche Optimierungsziel. Die Regelung soll Einspeisung reduzieren,
  ohne dafür unbegrenzt Energie aus dem Netz zu beziehen.
- Die Mindestladung des Hausakkus bleibt konfigurierbar.
- Schwankungen und Regelverzögerungen sollen nicht zu hektischen oder
  widersprüchlichen Wallbox-Befehlen führen.

## 3. Bestätigte Mess- und Systemdaten

### 3.1 Verfügbare Sensoren

Für die Regelung stehen installationsabhängige Modbus-Entitäten zur Verfügung:

| Messgröße | Einheit | Aktualisierung/Latenz | Verwendung |
|---|---:|---:|---|
| PV-Leistung | W | ca. 2 s | Erzeugungs- und Plausibilitätskontext |
| Hausakku-SOC | % | ca. 2 s | Mindest-SOC-Schutz und Wiederanlauf |
| Hauslast | W | ca. 2 s | Verbrauchskontext; Wallbox-Umschaltung am Lastanstieg erkennen |
| Netzbezug/Einspeisung | W | ca. 2 s | Primäre Rückmeldung für die Leistungsregelung |
| Batterieladung/-entladung | W | ca. 2 s | Hausakku-Verhalten beobachten |

Netzfluss und Batterieleistung können im normalen Regelbetrieb sowie bei
Lastwechseln schwanken. Das Gesamtsystem regelt vergleichsweise träge.

**Vorzeichenkonventionen, vom Nutzer bestätigt:**

- Netzfluss: positiver Wert = Netzbezug; negativer Wert = Einspeisung.
- Batterieleistung: positiver Wert = Entladung; negativer Wert = Ladung.

Die Entity-IDs dieser Sensoren unterscheiden sich je Installation. Auswahlfelder
für diese fünf Sensoren stehen in den Integrationsoptionen bereit. Die Auswahl
speichert die Entity-IDs; eine automatische Erfassung, Analyse oder Regelung
dieser Sensoren ist damit noch nicht implementiert.

### 3.2 Wallbox und Verzögerungen

- Die Wallbox wird über die AlphaESS-API gesteuert.
- Eine Änderung wird üblicherweise innerhalb von etwa 30 Sekunden wirksam.
- Die Wallbox-Reaktion ist direkt am Anstieg beziehungsweise Rückgang der
  Hauslast erkennbar.
- Ladeleistung und Ladestatus der Wallbox kommen aus der AlphaESS-Cloud und
  haben etwa 1–2 Minuten Latenz. Sie sind daher nicht als schnelle primäre
  Regelrückmeldung geeignet.
- Ein automatischer Phasenwechsel unterbricht den Ladevorgang vorübergehend,
  vermutlich wegen des Handshakes zwischen Wallbox und On-Board-Charger (OBC).
  Diese Erklärung ist eine Beobachtung/Hypothese, nicht unabhängig verifiziert.
- Nach einem API-Befehl muss die Regelung eine erneute Entscheidung mindestens
  etwa 30 Sekunden zurückstellen. Der zeitliche Mindestabstand ist kein Beleg,
  dass die physische Umschaltung zu diesem Zeitpunkt garantiert abgeschlossen
  ist.

### 3.3 Ladeleistungstabellen und Fahrzeugabhängigkeit

Die gemessene Ladeleistung ist fahrzeugabhängig. Insbesondere ist der reale
Sprung zwischen 3-phasig 7 A und 8 A fahrzeugspezifisch und bestätigt. Die
folgenden vom Nutzer gemeldeten Werte sind als Ausgangsprofil dokumentiert:

| Strom | 1-phasig | 3-phasig |
|---:|---:|---:|
| 6 A | 1.420 W | 2.990 W |
| 7 A | 1.640 W | 3.440 W |
| 8 A | 1.840 W | 5.540 W |
| 9 A | 2.075 W | 6.260 W |
| 10 A | 2.250 W | 6.960 W |
| 11 A | 2.480 W | 7.550 W |
| 12 A | 2.720 W | 8.280 W |
| 13 A | 2.960 W | 9.000 W |
| 14 A | 3.170 W | 9.650 W |
| 15 A | 3.400 W | 10.350 W |

Alle aufgeführten Werte, einschließlich der niedrigeren dreiphasigen Werte und
des Sprungs 7 A → 8 A, wurden vom Nutzer als korrekt bestätigt. Die 16-A-
Varianten wurden weggelassen, da die Wallbox nach Nutzerbeobachtung höchstens
bis 15 A steuert.

Die Tabellenwerte sind stabile Endwerte nach dem Einpendeln. Beim
dreiphasigen Wechsel von 6 A auf 7 A oder 8 A schwankt die Ladeleistung
zunächst stark, erkennbar an der Hauslast, und stabilisiert sich dann auf
einem niedrigeren Wert. Vermutlich gibt die Wallbox mehr Leistung frei, als
das Fahrzeug bzw. sein Bordladegerät übernimmt, und das Fahrzeug regelt
herunter. Diese Ursache ist noch nicht bestätigt. Die Regelung muss daher mit
den stabilen Endwerten rechnen und Messwerte während des Einschwingens nicht
als Grundlage für weitere Stufenwechsel verwenden. Fahrzeugprofile sollen
dafür eine Einschwingzeit erfassen und unzuverlässige Stufen ausschließen
können.

Mehrere Fahrzeugprofile mit jeweils eigener Tabelle sollen dauerhaft gepflegt
werden können. Der Nutzer soll das aktive Profil über eine Fahrzeugauswahl
wählen und Profile über die Home-Assistant-Optionsoberfläche hinzufügen,
bearbeiten und löschen können. Die obenstehende Tabelle dient nur als
Ausgangsprofil und darf nicht als universelle Kennlinie aller Fahrzeuge
behandelt werden.

### 3.4 Geplante Verlaufsaufzeichnung

Die bisher bereitgestellte History-Aufzeichnung wird vorerst nicht als
Grundlage für Regelungsdesign oder Grenzwerte verwendet, da sie für die
beabsichtigte Analyse nicht aussagekräftig genug ist. Der Nutzer zeichnet bei
ausreichender PV-Produktion zunächst seine manuelle Ladestrategie auf und
stellt anschließend einen gemeinsamen Werteverlauf aller relevanten Sensoren
bereit. Diese Aufzeichnung soll insbesondere Netzfluss, PV-Leistung,
Hauslast, Batterieleistung, Hausakku-SOC sowie die Lade-/Einstellungsänderungen
zeitlich nachvollziehbar enthalten.

Bis diese geeignete Aufzeichnung vorliegt, werden aus historischen Messdaten
keine Regelparameter abgeleitet.

### 3.5 Ergebnisse Messzyklus 13.10.2026

Manueller Testzyklus 09:20–10:25 Uhr (Ortszeit, Rohdaten im Ordner
`Messzyklus/`, Zeitstempel dort in UTC). Ausgewertet wurden 25
Einstellungsänderungen aus dem Sensor „Letzte angeforderte Änderung“.

Bestätigt:

- **Aktualisierung:** Hauslast und Netzfluss ca. 1 s, Batterieleistung ca.
  1–3 s, PV ca. 2–3 s, Hausakku-SOC nur in 0,4-%-Schritten.
- **Energiebilanz und Vorzeichen:** PV + Netz + Batterie ≈ Hauslast
  (Abweichung ca. 50–130 W). Netz positiv = Bezug, Batterie positiv =
  Entladung. Die Hauslast enthält die Wallbox-Leistung.
- **Befehlskette:** API angenommen nach ca. 2,5 s, Portalbestätigung nach
  ca. 3–9 s.
- **Reaktion der Wallbox:** Hauslast und Netzfluss erreichen 50 % der
  Änderung reproduzierbar **25–29 s** nach dem Befehl (Lademodusstart: ca.
  43 s, Phasenwechsel 1→3: ca. 37 s).
- **Reihenfolge:** Hauslast und Netzfluss reagieren gleichzeitig. Die
  Batterie folgt ca. 5–15 s später und gleicht den Netzfluss dann auf ca.
  0 ± 100 W aus. Bis dahin zeigt der Netzfluss kurzzeitige Spitzen bis ca.
  2 kW. Danach regelt die Batterie noch über Minuten langsam nach.
- **Folge für die Regelgröße:** Solange der Hausakku freigegeben ist, bleibt
  der Netzfluss nahe 0 W und zeigt kaum, ob PV-Überschuss oder Defizit
  besteht. Das Defizit erscheint in der Batterieleistung. Eine geeignete
  Regelgröße ist die Bilanz PV − Hauslast (bzw. Netz + Batterie); der Netzfluss
  allein ist nur bei gesperrtem Hausakku aussagekräftig.
- **Phasenwechsel:** Die Ladung fällt ca. 35–45 s nach dem Befehl für nur
  ca. 10–15 s auf die Grundlast ab und läuft dann in der neuen Stufe weiter.
- **Cloud-Werte:** Die Wallbox-Leistung wird fest ca. alle 73 s aktualisiert
  (effektive Verzögerung 0–73 s zusätzlich zur Wallbox-Reaktion). Der
  Wallbox-Status ändert sich erst ca. 33–46 s nach dem Befehl. Beide Werte
  sind für die Regelung zu langsam und nur zur Plausibilisierung geeignet.
- **1-phasige Stufen:** Die Schritte von ca. 230 W liegen im Bereich der
  normalen Lastschwankung und sind in der Hauslast kaum einzeln erkennbar.
- **3-phasig 7 A instabil:** Die Leistung pendelt zwischen ca. 3,4 kW und
  ca. 5,2–5,5 kW. Beim ersten Durchgang beruhigte sie sich nach ca. 5 min
  auf ca. 3,4 kW (mit vereinzelten Spitzen). Beim zweiten Durchgang mit
  gesperrtem Hausakku pendelte sie über die gesamten ca. 8 min. Andere
  3-phasige Stufen (6, 8, 9, 16 A) waren nach ca. 25–55 s stabil.
- **Hausakku-Sperre:** Batterieleistung 0 W von ca. 10:08 bis 10:21 Uhr.
  Bei 3-phasig 6 A und 7 A wurden dabei ca. 1,4–1,6 kW eingespeist; die
  Schwankungen der 7-A-Stufe gingen ungedämpft ins Netz (ca. −1,6 bis
  +0,7 kW).

Folgerungen für den Entwurf:

- Nach einem Befehl mindestens ca. 45–60 s warten, bevor die Reaktion
  bewertet wird; nach einem Phasenwechsel ca. 60–90 s.
- 3-phasig 7 A wird vorerst **zugelassen** (Nutzerentscheidung), da sie die
  einzige dreiphasige Stufe zwischen 6 A und 8 A ist und einphasiges Laden
  verlustreicher ist. Das Fahrzeugprofil kennzeichnet sie als **instabile
  Stufe**. Solange eine instabile Stufe aktiv ist, wertet die Regelung einen
  längeren Mittelwert aus (Zeitraum konfigurierbar; Messdaten legen
  mindestens ca. 3–5 min nahe) und trifft in dieser Zeit keine
  Folgeentscheidung aufgrund einzelner Leistungsspitzen. Der SOC-Schutz und
  die Netzbezugsgrenze bleiben davon unberührt. Das Ausschließen einer
  Stufe bleibt als Profiloption für spätere Fahrzeuge möglich.
- Die Auswertung der Bilanz bzw. Batterieleistung ist bei freigegebenem
  Hausakku der Netzfluss-Auswertung vorzuziehen. Abschnitt 4.1 ist
  entsprechend zu überarbeiten.

## 4. Regelungsentwurf

### 4.1 Netzflussregelung

> Umgesetzt wurde stattdessen die Bilanzregelung aus Abschnitt 3.5
> (PV − Hauslast ohne Wallbox); der Netzfluss dient nur noch als
> Bezugsschutz. Details in Abschnitt 5.2.

Primäre Grundlage ist ein **konfigurierbarer gleitender Durchschnitt des
Netzflusses mit Hysterese**. Der Regler soll den Netzfluss nahe einem
konfigurierbaren Zielbereich um möglichst geringe Einspeisung halten und
zugleich eine Obergrenze für anhaltenden Netzbezug einhalten:

1. Standard-Mittelungszeitraum: **2 Minuten**, in den Optionen änderbar.
2. Zwei getrennte Grenzwerte:
   - mittlerer Netzbezug, ab dem die Ladeleistung reduziert werden muss, um
     die zulässige Bezugsgrenze einzuhalten;
   - mittlere Einspeisung, ab der die Ladeleistung erhöht werden darf, um
     lokale Energie besser zu nutzen und Einspeisung zu verringern.
3. Die konkreten Grenzwerte sind noch festzulegen und müssen konfigurierbar
   sein.
4. Die Hysterese soll verhindern, dass die Regelung wegen kleiner Schwankungen
   fortlaufend zwischen Erhöhen und Reduzieren wechselt.
5. Eine Erhöhung beziehungsweise Reduzierung darf nicht allein durch einen
   einzelnen verrauschten Messwert ausgelöst werden.

Die exakte Filterdefinition (zeitgewichteter gleitender Mittelwert oder
messwertbasierter Durchschnitt), das Verhalten bei Lücken im Messverlauf und
die Behandlung von Messwerten während einer Wallbox-Änderung sind vor der
Implementierung festzulegen oder durch eine geeignete, nachvollziehbare
Voreinstellung zu definieren.

### 4.2 Anpassung der Ladeleistung

Zwei Regelungsarten sollen angeboten werden:

- **Stufenregelung (Standard):** pro Entscheidung genau eine verfügbare Stufe
  der ausgewählten Fahrzeugtabelle ändern; danach mindestens ca. 30 Sekunden
  keine weitere Leistungsentscheidung treffen.
- **Direktregelung (optional):** direkt die passende Stufe der ausgewählten
  Fahrzeugtabelle anfahren.

Bei Auswahl einer Ladeleistung müssen die tatsächlichen fahrzeugspezifischen
Tabellenwerte verwendet werden, nicht eine lineare W/A-Annahme. Bei einem
Phasenwechsel sind die Ladepause und die verzögerte Cloud-Rückmeldung zu
berücksichtigen. Die Betriebsart soll keine schnellen Folgekommandos senden,
während ein vorheriger Wechsel wahrscheinlich noch läuft.

**Phasenwahl und Ladeverluste:** Einphasiges Laden ist nach Nutzerangabe
deutlich verlustreicher als dreiphasiges. Eine einphasige Stufe ist deshalb
kein gleichwertiger Ersatz für eine dreiphasige Stufe mit ähnlicher
Leistung (z. B. 1-phasig 15 A ≈ 3,40 kW statt 3-phasig 7 A ≈ 3,44 kW).
Die Regelung soll dreiphasiges Laden bevorzugen, sobald der Überschuss für
die kleinste stabile dreiphasige Stufe reicht. Einphasig soll sie nur laden,
wenn die dreiphasige Mindeststufe nicht erreicht wird. Liegt der Überschuss
zwischen zwei dreiphasigen Stufen, ist die niedrigere dreiphasige Stufe
einer leistungsgleichen einphasigen Stufe vorzuziehen; der Rest bleibt für
den Hausakku. Die Verluste wurden bisher nicht gemessen (die Messwerte sind
wallboxseitige AC-Leistungen). Ob das Fahrzeugprofil einen Wirkungsgrad oder
eine Phasenpräferenz je Stufe erhält, ist noch festzulegen.

### 4.3 Hausakku-Mindest-SOC

- Mindest-SOC ist einstellbar.
- Oberhalb des Mindest-SOC darf der Hausakku das Auto unterstützen.
- Sinkt der SOC unter den Mindestwert, wird die Fahrzeugleistung zunächst
  stufenweise reduziert.
- Reicht die minimale verfügbare Ladeleistung nicht aus, um den SOC-Schutz
  einzuhalten, wird die Fahrzeugladung pausiert.
- Nach SOC-bedingter Pause darf erst bei
  **Mindest-SOC + einstellbarer SOC-Hysterese** wieder gestartet werden.

Die genauen SOC-Voreinstellungen, die Behandlung eines SOC-Werts exakt auf
dem Grenzwert und die Art, wie die Wallbox-Ladung pausiert/wieder gestartet
wird, sind noch festzulegen. Insbesondere muss geprüft werden, wie ein
Ladestopp in der bestehenden Integration zuverlässig und ohne Verwechslung mit
„Fahrzeug getrennt“ ausgelöst werden kann.

### 4.4 Optionale Hausakku-Sperre per Dispatch-Mode

Zusätzlich besteht die Möglichkeit, den Hausakku über den Dispatch-Mode zu
sperren. In diesem Fall soll die Regelung ausschließlich PV-Leistung und
Netzfluss berücksichtigen; der Hausakku unterstützt die Fahrzeugladung dann
nicht. Der Nutzer kann den Hausakku bereits manuell sperren und hat dies im
letzten Teil des aktuellen Testzyklus getan. Dieser Abschnitt ist in den
Sensorverläufen an einer Nulllinie des Batterieleistungssensors erkennbar.

Die Auswertung soll die Phasen mit und ohne Hausakku-Sperre getrennt
betrachten, insbesondere hinsichtlich Netzfluss-Schwankungen,
Stabilisierungszeit und Eignung von Hauslast und Netzfluss als Regelgrößen.

Nachteil: Die Sperre verhindert nicht nur die Entladung, sondern auch die
Ladung des Hausakkus. PV-Überschuss, den das Fahrzeug nicht aufnimmt, wird
dann eingespeist statt im Hausakku gespeichert. Die Sperre ist deshalb
vorerst nur eine im Hinterkopf behaltene Option und kein Bestandteil der
geplanten Standardregelung.

Ob und wie Modus 5 die Sperre automatisch per Dispatch-Mode setzt und wieder
aufhebt, ist noch festzulegen.

### 4.5 Sensorfehler und Rückkehr aus dem Fallback

- Ein benötigter Sensor ist fehlerhaft, wenn er fehlt, `unknown` oder
  `unavailable` ist oder länger als **10 Sekunden** keinen neuen Messwert
  geliefert hat.
- Bei einem Sensorfehler soll die Betriebsart auf die klassische
  Überschussregelung, AlphaESS-Modus 1, zurückfallen.
- Sobald alle benötigten Sensoren wieder **30 Sekunden** durchgehend gültige
  und frische Werte liefern, soll Modus 5 automatisch fortgesetzt werden.
- Für die Umsetzung muss der Integrationszustand die vom Nutzer gewählte
  Betriebsabsicht „HA-Modus 5“ vom aktuell an die API gesendeten AlphaESS-Modus
  trennen, damit der Fallback die automatische Rückkehr nicht verhindert.

Zu klären ist noch, ob „10 Sekunden ohne neuen Messwert“ anhand von
`last_changed`, `last_updated` oder einer von der Integration erfassten
Empfangszeit bewertet wird. Manche gültigen Sensoren veröffentlichen denselben
Wert erneut, ohne ihren Zustand zu ändern; `last_changed` allein wäre dafür
ungeeignet.

## 5. Integrations- und Bedienanforderungen

1. HA-Modus 5 ergänzen, ohne einen AlphaESS-API-Modus 5 zu senden.
2. Beim Aktivieren von HA-Modus 5 den API-Modus 4
   „Benutzerdefinierte Ladeleistung“ verwenden.
3. Modus 1 als klassische Überschussregelung für den definierten Sensor-Fallback
   verwenden.
4. Die für Modus 5 erforderlichen Sensor-Entity-IDs in den
   Integrationsoptionen per Entity-Auswahl konfigurieren. PV-Leistung,
   Hausakku-SOC, Hauslast, Netzfluss und Batterieleistung werden in diesem
   Arbeitsschritt auswählbar; der Wallbox-Leistungssensor ist bereits Teil der
   Integration.
5. Optionen für Mittelungszeitraum, Import-/Exportgrenze,
   SOC-Mindestwert, SOC-Hysterese und Regelungsart bereitstellen.
6. Mehrere Fahrzeugprofile einschließlich eigener Ladeleistungstabellen über
   die Optionsoberfläche verwalten und ein aktives Profil auswählen können.
7. Ladeleistungswerte validieren: gültige Phasen-/Stromkombinationen,
   positive Leistung, keine doppelten Profilkennungen und verständliche
   Fehleranzeige bei ungültigen Eingaben.
8. Die Integrationsoberfläche soll aktuellen HA-Betriebsmodus, aktives
   Fahrzeugprofil, Regelungszustand (Normalbetrieb/Fallback/SOC-Schutz),
   gleitenden Netzfluss und letzte Regelaktion nachvollziehbar anzeigen.
   Die genauen Entitäten dafür sind noch zu entwerfen.
9. Vorhandene AlphaESS-Schreibschutz-, Zeitfenster-, Smart-Mode- und
   Rückleselogik nicht unbeabsichtigt verändern.
10. Optionsänderungen müssen ohne Verlust bestehender Zugangsdaten oder
    Konfigurationsdaten migrierbar sein.

### 5.1 Umgesetzte Konfiguration

Die Integrationsoptionen sind als Menü aufgebaut:

- **Aktualisierungsintervall und Überwachungssensoren:** wie bisher.
- **PV-Laderegelung (Modus 5):** aktives Fahrzeug, Regelungsart und
  Parameter. Die Regelung selbst ist noch nicht implementiert; die Werte
  werden nur gespeichert.
- **Fahrzeugprofile:** Fahrzeug hinzufügen, bearbeiten, löschen. Jedes Profil
  hat einen Namen, je einen aufklappbaren Bereich „1-phasig“ und „3-phasig“
  mit den stabilen Leistungen für 6–15 A sowie Mehrfachauswahlen für
  instabile und ausgeschlossene Stufen. Ohne gespeicherte Profile gilt das
  „Standardfahrzeug“ mit den Messwerten aus Abschnitt 3.3 und 3-phasig 7 A als
  instabile Stufe. Das letzte Profil kann nicht gelöscht werden.

Validierung: Name erforderlich und eindeutig, Leistungen größer 0 W
(höchstens 4.000 W einphasig bzw. 12.000 W dreiphasig) und mit steigendem
Strom nicht fallend, keine Stufe zugleich instabil und ausgeschlossen,
mindestens eine nutzbare Stufe.

Standardwerte der Regelungsparameter:

| Parameter | Standard | Bereich | Herkunft |
|---|---:|---:|---|
| Regelungsart | Stufenregelung | Stufe/Direkt | Nutzerentscheidung |
| Mittelungszeitraum | 120 s | 30–900 s | Nutzerentscheidung |
| Mittelungszeitraum instabile Stufen | 240 s | 60–1.800 s | Messzyklus (3–5 min) |
| Wartezeit nach Stromänderung | 60 s | 30–600 s | Messzyklus (Reaktion 25–29 s + Einschwingen) |
| Wartezeit nach Phasenwechsel | 90 s | 30–600 s | Messzyklus (Pause 35–45 s + 10–15 s) |
| Zulässiges Defizit beim Laden | 0 W | 0–5.000 W | Nutzerentscheidung (0 = nur PV-Überschuss) |
| Netzbezugsschutz: Toleranz über dem zulässigen Defizit | 200 W | 0–5.000 W | vorläufiger Vorschlag |
| Netzbezugsschutz greift nach | 30 s | 10–300 s | vorläufiger Vorschlag |
| Reaktionserkennung: Bestätigungszeit | 10 s | 0–60 s (0 = aus) | vorläufiger Vorschlag |
| Überschussreserve vor Erhöhung | 200 W | 0–3.000 W | vorläufiger Vorschlag |
| Mindest-SOC Hausakku | 20 % | 0–100 % | vorläufiger Vorschlag |
| SOC-Hysterese für Wiederanlauf | 5 % | 1–50 % | vorläufiger Vorschlag |
| Sensor gilt als veraltet nach | 10 s | 5–120 s | Nutzerentscheidung |
| Gültige Sensorzeit vor Rückkehr | 30 s | 10–600 s | Nutzerentscheidung |

Die Überschussreserve bedeutet: erhöhen nur, wenn der Überschuss die
Leistung der nächsten Stufe um diesen Wert übersteigt.

Das zulässige Defizit beim Laden (X) wird zum Überschuss addiert; alle
Entscheidungen (Starten, Erhöhen, Senken) rechnen mit dem Ladebudget
Überschuss + X. Das Defizit deckt je nach Lage der Hausakku oder das Netz.
Der Netzbezugsschutz misst weiterhin den Netzbezug und greift erst oberhalb
von X + Toleranz. Mit X = 0 gilt das bisherige Verhalten.

X lässt sich zusätzlich über die Slider-Entität „Zulässiges Defizit beim
Laden“ (Kategorie Konfiguration) ändern. Der Slider schreibt dieselbe Option,
lädt die Integration aber nicht neu: Die laufende Regelung übernimmt den Wert
ab der nächsten Entscheidung, die gebildeten Mittelwerte bleiben erhalten.

### 5.2 Umgesetzte Regelung (erste Version)

Die erste Fassung ist umgesetzt in `pv_control.py` (Entscheidungslogik ohne
Home-Assistant-Abhängigkeit, mit Simulationstests) und `pv_mode.py` (Anbindung
an Home Assistant). Sie legt die offenen Punkte aus Abschnitt 6 vorläufig so
fest:

- **Bedienung:** Das Select „Lademodus“ bietet bei G2T zusätzlich
  „PV-Eigenverbrauch (Modus 5)“. Die Absicht „Modus 5 aktiv“ wird als Option
  `pv_mode_active` gespeichert und überlebt Neustarts. Wählt man einen anderen
  Modus, wird Modus 5 beendet und der gewählte AlphaESS-Modus geschrieben.
  Aktivierung nur bei G2T und wenn PV-Leistung, Hauslast, Netzfluss und
  Hausakku-SOC ausgewählt sind; der Batterieleistungssensor ist optional.
- **Regelgröße (statt Netzfluss, siehe 3.5):**
  verfügbar für die Wallbox = PV Ø − (Hauslast Ø − Wallbox Ø). Die
  Wallbox-Leistung wird in Modus 4 aus der Profiltabelle der aktuellen Stufe
  geschätzt (nur bei Status „Charging“), in Modus 1 aus der Cloud-Leistung.
- **Mittelwert:** Abtastung alle 5 s, gleitendes Fenster nach Zeit
  (Standard 120 s, bei instabilen Stufen 240 s). Die erste Entscheidung fällt
  erst nach einem vollen Fenster. Nach jedem Befehl werden alle Messwerte
  verworfen und die Wartezeit (Strom 60 s, Phasenwechsel oder Wechsel
  von/zu Modus 1: 90 s) abgewartet.
- **Reaktionserkennung:** Beim Befehl auf eine Modus-4-Stufe wird die erwartete
  Hauslast berechnet: Hauslast Ø der letzten 15 s + (Zielleistung −
  bisherige Wallbox-Leistung). Liegt die gemessene Hauslast die
  Bestätigungszeit lang (Standard 10 s) ununterbrochen in einem Band von
  ±35 % des kleineren Werts aus Leistungsänderung und Zielleistung um diesen
  Erwartungswert, endet die Wartezeit vorzeitig. Das Band schließt den alten
  Wert und die Ladepause beim Phasenwechsel aus. Verschieben andere
  Verbraucher die Hauslast aus dem Band, gilt die volle Wartezeit. Ein
  zufälliger Treffer durch einen fremden Verbraucher beendet nur das Warten;
  die Hauslast fließt danach ohnehin korrekt in den neuen Mittelwert ein.
  Bei kleinen Änderungen (einphasig ±1 A, Band ca. ±80 W) greift die
  Erkennung meist nicht. Wechsel zu Modus 1 nutzen immer die volle Wartezeit.
- **Erhöhen:** auf eine Stufe, deren Tabellenleistung ≤ Ladebudget −
  Überschussreserve ist. **Senken:** sobald die Leistung der aktuellen Stufe
  über dem Ladebudget liegt (Ladebudget = verfügbar + zulässiges Defizit
  beim Laden). Dazwischen bleibt die Stufe (Totband =
  Reserve); in diesem Bereich deckt der Hausakku kleine Lücken.
- **Direktregelung:** fährt die höchste passende Stufe in einem Befehl an;
  **Stufenregelung:** eine Stufe pro Entscheidung.
- **Stufenleiter:** ausgeschlossene Stufen entfallen; einphasige Stufen nur
  unterhalb der kleinsten nutzbaren dreiphasigen Stufe.
- **Pause:** Reicht der Überschuss für keine Stufe, wird AlphaESS-Modus 1
  geschrieben (kein START/STOP). Modus 1 dient auch als SOC-Schutz und
  Sensor-Fallback.
- **Netzbezugsschutz:** liegt der Netzbezug-Mittelwert nach der einstellbaren
  Zeit (Standard 30 s, höchstens der Mittelungszeitraum) über zulässigem
  Defizit beim Laden + Toleranz,
  wird sofort reduziert (direkt: um die Überschreitung;
  Stufe: eine Stufe), ohne das volle Fenster abzuwarten.
- **SOC-Schutz:** unter Mindest-SOC sofort Modus 1; Rückkehr erst ab
  Mindest-SOC + Hysterese.
- **Sensorfehler:** fehlend, `unknown`/`unavailable`, nicht numerisch oder bei
  Leistungssensoren älter als die eingestellte Zeit (geprüft über
  `last_reported`, ersatzweise `last_updated`) → Modus 1. Rückkehr nach der
  eingestellten Zeit mit durchgehend gültigen Werten. Der SOC wird nur auf
  Gültigkeit geprüft, weil er sich selten ändert.
- **Zeitgesteuertes Laden aktiv / kein Fahrzeug:** keine Befehle.
- **Diagnose:** Sensor „PV-Laderegelung“ mit Zustand (z. B. „Mittelwert wird
  gebildet“, „Regelung aktiv“, „Warten auf Überschuss“, „Warten auf
  Wallbox-Reaktion“, „SOC-Schutz“, „Fallback Sensorfehler“) und Attributen
  für Mittelwerte, verfügbare Leistung, aktuelle und Zielstufe, Fahrzeugprofil,
  Regelungsart und letzte Aktion.
- Manuelle Strom- oder Phasenänderungen während Modus 5 werden bei der
  nächsten Entscheidung überschrieben. Die Hausakku-Sperre (4.4) ist nicht
  Bestandteil dieser Version.

## 6. Offene Punkte vor Implementierungsbeginn

> Abschnitt 5.2 legt die meisten dieser Punkte vorläufig fest. Offen bleiben
> die Hausakku-Sperre, der Praxistest von Modus 1 als Pause sowie
> Fahrzeugwechsel und externe Änderungen über App oder Portal.

Die folgenden Details sind noch nicht festgelegt:

- Konkrete Standardwerte und zulässige Bereiche der Netzbezugs- und
  Einspeisegrenzen.
- Ob ein zusätzlicher Sicherheitsabstand/Leistungsreservewert benötigt wird.
- Exakte Durchschnittsdefinition, Abtast-/Fensterbehandlung und Verhalten bei
  lückenhaften Sensordaten.
- Konkrete Wertebereiche und Voreinstellungen für Mindest-SOC und
  SOC-Hysterese.
- Wie Modus 5 pausiert und wieder startet, ohne unerwünschte Zustandswechsel
  oder wiederholte API-Kommandos auszulösen.
- Welche Sensoren zwingend für den sicheren Regelbetrieb erforderlich sind.
  Der Netzflusssensor und Hausakku-SOC sind für die bisher beschriebene
  Grundregelung naheliegend; die genaue notwendige Sensorliste muss bestätigt
  werden.
- Der Nutzer hat einen Fallback zu Modus 1 und automatische Rückkehr gewählt.
  Zu prüfen ist, ob Modus 1 auf dem konkreten AlphaESS-System tatsächlich die
  gewünschte klassische Überschussregelung startet und wie sich das mit den
  übrigen AlphaESS-Strategie-/Zeitfenstereinstellungen verträgt.
- Ob Modus 5 den Hausakku per Dispatch-Mode automatisch sperren soll, unter
  welchen Bedingungen die Sperre gesetzt und aufgehoben wird und wie sie sich
  mit SOC-Schutz und Fallback verträgt.
- Verhalten bei manuellem Moduswechsel, Neustart von Home Assistant,
  Fahrzeugwechsel während des Ladens und externen Änderungen über App/Portal.
- Verifikation, wie die ausgewählte API-Current-Einstellung mit dem
  fahrzeugspezifischen Leistungsprofil zusammenspielt und wie
  Phasenwechsel-Befehle in der aktuellen API-Schreiblogik abgebildet werden.
- Test- und Abnahmekriterien, einschließlich Simulation mit gemeinsam
  aufgezeichneten PV-, Netz-, Batterie-, SOC-, Hauslast- und Wallbox-Werten.

## 7. Empfohlene nächste Schritte

1. Offene Punkte aus Abschnitt 6 festlegen, bevor Regelungslogik geschrieben
   wird.
2. Eine synchronisierte Aufzeichnung der manuellen Regelung bei ausreichender
   PV-Produktion mit Netz-, PV-, Hauslast-, Batterieleistungs-, SOC- und
   Wallbox-Signalen bereitstellen. Dadurch lassen sich Filter, Hysterese und
   Verzögerungen offline gegen echte Verläufe prüfen.
3. Ein zustandsbasiertes Regelungsmodell mit Simulationstests erstellen.
4. Optionen, Sensorzuordnung und Fahrzeugprofilverwaltung implementieren.
5. Danach die API-Ansteuerung mit expliziter Änderungsrate, Fallback,
   Wiederanlauf und Statusdiagnostik ergänzen.
6. Erst nach Tests mit aufgezeichneten Daten und kontrolliertem
   Home-Assistant-/Wallbox-Testbetrieb eine Version veröffentlichen.

## 8. Abgrenzung

Dieses Dokument ist ein vollständiges **Design- und Lastenheft für den
Entwurfsstand**, aber keine Implementierungsfreigabe für unentschiedene
Grenzwerte oder Sicherheitsdetails. Es enthält weder Zugangsdaten noch
Portal-Tokens. Historische Rohdaten werden nicht in das Repository kopiert.
