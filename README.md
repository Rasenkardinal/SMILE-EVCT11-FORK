# AlphaESS Wallbox Bridge – persönlicher Fork

> **Fork-Version 0.7.9 (Beta)** – basierend auf dem Originalstand 0.5.7.

## Zweck dieses Forks

[Rasenkardinal/SMILE-EVCT11-FORK](https://github.com/Rasenkardinal/SMILE-EVCT11-FORK)
ist ein persönlicher Fork von
[wfa001/SMILE-EVCT11](https://github.com/wfa001/SMILE-EVCT11).
Er dient dazu, die Integration an die eigene Wallbox-Nutzung und Bedienung
anzupassen, ohne das Originalprojekt zu verändern.

Der Fork ersetzt die ursprüngliche Integration. Die Integrations-Domain
`alphaess_portal_bridge`, die eindeutigen Entitätskennungen und die
Konfigurationsstruktur bleiben erhalten. Original und Fork sind deshalb
**nicht parallel installierbar** und sollten nicht gleichzeitig als installierte
Quellen in HACS verwaltet werden.

Der Betreiber nutzt die Integration nach eigener Rückmeldung erfolgreich mit
seiner G3-Wallbox. Die Modellbezeichnung G3 ist dabei von den im Code erkannten
Portal-Profilen `g1T` und `g2T` zu unterscheiden; ein zusätzliches Profil `g3T`
wurde durch diesen Fork nicht implementiert.

### Eigene Änderungen gegenüber dem Original

- **10.10.2026 – Smart Mode und benutzerdefinierte Ladeleistung:** Die beiden
  gegenseitigen Sperren entfallen. Zwischen Langsam-/Schon-/Schnellladung und
  kundenspezifischer Ladeleistung kann gewechselt werden, ohne die gespeicherte
  Smart-Mode-Einstellung zu ändern. Smart Mode kann auch bei kundenspezifischer
  Ladeleistung eingeschaltet werden, sofern die übrigen Prüfungen erfüllt sind.
  Laut Betreiberbeobachtung ignoriert der Server Smart Mode in diesem Lademodus.
  Dieses Verhalten ist nicht unabhängig für alle Firmwarestände bestätigt.
  Der Schalter zeigt das gespeicherte Flag, nicht eine bestätigte Wirksamkeit.
- Bei **Kundenspezifischer Ladeleistung** (Modus 4) ist die OBC-Phasenwahl
  auch bei gespeichertem Smart Mode frei. In Modi 1–3 bleibt die Sperre für
  1-/2-phasige Auswahl bei eingeschaltetem Smart Mode bestehen.
  Die Prüfungen für Zeitsteuerung, 3-phasige OBC-Sollwahl beim Einschalten
  von Smart Mode und gültige Lademodi bleiben bestehen.
  Ein Regressionstest prüft den Wechsel in
  beide Richtungen und die unveränderten übrigen Konfigurationswerte.
- **10.10.2026 – Ladestrom als Slider:** Die Entität
  `number.alphaess_wallbox_ladestrom_kundenspezifisch` verwendet standardmäßig
  einen Slider von **6 bis 16 A in 1-A-Schritten** statt eines Zahlenfelds.
  Die tatsächliche Entitäts-ID kann je nach Home-Assistant-Einrichtung abweichen.
- Hausstrom-Einstellung und Zeitfenster-Ströme bleiben Zahlenfelder.
  Der globale Ladestrom-Slider ist in allen Lademodi bedienbar.
  Änderungen schreiben nur den Sollwert und wechseln den Lademodus nicht.
  Verbindungsfehler und Portal-Ablehnungen werden weiterhin angezeigt.
  Grenzen von 6–16 A und die Modusprüfung der Zeitfenster-Ströme bleiben bestehen.
- Individuelle Dashboard-Karten können die Darstellung selbst bestimmen.
  Der Slider ändert nur den Standard-Eingabemodus der Entität, nicht die
  Bedeutung des Portal-Sollwerts oder die Reaktionszeit der Wallbox.
- Ein Regressionstest prüft den Slider-Modus, die Grenzen und Schrittweite
  sowie die unveränderten Eingabemodi der anderen Zahlenfelder.
  Mit den bisherigen Änderungen bestehen insgesamt **77 automatisierte Tests**;
  eine Prüfung der Darstellung im eigenen Home Assistant steht noch aus.

Ab **0.7.9** können in den Integrationsoptionen Sensoren für PV-Leistung,
Hausakku-SOC, Hauslast, Netzfluss und Batterieleistung ausgewählt werden.
Der Wallbox-Leistungssensor ist bereits in der Integration enthalten. Die
Auswahl speichert die Entity-IDs, implementiert aber noch keine automatische
Aufzeichnung oder PV-Laderegelung.

Die Fork-Version **0.7.9** wird als GitHub-Release **`v0.7.9`** für HACS
bereitgestellt. Sie ergänzt die Auswahl der lokalen Überwachungssensoren in
den Integrationsoptionen.
Die Änderungshistorie steht im [Changelog](CHANGELOG.md).

**Bis v0.7.3** war die globale Ladestrom-Eingabe auf Modus 4 beschränkt.
Seit v0.7.4 ist der Slider in allen Lademodi verfügbar. Eine Ladestromänderung
schreibt weiterhin nur den Sollwert und wechselt den Lademodus nicht.

### Letzte Einstellungsänderung (ab 0.7.0)

**Ab v0.7.2:** Der Sensor verwendet zustandsabhängige Symbole:
Informationskreis (kein Auftrag), Cloud-Upload (Senden), Sanduhr (API angenommen),
Häkchen (Portal bestätigt), Uhr mit Warnzeichen (noch nicht bestätigt),
Fragezeichen (Übermittlung unklar), Kreuz (abgelehnt) und unterbrochene Cloud
(nicht übermittelt). Statustext und Bedeutung bleiben erhalten.
Manuelle Symbolvorgaben in Home Assistant oder einer Dashboard-Karte können
die automatische Symbolwahl überschreiben. Farben werden nicht vorgegeben.

Der zusätzliche Diagnose-Sensor **Letzte Einstellungsänderung** zeigt den
letzten lokalen Auftrag für Einstellungen oder Zeitfenster. Er wird bereits
beim Senden aktualisiert, unabhängig vom normalen Polling.

**Ab 0.7.5:** Der zusätzliche Sensor **Letzte angeforderte Änderung** zeigt
die lesbare Zusammenfassung der zuletzt angeforderten Einstellungen, zum
Beispiel `Ladestrom: 10 A` oder `Lademodus: Benutzerdefinierte Ladeleistung`.
Bei Zeitfenster-Schreibvorgängen wird auch die Zeitrahmennummer angezeigt.
Der Sensor beschreibt den Auftrag und behauptet keine Übernahme; dafür bleibt
der API-/Portalstatussensor zuständig.

| Zustand | Bedeutung |
|---|---|
| Noch keine Änderung | Seit dem Laden der Integration kein Auftrag gestartet. |
| Wird gesendet | Konfiguration wird gelesen oder der Schreibvorgang läuft. |
| API angenommen – Bestätigung ausstehend | HTTP 200/201/204 erhalten; Werte noch nicht zurückgelesen. |
| Im Portal bestätigt | Alle angeforderten Werte entsprechen der gelesenen Portal-Konfiguration. |
| Noch nicht im Portal bestätigt | Erfolgreiche Rücklesung, aber nicht alle Werte stimmen überein. |
| Abgelehnt | Schreibvorgang ausdrücklich abgelehnt, etwa mit HTTP 400/401/403. |
| Nicht übermittelt | Lokale Validierung, Anmeldung oder vorbereitende Abfrage fehlgeschlagen; kein PATCH gesendet. |
| Übermittlung unklar | Schreibvorgang ohne sichere Bestätigung, etwa Timeout, Abbruch oder HTTP 5xx. |

Attribute enthalten die angeforderten Portal-Felder (einschließlich automatisch
gesetzter OBC-Sollwahl), Zeitpunkte für Senden/API-Annahme/Portal-Bestätigung,
HTTP-Status und gegebenenfalls einen Fehler oder Rücklesefehler.
**Ab v0.7.3:** Numerisch gleiche Ganz- und Dezimalzahlen
(z. B. `10` und `10.0`) bestätigen denselben Sollwert. Boolesche Werte
und Zahlen als Text werden nicht in Zahlen umgewandelt; es gibt keine
Rundungstoleranz. Nicht endliche Zahlen bestätigen keinen Sollwert.
`Rückgelesen` zeigt für jedes angeforderte Feld den Wert, Datentyp und
ob es vorhanden war. `Abweichende Felder` nennt die noch nicht passenden
Feldpfade. Zusammen mit `Angefordert` lassen sich Wert- und Typabweichungen
unterscheiden. Fehlende Felder, null und unerwartete Objektwerte werden
unterschieden, ohne ganze Objekte oder Gerätekonfigurationen offenzulegen.
Zeitpunkte enthalten eine UTC-Zeitzonenangabe. Zeitfenster werden in den
Feldpfaden mit API-Indizes **0/1/2** für Zeitrahmen **1/2/3** bezeichnet.
Bereits passende Werte werden ohne PATCH als im Portal bestätigt angezeigt,
mit einem entsprechenden Hinweis und ohne behauptete HTTP-Annahme.

Die vorhandene Rücklesung nach drei Sekunden und das normale Polling prüfen
nur die angeforderten Felder. Fehlende oder abweichende Werte bestätigen den
Auftrag nicht. Rücklesefehler löschen eine vorherige API-Annahme nicht.
Eine ältere Abfrage kann keinen neueren Auftrag bestätigen. Es gibt keine
automatische Wiederholung von Schreibbefehlen und keine feste Frist, nach
der eine fehlende Bestätigung als Ablehnung gilt.

**Die Anzeige bestätigt keine physische Umsetzung an der Wallbox.** Insbesondere
nach einem Timeout kann ein später passend gelesener Wert die Portal-Einstellung
bestätigen, ohne nachzuweisen, welcher Client ihn geändert hat.
START/STOP und reine App-/Portal-Änderungen werden nicht als eigene Aufträge
erfasst. Der Sensor bleibt bei Pollingfehlern sichtbar; sein Status wird bei
Neustart oder Neuladen der Integration zurückgesetzt. Es werden keine
Zugangsdaten, Tokens oder vollständigen Gerätekonfigurationen im Sensor abgelegt.

## Übernommene Projektbeschreibung

> **Beta 0.5.7**  
> Entwickelt u.a. für die Community von **https://www.storion4you.de/**  
> G2T-Erweiterung für **AlphaESS SMILE-G3-EVCT11/S**: **Kavino**  

Diese Home-Assistant-Custom-Integration bindet AlphaESS-Wallboxen über das AlphaESS-Kundenportal an Home Assistant an. 
G1T-Unterstützung und ergänzend eine neuere G2T-Konfiguration der SMILE-G3-EVCT11/S (Kavino).

Dies ist ein Community-Projekt und keine offizielle AlphaESS-Integration. Die G2T-Funktionen und die G1T-Hardwarekompatibilität wurden praktisch getestet; einzelne Sonderfälle benötigen weitere Rückmeldungen.

## Unterstützter Stand

### G2T

- automatische Erkennung des Portal-Profils `g2T`
- Live-Status und Ladeleistung
- Fahrzeug angeschlossen und Ladestecker verriegelt als Ja/Nein
- Ladeeinstellung: **Manuell / Zeitgesteuertes Aufladen / Plug and Play**
- Lademodus: **Langsamladung / Schonladung / Schnellladung / Benutzerdefinierte Ladeleistung**
- kundenspezifischer Ladestrom **6–16 A**
- OBC-Phasenwahl **1 / 2 / 3**
- Smart Mode mit Schutzprüfungen
- drei Zeitrahmen mit Aktivierung, Start, Ende, Lademodus und Maximalstrom
- **Zeitfenster:** Die Weboberfläche bietet nur das **15-Minuten-Raster**,
  die AlphaESS-App nach Tester-Rückmeldung minutengenaue Eingabe.
  Die Integration liest bereits gespeicherte `HH:MM`-Werte ohne Rundung,
  erlaubt beim Schreiben über die Portal-API vorsichtshalber weiterhin
  nur Viertelstunden bis ein minutengenauer API-Schreibtest erfolgreich ist
- Hausstrom-Einstellung **25–1000 A**
- Installateursteuerung und Kabel-Selbstverriegelung
- Hardware-, Software-, Modell- und Profildiagnose
- Energie- und Ladeberichtswerte

Der Diagnose-Sensor **Portal-Profil** zeigt das erkannte Profil und das dazugehörige Bild `g1t.png` oder `g2t.png`.

### G1T

Die bestehende G1T-Erkennung und -Konfiguration bleibt erhalten. Die G2T-spezifischen Schutzregeln greifen nicht in den G1T-Pfad ein.

## Hinweise aus dem Testerfeedback

- **Unterschied Webportal / App:** Die App kann Zeiten minutengenau
  eintragen, während die Weboberfläche nur Viertelstunden anbietet.
  Daraus lässt sich nicht sicher ableiten, ob der für diese Integration
  genutzte PATCH-Endpunkt beliebige Minuten annimmt. Daher werden
  minutengenaue App-Werte weiterhin unverändert angezeigt und beim
  Ändern anderer Felder nicht bewusst gerundet; neue Zeitänderungen
  bleiben bis zum gesonderten API-Test im 15-Minuten-Raster.
- **Zeitfenster und Plug and Play:** Der im Portal gespeicherte Zeitplan
  bleibt beim Wechsel zwischen Manuell, Zeitgesteuertem Aufladen und Plug and
  Play erhalten. Die Entitäten unterscheiden jetzt zwischen
  **deaktiviertem Zeitfenster**, **im Zeitplan aktiviertem Zeitfenster** und
  **gespeichert, aber nicht ausgewählt**. Die gespeicherten Uhrzeiten bleiben
  auch bei `isEnable: false` sichtbar. Die tatsächliche Wirksamkeit muss
  weiterhin an der Wallbox geprüft werden. Die Integration schaltet beim
  Wechsel zu Plug and Play **keine** Zeitrahmen ungefragt aus.
- **API-Sollwert und tatsächlicher Ladestrom:** Die Entität
  `Ladestrom (kundenspezifisch)` meldet den im Portal gespeicherten Sollwert,
  keine physisch bestätigte Umsetzung. Die Ladereaktion kann verzögert sein;
  für den tatsächlichen Betrieb die Live-Leistung und ggf. ein externes
  Messgerät beobachten.
- **Änderungen aus App/Portal:** Sie werden durch die normalen
  Integrationsabfragen erkannt. Die zusätzliche 3-Sekunden-Rücklesung nach
  einem **von Home Assistant gesendeten** Schreibbefehl gilt nicht für
  Änderungen, die ausschließlich aus der AlphaESS-App kommen.

### Häufige Fragen zum Testerfeedback

**Woran erkenne ich deaktivierte Zeitfenster?** Die Entität
`Zeitrahmen N Aktiv` zeigt den gespeicherten Portal-Schalter `isEnable`.
Das Statusattribut **Zeitfenster-Status** unterscheidet ausdrücklich zwischen
deaktiviert, im Zeitplan aktiviert und lediglich gespeichert. Wenn die
Portal-Antwort keinen verlässlichen Aktivierungswert enthält, steht dort
`Unbekannt`. Alte Uhrzeiten allein beweisen keine aktive Zeitsteuerung.

**Warum werden Änderungen aus der App nicht sofort in Home Assistant sichtbar?**
Änderungen direkt in der App werden durch das normale Polling eingelesen
(G2T standardmäßig 30 s; in den Optionen einstellbar). Cloud-Verzögerungen
sind zusätzlich möglich. Die 3-Sekunden-Rücklesung wird nur bei einem
**Home-Assistant-Schreibbefehl** ausgelöst und bestätigt keinen physisch
abgeschlossenen Ladevorgang.

**Was geschieht bei Cloud- oder Internetausfall?** Diese Integration verwendet
die AlphaESS-Portal-API, keinen lokalen Steuerkanal. Sie kann bei Ausfall
der Cloud **nicht** verlässlich von Manuell zu Plug and Play wechseln und
keine lokale Abschaltsicherheit oder SoC-Abschaltung garantieren. Eine
Stromunterbrechung ist kein dokumentierter Reset auf Plug and Play.
Für sicherheitskritische Ladebedingungen ist eine unabhängige, entsprechend
geprüfte Lösung erforderlich.

**Wie installiere ich Updates?** Über HACS das benutzerdefinierte Repository
hinzufügen und veröffentlichte Releases aktualisieren; nach einem Update
Home Assistant neu starten. Bei manueller Installation nur den
Integrationsordner `custom_components/alphaess_portal_bridge/` kopieren,
nicht das gesamte Git-Repository. Das aktuell ausgewählte Release kann
von neuesten Änderungen auf `main` abweichen.

**Installateursteuerung und Kabelverriegelung:** Die verfügbaren
Konfigurationsfelder werden aus dem Portal übernommen. Der genaue Umfang
der Installateursteuerung ist nicht vollständig dokumentiert.
`gunLineSelfLockEnable` bezeichnet die Selbstverriegelungs-Einstellung
**an der Wallbox**; eine automatische Verriegelung im Fahrzeug ist damit
nicht bestätigt.

## G2T-Schutzlogik

### Laden starten und stoppen

**Laden starten** und **Laden stoppen** sind bei G2T ausschließlich mit der Ladeeinstellung **Manuell** verfügbar. Das wurde mit angeschlossenem Fahrzeug unter Last bestätigt. Bei **Zeitgesteuertem Aufladen** und **Plug and Play** deaktiviert die Integration die Schaltflächen und blockiert direkte Start-/Stopp-Aufrufe zusätzlich in der API-Schicht.

Die Beta sendet absichtlich **keinen automatischen zweiten STOP-Befehl**. In einem Test musste STOP einmal erneut gesendet werden; die Ursache ist noch nicht reproduzierbar geklärt.

### Smart Mode

Smart Mode wird nur für G2T angeboten. Beim Aktivieren prüft die Integration:

- Zeitgesteuertes Aufladen darf nicht aktiv sein.
- Die OBC-Phasenwahl muss auf **3-phasig** stehen.
- Ein gültiger Lademodus muss ausgewählt sein; im Fork ist auch
  **Benutzerdefinierte Ladeleistung** zulässig.

Der Fork lässt das Smart-Mode-Flag beim Wechsel des Lademodus unverändert.
Laut Betreiberbeobachtung wird Smart Mode bei kundenspezifischer Ladeleistung
serverseitig ignoriert. Ein eingeschalteter Schalter bestätigt daher keine
aktive Smart-Mode-Regelung in diesem Modus. Ob der Server das Flag beim Wechsel
erhält und beim Rückwechsel wieder berücksichtigt, ist an der eigenen Wallbox
zu prüfen; die Integration erzwingt dies nicht.

Ein Wechsel auf Zeitgesteuertes Aufladen bei aktivem Smart Mode wird blockiert.
Vor einem manuellen Wechsel auf 1- oder 2-phasig muss Smart Mode in Lademodi
1–3 deaktiviert werden. In Modus 4 ist diese Phasenwahl auch bei eingeschaltetem
Smart Mode zulässig; das Flag und der Lademodus bleiben dabei unverändert.
Die Ausnahme bestätigt keine physische Umsetzung durch die Wallbox.

Beim Rückwechsel von Modus 4 zu Modus 1–3 mit eingeschaltetem Smart Mode
setzt die Integration die OBC-Sollwahl automatisch auf 3-phasig.
Modus und Phasenwahl werden gemeinsam in einem Portal-Schreibvorgang gesendet;
das Smart-Mode-Flag bleibt erhalten. Bei ausgeschaltetem Smart Mode oder
gleichzeitigem Ausschalten bleibt die bisherige Phasenwahl unverändert.
Die Rücklesung bestätigt nur die Portal-Konfiguration, keine physische Umschaltung.

## Bekannte Einschränkungen und offene Prüfungen

1. **Smart-Mode-Phasenautomatik:** Smart Mode wurde erfolgreich aktiviert. Die automatische 1↔3-Phasenumschaltung bei geeignetem PV-Überschuss ist noch nicht abschließend live bestätigt.
2. **OBC „2-phasig“:** AlphaESS-App und Portal speichern den Wert. Bei einem Test mit einem Peugeot e-208 wurde trotz der Auswahl „2-phasig“ extern auf allen drei Phasen Leistung gemessen. Die Entität zeigt deshalb eine **Sollwahl**, nicht die tatsächlich stromführenden Phasen.
3. **`chargingAmount`:** Wird wie in der AlphaESS-App als **„In dieser Sitzung geladen“** angezeigt. Der Wert blieb im Test nach erneutem Anstecken erhalten; seine genaue Definition und sein Reset-Zeitpunkt sind offen.
4. **`lastChargingAmount`:** Wird als **„Letzter Ladeabschnitt“** angezeigt. Der Wert kann zeitweise `null` sein und erhält keinen künstlichen Fallback.
5. **„Heute laut Ladebericht“:** Summe abgeschlossener Berichtseinträge des aktuellen Tages. Der Wert war in einem Test während einer Live-Ladung noch 0,00 kWh und ist daher vorerst als experimentell zu betrachten.

Besonders erwünscht sind Tests mit weiteren G2T-Fahrzeugmodellen und Firmwareständen, eine G1T-Regressionsprüfung, die Smart-Mode-Phasenautomatik, zweiphasig ladenden Fahrzeugen sowie das Resetverhalten von `chargingAmount` und die Plausibilität des Tagesberichts.

Bei unerwartetem Verhalten zuerst die AlphaESS-App oder das Portal prüfen. Die Wallbox nicht durch schnelle wiederholte Schreibbefehle belasten.

## Polling

- Wallbox- und Konfigurationsdaten: Eingabefeld **5–300 Sekunden** in **1-Sekunden-Schritten**
- Standard: **G1T 120 Sekunden**, **G2T 30 Sekunden**
- Energiebericht: gecacht und höchstens etwa alle **5 Minuten** neu abgefragt
- Sehr kurze Intervalle erhöhen die Anzahl der Cloud-Abfragen deutlich und
  können vom Portal gedrosselt werden. Die Integration garantiert keine
  bestimmte Antwortzeit oder erfolgreiche Abfrage bei 5-Sekunden-Polling.
  Das 5-Sekunden-Intervall ist eine Nutzeroption, nicht die empfohlene
  Standardeinstellung.

Kurze Übergangszustände der Wallbox können zwischen zwei Abfragen liegen und in Home Assistant unsichtbar bleiben.

## Installation über HACS

1. HACS öffnen und **Integrationen → ⋮ → Benutzerdefinierte Repositories** wählen.
2. `https://github.com/Rasenkardinal/SMILE-EVCT11-FORK` als Repository mit Typ **Integration** hinzufügen.
3. Die **AlphaESS Wallbox Bridge** aus diesem Fork installieren, beim Herunterladen das Release **`v0.7.1`** (oder ein neueres Fork-Release) auswählen und anschließend Home Assistant neu starten.
4. Eine bereits eingerichtete Integration nicht löschen. Zugangsdaten und Wallbox-Seriennummer bleiben im vorhandenen Config Entry erhalten.
5. Auf der Geräteseite unter Diagnose prüfen, welches Portal-Profil (`g1T` oder `g2T`) erkannt wurde.

### Wechsel vom Original zum Fork

1. Zuerst ein Home-Assistant-Backup erstellen.
2. Die ursprüngliche Repository-Installation **nur in HACS** entfernen.
   HACS kann dabei die Integrationsdateien löschen.
3. **Noch nicht neu starten:** Den Fork wie oben beschrieben hinzufügen und
   herunterladen, sodass die Integrationsdateien wieder vorhanden sind.
4. Erst danach Home Assistant neu starten.
5. Bestehende Entitäten und Automatisierungen sowie den Ladestrom-Slider prüfen.

Die eingerichtete Integration unter **Einstellungen → Geräte & Dienste**
**nicht löschen**. Sie enthält die bestehende Einrichtung und soll vom Fork
weiterverwendet werden. Künftige Updates nur über das Fork-Repository beziehen,
damit Updates des Originals die eigenen Änderungen nicht überschreiben.
Für neue Änderungen auf `main` bei Bedarf in HACS **Erneut herunterladen**
verwenden und anschließend Home Assistant neu starten.

## Manuelle Installation

1. Den bestehenden Ordner `config/custom_components/alphaess_portal_bridge` sichern.
2. Den Ordner `custom_components/alphaess_portal_bridge` aus diesem Repository nach `config/custom_components/` kopieren und vorhandene Dateien ersetzen.
3. Home Assistant vollständig neu starten.
4. Eine bereits eingerichtete Integration nicht löschen. Zugangsdaten und Wallbox-Seriennummer bleiben im vorhandenen Config Entry erhalten.

Bei einer Neuinstallation die Integration über **Einstellungen → Geräte & Dienste → Integration hinzufügen** einrichten.

## G2T-Portal-Zuordnungen

| Portal-Feld | Bedeutung |
|---|---|
| `chargeStrategy` | `0` Manuell, `1` Zeitgesteuert, `2` Plug and Play |
| `chargeMode` | `1` Langsam, `2` Schon, `3` Schnell, `4` Kundenspezifisch |
| `chargeCurrent` | kundenspezifischer Ladestrom, 6–16 A |
| `obcPhase` | OBC-Sollwahl 1 / 2 / 3 |
| `smartMode` | Smart Mode |
| `timePeriods` | bis zu drei Zeitrahmen |
| `houseHoldCurrent` | Hausstrom-Einstellung |
| `allowInstallersControl` | Installateursteuerung erlaubt |
| `gunLineSelfLockEnable` | Kabel-Selbstverriegelung |

## Projekt-Herkunft und Attribution

Dieser Fork baut auf dem Originalprojekt von **wfa001** auf. Die nachfolgend
beschriebene G2T-Unterstützung stammt aus dem übernommenen Projekt und ist keine
Neuentwicklung dieses Forks. Die ursprünglichen Beiträge und die
[MIT-Lizenz](LICENSE) bleiben erhalten.

Die Unterstützung der **AlphaESS SMILE-G3-EVCT11/S (G2T)** wurde durch **Kavino** aus der Storion4you-Community initiiert, anhand realer Portal- und Wallbox-Daten ermittelt und praktisch getestet. Dazu gehören insbesondere die G2T-Zuordnungen und die Home-Assistant-Unterstützung für Ladestrategie, Lademodus, Ladestrom, OBC-Phasenwahl, Smart Mode, Zeitfenster, Live-Status und Energiebericht.

## Beta-Feedback

Für einen Fehlerbericht helfen besonders:

- Home-Assistant-Version
- Wallbox-Modell sowie Hardware- und Software-Version
- erkanntes Portal-Profil `g1T` oder `g2T`
- Fahrzeugmodell, wenn der Fehler während einer Ladung auftritt
- Ausgangseinstellung und ausgeführte Aktion
- Status und Leistung vor und nach der Aktion
- relevante Home-Assistant-Logs

Zugangsdaten, Tokens und persönliche Daten aus Logs entfernen. Seriennummern für öffentliche Beiträge ebenfalls schwärzen.

Änderungen früherer Entwicklungsstände stehen im `CHANGELOG.md`.
