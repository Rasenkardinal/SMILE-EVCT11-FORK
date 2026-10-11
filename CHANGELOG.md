# Changelog

## Fork 0.7.4 – 2026-10-11

- Globalen Ladestrom-Slider in allen Lademodi freigeben. Die Modusprüfung
  bleibt für Zeitfenster-Ströme bestehen; globale Stromänderungen wechseln
  den Lademodus weiterhin nicht.
- Regressionstests für die Verfügbarkeit und Schreibbarkeit in allen Modi
  ergänzt.

## Fork 0.7.3 – 2026-10-10

- Portal-Rücklesung akzeptiert numerisch gleiche Ganz- und Dezimalzahlen,
  ohne boolesche Werte oder Zahlen als Text gleichzusetzen.
- Diagnoseattribute „Rückgelesen“ und „Abweichende Felder“ zeigen angeforderte
  Einzelwerte, Datentypen und fehlende Felder, ohne vollständige
  Gerätekonfigurationen zu veröffentlichen.
- Derselbe Zahlenvergleich beendet die vorläufige Modusfreigabe bei
  passender Portal-Rückmeldung. Regressionstests für Zahlen, Typabweichungen,
  fehlende Felder und Diagnosebereinigung ergänzt.
- Insgesamt 70 automatisierte Tests bestanden. Ob die Typabweichung bei der
  realen G3 die fehlende Bestätigung verursacht, ist noch zu prüfen.

## Fork 0.7.2 – 2026-10-10

- Ladestrom-Slider sofort nach erfolgreicher API-Annahme von Modus 4 freigeben,
  mit maximal 60 Sekunden Überbrückung bis zur Portal-Rückmeldung.
  API-Annahme eines anderen Modus sperrt ihn sofort; Fehler und Timeouts
  erzeugen keine neue Freigabe.
- Sofortige Ladestromänderungen bewahren den angenommenen Modus im PATCH,
  ohne die Überbrückungsfrist zu verlängern. Portalbestätigung bleibt getrennt.
- Ablauf aktualisiert die Entitäten ohne neue Schreibbefehle; Timer beim
  Entladen entfernen. Regressionstests für Freigabe, Ablauf, alte Antworten,
  Fehler, nachfolgende Stromänderungen und Listener ergänzt.
- Zustandsabhängige Symbole für „Letzte Einstellungsänderung“ ergänzt:
  Cloud-Upload, Sanduhr, Bestätigung, ausstehende Prüfung und Fehler unterscheiden.
  Statustexte und Schreiblogik bleiben unverändert.
- Regressionstest für alle acht Zustandssymbole und unbekannte Zustände ergänzt.
- Insgesamt 66 automatisierte Tests bestanden; reale Home-Assistant-/Wallbox-
  Prüfung steht noch aus.

## Fork 0.7.1 – 2026-10-10

- Globalen Ladestrom-Slider wieder nur in Modus 4 verfügbar machen.
  Direkte Schreibaufrufe über die Entität in anderen oder unbekannten Modi
  werden blockiert. Smart-Mode-, Phasen- und Zeitfensterlogik bleiben unverändert.
- Regressionstest für Freigabe in Modus 4 und Sperre in Modi 0–3 sowie bei
  unbekanntem Modus aktualisiert.

## Fork 0.7.0 – 2026-10-10

- Diagnose-Sensor „Letzte Einstellungsänderung“ für lokale Einstellungs- und
  Zeitfenster-Schreibvorgänge ergänzt. API-Annahme und passende Portal-Rücklesung
  werden getrennt angezeigt, ohne eine physische Umsetzung zu behaupten.
- Angeforderte Felder, automatische OBC-Anpassungen, Zeitpunkte, HTTP-Status,
  Fehler und Rücklesefehler als Attribute. Keine Speicherung von Zugangsdaten
  oder vollständigen Portal-Dokumenten.
- Abgelehnte, nicht gesendete und unklare Übermittlungen unterscheiden.
  No-op-Aufträge ohne erfundene API-Annahme bestätigen. Ältere Rücklesungen
  dürfen keinen neueren Auftrag bestätigen; keine automatischen Schreib-Retries.
