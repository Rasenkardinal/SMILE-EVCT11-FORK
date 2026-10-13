# HA-Lademodus 5: PV-Eigenverbrauch und Fahrzeugladung

**Status:** Anforderungs- und Designentwurf, noch nicht implementiert
**Stand:** 11.10.2026
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

## 4. Regelungsentwurf

### 4.1 Netzflussregelung

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

### 4.4 Sensorfehler und Rückkehr aus dem Fallback

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

## 6. Offene Punkte vor Implementierungsbeginn

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
