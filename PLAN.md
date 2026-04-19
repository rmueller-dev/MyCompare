# MyCompare — Feature-Gap zu Litera Compare

## Legende
- **Haben wir** = bereits implementiert
- **Fehlt** = noch nicht implementiert
- Priorität: P1 (Kern-Feature), P2 (wichtig), P3 (nice-to-have)

---

## PRIORITÄT 1 — Kern-Features die fehlen

### 1. Cross-Format-Vergleich (Word vs PDF, Word vs RTF)
- **Status:** Fehlt
- **Was:** Zwei verschiedene Dateitypen vergleichen (z.B. DOCX gegen PDF)
- **Aufwand:** Mittel — beide Formate zu Plaintext extrahieren, dann diff
- **Dateien:** `extractors.py`, `routes.py`, `App.js` (UI für Format-Auswahl)

### 2. Accept/Reject Workflow im Word Redline
- **Status:** Fehlt
- **Was:** Im Browser Änderungen einzeln oder per Batch akzeptieren/ablehnen, daraus ein neues "Clean" Dokument generieren
- **Aufwand:** Hoch — Frontend mit Checkbox pro Änderung, Backend zum selektiven Anwenden
- **Dateien:** Neuer Endpoint `/apply-changes`, neues Frontend-Component `AcceptReject.js`

### 3. Formatierungsänderungen erkennen und anzeigen
- **Status:** Teilweise (Extraktion ja, Diff nur bei DOCX strukturell)
- **Was:** Font-Wechsel, Schriftgröße, Farbe, Absatzformatierung explizit als "Formatierungsänderung" anzeigen (nicht nur Textänderung)
- **Aufwand:** Mittel — diff_engine erweitern für Format-Only-Changes im Redline
- **Dateien:** `diff_engine.py`, `routes.py` (_generate_docx_redline), Frontend

### 4. Bildvergleich (Pixel-Level)
- **Status:** Fehlt
- **Was:** Eingebettete Bilder in DOCX/PPTX extrahieren und pixelweise vergleichen
- **Aufwand:** Mittel — Pillow/PIL für Bildextraktion und Diff, Overlay-Darstellung
- **Dateien:** `extractors.py`, neues Modul `image_diff.py`, `routes.py`

### 5. Tabellenvergleich in Word (nicht nur Excel)
- **Status:** Teilweise (Tabellen-Text wird extrahiert, aber kein struktureller Tabellenvergleich)
- **Was:** Tabellen Zelle-für-Zelle vergleichen innerhalb von DOCX, mit farbiger Markierung
- **Aufwand:** Mittel — Tabellen-XML parsen, zellenweisen Diff machen
- **Dateien:** `extractors.py`, `diff_engine.py`, `routes.py`

### 6. OCR für gescannte PDFs
- **Status:** Fehlt
- **Was:** Bild-basierte PDFs per OCR in Text umwandeln, dann vergleichen
- **Aufwand:** Mittel — Tesseract/pytesseract Integration
- **Dateien:** `extractors.py` (extract_pdf), `requirements.txt`

---

## PRIORITÄT 2 — Wichtige Features

### 7. 1:Many Vergleich (ein Original gegen mehrere Versionen)
- **Status:** Fehlt
- **Was:** Bis zu 5 modifizierte Versionen gegen ein Original vergleichen, Änderungen zusammenführen
- **Aufwand:** Hoch — Multi-Diff-Logik, Merge-Konflikt-Handling, neue UI
- **Dateien:** `diff_engine.py`, `routes.py`, neues Frontend-Component `MultiCompare.js`

### 8. Rendering Sets / Vergleichsprofile
- **Status:** Teilweise (ColorConfig mit Presets)
- **Was:** Vollständige Profile speichern/laden mit allen Einstellungen (Farben, Schrifteffekte, was ignoriert wird, Zeichenebene an/aus)
- **Aufwand:** Mittel — Settings-Modell in DB, CRUD-Endpoints, UI
- **Dateien:** `models.py`, `routes.py`, neues Frontend-Component `RenderingSets.js`