- Sensor auch bei Pollingfehlern sichtbar; Status nur im Arbeitsspeicher,
  Callback beim Entladen entfernen.
- Insgesamt 55 automatisierte Tests bestanden, einschließlich echter
  Produktionsmethoden für HTTP-Ergebnisse, Rücklesung, Sensor und Abbruch.

## Fork 0.6.3 – 2026-10-10

- Beim G2T-Moduswechsel von 4 auf 1–3 mit eingeschaltetem Smart Mode die
  OBC-Sollwahl automatisch auf 3 setzen, gemeinsam mit dem Modus in einem PATCH.
  Smart-Mode-Flag und übrige Einstellungen bleiben erhalten.
- Bei ausgeschaltetem oder gleichzeitig ausgeschaltetem Smart Mode keine
  automatische Änderung der Phasenwahl.
- Regressionstests für alle Zielmodi und Ausgangsphasen sowie widersprüchliche
  explizite Phasenangaben ergänzt.
- Insgesamt 39 automatisierte Tests bestanden.

## Fork 0.6.2 – 2026-10-10

- OBC-Phasenwahl in Lademodus 4 auch bei gespeichertem Smart Mode freigegeben.
  Sperre für Modi 1–3 und 3-Phasen-Prüfung beim Einschalten von Smart Mode
  bleiben bestehen. Modus und Smart-Mode-Flag werden nicht automatisch geändert.
- Regressionstests prüfen alle Phasen in Modus 4 sowie die beibehaltenen
  Sperren in Modi 1–3 und bei fehlendem Modus.
- Insgesamt 35 automatisierte Tests bestanden.

## Fork 0.6.1 – 2026-10-10

- Globale Ladestromeingabe unabhängig vom Lademodus freigegeben:
  Modus-4-Verfügbarkeitsprüfung und Schreibsperre entfernt.
  Änderungen wechseln den Lademodus nicht. Verbindungsverfügbarkeit,
  Stromgrenzen und Zeitfenster-Ströme bleiben unverändert.
- Hinweis zur Annahme und Wirksamkeit des Sollwerts in anderen Modi ergänzt.
- Regressionstest für Verfügbarkeit und Schreiben in allen Lademodi sowie
  Nichtverfügbarkeit bei Verbindungsfehlern ergänzt; insgesamt 33 Tests bestanden.
- Manifest-Version auf 0.6.1 angehoben.
- Erstes eigenes GitHub-Release v0.6.1 für die Versionsauswahl in HACS.

## Fork 0.6.0 – 2026-10-10 (auf main, noch kein eigenes Release)

- Gegenseitige Sperren zwischen Smart Mode und kundenspezifischer Ladeleistung
  entfernt. Moduswechsel ändern das gespeicherte Smart-Mode-Flag nicht.
  Zeitsteuerungs-, Phasen- und Gültigkeitsprüfungen bleiben bestehen.
- Hinweis am Smart-Mode-Schalter ergänzt: Gespeicherter Portal-Zustand ist
  nicht mit tatsächlich wirksamer Regelung gleichzusetzen.
- Regressionstests für Moduswechsel, Smart-Mode-Aktivierung bei
  kundenspezifischer Ladeleistung und verbleibende Schutzprüfungen ergänzt.
- Kundenspezifischen Ladestrom standardmäßig als Slider von 6 bis 16 A
  in 1-A-Schritten darstellen. Die übrigen Zahlenfelder bleiben unverändert.
- Entitätskennungen, API-Steuerung und Schutzprüfungen bleiben unverändert.
- Regressionstest für den Slider, seine Grenzen und Schrittweite sowie die
  unveränderten Zahlenfelder ergänzt; mit den Smart-Mode-Tests insgesamt
  32 Tests bestanden.
- Zweck, Herkunft und Grenzen des persönlichen Forks in der README erläutert.
  HACS-Installation, Wechsel vom Original und Updates über main dokumentiert.
- Manifest-Version von 0.5.7 auf 0.6.0 angehoben, um den funktional
  erweiterten Fork-Stand zu kennzeichnen.

## Übernommener Stand – Noch nicht veröffentlicht – Testerfeedback

