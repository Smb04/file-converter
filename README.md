# FileConverter — Ephemerer Online-Dateikonverter für Portainer & ZimaOS

Ein selbstgehosteter, datensparsamer Universal-Dateikonverter ohne Benutzerkonten und ohne dauerhafte Datenspeicherung (*Zero-Persistence*). Entwickelt für den Betrieb in **Portainer auf ZimaOS** und ausgerichtet an **DIN EN ISO 9241 (Teile 11, 110, 171)** sowie den **Apple Human Interface Guidelines (HIG)**.

## Kernfunktionen

- **Alle gängigen Formate:**
  - **Bilder:** PNG, JPG, WebP, AVIF, HEIC/HEIF, JXL, TIFF, BMP, GIF, ICO, SVG, PSD, Kamera-RAW (`CR2`, `NEF`, `ARW`, `DNG`, `ORF`)
  - **Audio:** MP3, WAV, FLAC, AAC/M4A, OGG, OPUS, AIFF, ALAC, WMA
  - **Video (+ Audio-Extraktion):** MP4, MKV, WebM, MOV, AVI, WMV, FLV, animiertes GIF
  - **Dokumente & PDF:** PDF (Komprimierung, Seiten-zu-Bild-ZIP, Bilder-zu-PDF-Merge), DOCX, DOC, ODT, RTF, TXT, Markdown, HTML, EPUB, PPTX, ODP, ODS
  - **Strukturierte Daten:** JSON, YAML, XML, CSV, XLSX
- **Drag & Drop + Multi-File-Batch:** Vollflächige Drag-Dropzone, Zwischenablage (`Strg/Cmd+V`), Chunked Uploads (5-MB-Chaps kompatibel mit Cloudflare Tunnel & Proxies), Echtzeit-SSE-Fortschritt und Streaming-ZIP-Download (`zipstream-ng`).
- **Ephemer by Design:** Verarbeitung im RAM (`tmpfs`), konfigurierbare TTL (Standard: 20 Min.), High-Watermark-Schutz (80 % / 90 %), optionales Auto-Delete nach Download und Sofort-Lösch-Button.
- **Security First:** Worker laufen ohne Internetzugang (`internal: true`), Non-Root (`1000:1000`), Read-Only-Root-Filesystem, gehärtete ImageMagick `policy.xml` und Magic-Byte-Validierung.

## Dokumentation

- **Architektur & Design-Spezifikation:** [Plan.md](Plan.md)
- **Portainer auf ZimaOS & DuckDNS-Anbindung am VPS:** [DEPLOY_ZIMAOS_DUCKDNS.md](DEPLOY_ZIMAOS_DUCKDNS.md)

## Lokaler Test (Backend)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/api/requirements.txt PyYAML openpyxl lxml
PYTHONPATH=. pytest -v
```