### 9. Zeichenebene-Vergleich (Character-Level Diff)
- **Status:** Fehlt (aktuell nur Wort-Ebene)
- **Was:** Einzelne Buchstabenänderungen erkennen, mit Optionen: AN, AUS, AN-Zahlen-ignorieren
- **Aufwand:** Niedrig — difflib auf Zeichenebene statt Wortebene
- **Dateien:** `routes.py` (_generate_docx_redline), `diff_engine.py`

### 10. Vertikale Änderungsbalken (Change Bars)
- **Status:** Fehlt
- **Was:** Vertikale Linien am Seitenrand neben geänderten Absätzen (wie in Word "Markup: einfach")
- **Aufwand:** Niedrig — OOXML `w:pPr/w:pBdr` mit linkem Rand-Balken
- **Dateien:** `routes.py` (_generate_docx_redline)

### 11. PDF/A Export
- **Status:** Fehlt (nur PDF)
- **Was:** Redline als PDF/A (Langzeitarchivierung) exportieren
- **Aufwand:** Niedrig — reportlab kann PDF/A
- **Dateien:** `routes.py`

### 12. Nur geänderte Seiten drucken/exportieren
- **Status:** Teilweise (Export gibt es, aber nicht seitengenau)
- **Was:** Nur die Seiten exportieren/drucken, die tatsächlich Änderungen enthalten
- **Aufwand:** Mittel — Seitenumbrüche erkennen, selektiv exportieren
- **Dateien:** `routes.py`, Frontend

### 13. Email-Integration (Outlook/SMTP)
- **Status:** Fehlt
- **Was:** Redline per Email versenden direkt aus der App, optional als ZIP
- **Aufwand:** Mittel — SMTP-Integration, UI für Email-Versand
- **Dateien:** Neues Modul `email_sender.py`, `routes.py`, Frontend

### 14. Embedded Objects vergleichen (Excel in Word, Visio, etc.)
- **Status:** Fehlt
- **Was:** Eingebettete Excel-Tabellen, Visio-Diagramme etc. in DOCX erkennen und vergleichen
- **Aufwand:** Hoch — OLE-Objekte extrahieren, format-spezifisch parsen
- **Dateien:** `extractors.py`, `routes.py`

### 15. HTML-Datei-Unterstützung
- **Status:** Fehlt
- **Was:** HTML-Dateien als Eingabe für Vergleich
- **Aufwand:** Niedrig — BeautifulSoup für Text-Extraktion
- **Dateien:** `extractors.py`, `routes.py` (Dateityp-Liste erweitern)

### 16. .MSG (Outlook Email) Unterstützung
- **Status:** Fehlt
- **Was:** Outlook-Emails (.msg) als Dokumente vergleichen
- **Aufwand:** Mittel — python-msg oder extract-msg Library
- **Dateien:** `extractors.py`, `requirements.txt`

---

## PRIORITÄT 3 — Nice-to-have / Erweitert

### 17. Bulk-Vergleich (mehrere Dokumentenpaare)
- **Status:** Fehlt
- **Was:** Mehrere Dokumentenpaare auf einmal hochladen und vergleichen, Ergebnisse als Batch
- **Aufwand:** Mittel — Queue-basierte Verarbeitung, Batch-UI
- **Dateien:** `routes.py`, neues Frontend-Component `BulkCompare.js`

### 18. Clipboard-Vergleich (Browser-Zwischenablage)
- **Status:** Teilweise (Snippet Compare existiert)
- **Was:** Direkt aus der Zwischenablage (Ctrl+V) vergleichen ohne manuelles Einfügen
- **Aufwand:** Niedrig — JavaScript Clipboard API im Frontend
- **Dateien:** `SnippetCompare.js`

### 19. REST API / Server-Modus
- **Status:** Fehlt (nur Web-UI)
- **Was:** Dokumentierte REST API für externe Integration, API-Keys, Rate Limiting
- **Aufwand:** Mittel — API-Doku, Auth, OpenAPI/Swagger Spec
- **Dateien:** `routes.py`, neues Modul `api_auth.py`, Swagger YAML

### 20. AI-Zusammenfassung der Änderungen
- **Status:** Fehlt
- **Was:** KI-basierte Zusammenfassung ("Die wesentlichen Änderungen betreffen §3 Haftung und §7 Laufzeit..."), Risikoanalyse
- **Aufwand:** Mittel — Claude API Integration
- **Dateien:** Neues Modul `ai_summary.py`, `routes.py`, Frontend