- Anzeige der gewählten Ladeeinstellung und der laut Portal-Modus ausgewählten
  Zeitfenster klargestellt. Gespeicherte Zeiträume bleiben unangetastet.
- Der benutzerdefinierte Ladestrom wird ausdrücklich als Portal-Sollwert
  und nicht als physisch bestätigter Istwert beschrieben.
- Deaktivierte, ausgewählte und lediglich gespeicherte Timer nun
  explizit anhand der Portal-Flags beschrieben; fehlende Aktivierungsflags
  werden als unbekannt ausgewiesen.
- G2T-Zeitfenster: Bereits gespeicherte Minuteneinstellungen aus der
  AlphaESS-App werden ohne Rundung angezeigt. Schreibvorgänge bleiben
  bis zu einem erfolgreichen API-Praxistest auf Viertelstunden begrenzt,
  entsprechend der Weboberfläche.
- Automatisierte Regressionstests für die Hinweise und minutengenaue
  Zeitvalidierung ergänzt.


## 0.5.7

- Ersetzt die Auswahl des Abfrageintervalls durch ein Zahlenfeld (30–300 Sekunden in 30-Sekunden-Schritten); die G1T-/G2T-Standardwerte bleiben 120 beziehungsweise 30 Sekunden.

## 0.5.6

- Behebt einen Fehler im Optionsfluss: Das ungültige Auswahlmodus-Enum `RADIO` wird durch `LIST` ersetzt.

## 0.5.5

- Stellt die Integration in die Standardstruktur `custom_components/alphaess_portal_bridge/` um.
- Ergänzt HACS- und Home-Assistant-Metadaten im Manifest.
- Richtet die Profilbild-Pfade an den kleingeschriebenen Dateinamen aus.

## 0.5.4

- Zeigt beim Portal-Profil-Sensor das passende G1T- oder G2T-Bild.
- Ergänzt englische Übersetzungen für Einrichtungs- und Optionsdialoge sowie den Profil-Sensor.

## 0.5.3

- Setzt das Standardintervall abhängig vom Portal-Profil: G1T 120 Sekunden, G2T 30 Sekunden.
- Zeigt das gespeicherte Intervall im Optionsdialog mit einer Radio-Auswahl zuverlässig an.

## 0.5.2

- Entwicklungsstand 0.5.2 als öffentliche Beta paketiert.
- START/STOP bei G2T auf Ladeeinstellung **Manuell** begrenzt – UI und API-Schutz.
- `WaitingForChargingPile` als **„Warten auf Antwort des E-Autos“** übersetzt.
- Smart-Mode-Schutz für Zeitsteuerung, OBC-Phasenwahl und Lademodus ergänzt.
- OBC-Auswahl 1/2/3 beibehalten; 2-phasig ausdrücklich als Sollwahl dokumentiert.
- `chargingAmount` als **„In dieser Sitzung geladen“** und `lastChargingAmount` als **„Letzter Ladeabschnitt“** getrennt geführt.
- separater Sensor **„Heute laut Ladebericht“**.
- unnötige `null`-Attribute im Status reduziert.
- Installateursteuerung und Kabel-Selbstverriegelung schreibbar.
- öffentliche Beta-Dokumentation und bekannte Einschränkungen ergänzt.

### 0.5.11
- Installateursteuerung und Kabel-Selbstverriegelung als schreibbare Schalter ergänzt und praktisch bestätigt.

### 0.5.9
- G2T-Schutz- und Validierungsfehler vereinheitlicht und auf Deutsch ausgegeben.

### 0.5.8
- Zeitrahmen auf das 15-Minuten-Raster des AlphaESS-Portals begrenzt.

### 0.5.7
- Hardware-Phasen als 1/2/3 dargestellt; nicht unterstützte Power-Share-Diagnosewerte ausgeblendet.

### 0.5.4–0.5.6
- Hausstrom-Einstellung schreibbar gemacht und G2T-Konfiguration weiter vervollständigt.

### 0.5.1–0.5.3
- grundlegende G2T-Erkennung, Status-, Lade-, OBC-, Zeitrahmen- und Energieentitäten aufgebaut.