### 21. Admin Panel / Benutzerverwaltung
- **Status:** Fehlt (Single-User lokal)
- **Was:** Multi-User mit Login, Rollen, zentrale Einstellungen, Audit-Log
- **Aufwand:** Hoch — Auth-System, User-Modell, RBAC
- **Dateien:** `models.py`, neues Modul `auth.py`, Frontend

### 22. DMS-Integration (iManage, NetDocuments, SharePoint)
- **Status:** Fehlt
- **Was:** Direkt aus DMS Dokumente öffnen/vergleichen/zurückspeichern
- **Aufwand:** Sehr hoch — Pro DMS eine eigene API-Integration
- **Dateien:** Neues Modul pro DMS

### 23. .DOC (Legacy Word) Unterstützung
- **Status:** Fehlt (nur .docx)
- **Was:** Alte .doc-Dateien (binäres Format) unterstützen
- **Aufwand:** Mittel — antiword oder LibreOffice-Konvertierung
- **Dateien:** `extractors.py`

### 24. PowerPoint Bild/Shape-Vergleich
- **Status:** Fehlt (nur Text in PPTX)
- **Was:** Shapes, Positionen, Bilder in Folien vergleichen
- **Aufwand:** Hoch — Shape-XML parsen, Positions-Diff
- **Dateien:** `extractors.py`, `diff_engine.py`

### 25. Chart-Vergleich (Diagramme)
- **Status:** Fehlt
- **Was:** Diagramme in DOCX/XLSX/PPTX erkennen und Datenpunkte vergleichen
- **Aufwand:** Hoch — Chart-XML parsen, Datenreihen-Diff
- **Dateien:** `extractors.py`

### 26. Automatisches Inhaltsverzeichnis im Redline
- **Status:** Fehlt
- **Was:** TOC automatisch aktualisieren/einfügen im Redline-Dokument
- **Aufwand:** Niedrig — Word TOC-Feld einfügen und als "dirty" markieren
- **Dateien:** `routes.py` (_generate_docx_redline)

### 27. Deckblatt (Cover Page) für Redline
- **Status:** Fehlt
- **Was:** Automatisch ein Deckblatt mit Metadaten (Dateinamen, Datum, Autor) einfügen
- **Aufwand:** Niedrig — python-docx Seite einfügen
- **Dateien:** `routes.py`

### 28. Passwortgeschützte Dokumente
- **Status:** Fehlt
- **Was:** Passwortgeschützte DOCX/XLSX/PDF öffnen können
- **Aufwand:** Mittel — msoffcrypto-tool für Office, PyPDF2 für PDF
- **Dateien:** `extractors.py`, `requirements.txt`

---

## Zusammenfassung

| Priorität | Anzahl | Highlights |
|-----------|--------|------------|
| P1 | 6 | Cross-Format, Accept/Reject, Bildvergleich, OCR, Tabellen-Diff, Formatierung |
| P2 | 10 | 1:Many, Rendering Sets, Char-Level, Change Bars, PDF/A, Email, HTML, MSG |
| P3 | 12 | Bulk, API, AI-Summary, Admin, DMS, Legacy .doc, Charts, Cover Page |
| **Gesamt** | **28** | |

## Was wir BEREITS haben (Vergleich zu Litera)

- Word/Excel/PPT/PDF/RTF/TXT Vergleich
- Tracked Changes (w:ins/w:del) im Word Redline
- Separater Änderungsbericht (Word) mit farbigem Markup
- Kommentare, Fußnoten, Endnoten Extraktion + Vergleich
- XE, TA, TC, TOC, REF und alle Feldtypen
- Move Detection (verschobener Text)
- Three-Pane View (Original | Redline | Modified)
- Change Navigation + Filter
- Color Config mit Presets
- Snippet Compare (Text-Vergleich)
- Vergleichsoptionen (Whitespace, Case, Headers ignorieren)
- PDF Redline mit Inline-Markup + Statistik
- Excel Redline (Litera-Style mit Summary, Legend, Kommentare)
- Metadaten-Bereinigung
- Bookmarks für Querverweise im Redline
- Gunicorn Production Server
