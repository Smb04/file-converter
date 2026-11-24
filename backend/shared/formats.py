"""Canonical format registry, MIME types, smart defaults, and UI hints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Category = Literal["image", "audio", "video", "document", "data"]


@dataclass(frozen=True)
class FormatSpec:
    id: str
    label: str
    category: Category
    extensions: tuple[str, ...]
    mime_types: tuple[str, ...]
    can_input: bool = True
    can_output: bool = True
    default_target: str = ""
    hint: str = ""
    already_compressed: bool = False


FORMAT_SPECS: dict[str, FormatSpec] = {
    # --- Images ---
    "png": FormatSpec("png", "PNG", "image", ("png",), ("image/png",), default_target="webp", hint="Verlustfrei mit Transparenz", already_compressed=True),
    "jpg": FormatSpec("jpg", "JPG", "image", ("jpg", "jpeg"), ("image/jpeg",), default_target="webp", hint="Universell fuer Fotos", already_compressed=True),
    "webp": FormatSpec("webp", "WebP", "image", ("webp",), ("image/webp",), default_target="png", hint="Ideal fuers Web (klein)", already_compressed=True),
    "avif": FormatSpec("avif", "AVIF", "image", ("avif",), ("image/avif",), default_target="jpg", hint="Moderne Kompression", already_compressed=True),
    "heic": FormatSpec("heic", "HEIC", "image", ("heic", "heif"), ("image/heic", "image/heif"), default_target="jpg", hint="Apple-Fotoformat", already_compressed=True),
    "jxl": FormatSpec("jxl", "JPEG XL", "image", ("jxl",), ("image/jxl",), default_target="png", hint="Next-Gen Bildformat", already_compressed=True),
    "tiff": FormatSpec("tiff", "TIFF", "image", ("tif", "tiff"), ("image/tiff",), default_target="png", hint="Druck & Archiv"),
    "bmp": FormatSpec("bmp", "BMP", "image", ("bmp",), ("image/bmp",), default_target="png", hint="Unkomprimiertes Bitmap"),
    "gif": FormatSpec("gif", "GIF", "image", ("gif",), ("image/gif",), default_target="webp", hint="Animationen & Grafiken", already_compressed=True),
    "ico": FormatSpec("ico", "ICO", "image", ("ico",), ("image/x-icon", "image/vnd.microsoft.icon"), default_target="png", hint="App- & Favicon (Multi-Size)"),
    "svg": FormatSpec("svg", "SVG", "image", ("svg",), ("image/svg+xml",), can_output=False, default_target="png", hint="Skalierbare Vektorgrafik"),
    "psd": FormatSpec("psd", "PSD", "image", ("psd",), ("image/vnd.adobe.photoshop",), can_output=False, default_target="png", hint="Photoshop-Dokument"),
    "raw": FormatSpec("raw", "Kamera RAW", "image", ("cr2", "nef", "arw", "dng", "orf"), ("image/x-dcraw",), can_output=False, default_target="jpg", hint="Unbearbeitete Sensordaten"),

    # --- Audio ---
    "mp3": FormatSpec("mp3", "MP3", "audio", ("mp3",), ("audio/mpeg",), default_target="m4a", hint="Universelles Audioformat", already_compressed=True),
    "wav": FormatSpec("wav", "WAV", "audio", ("wav",), ("audio/wav", "audio/x-wav"), default_target="mp3", hint="Unkomprimiertes PCM"),
    "flac": FormatSpec("flac", "FLAC", "audio", ("flac",), ("audio/flac",), default_target="mp3", hint="Verlustfrei komprimiert", already_compressed=True),
    "m4a": FormatSpec("m4a", "AAC / M4A", "audio", ("m4a", "aac"), ("audio/mp4", "audio/aac"), default_target="mp3", hint="Effizient (Apple/Web)", already_compressed=True),
    "ogg": FormatSpec("ogg", "OGG Vorbis", "audio", ("ogg",), ("audio/ogg",), default_target="mp3", hint="Offenes Audioformat", already_compressed=True),
    "opus": FormatSpec("opus", "OPUS", "audio", ("opus",), ("audio/opus",), default_target="mp3", hint="Sehr effizient fuer Sprache", already_compressed=True),
    "aiff": FormatSpec("aiff", "AIFF", "audio", ("aiff", "aif"), ("audio/aiff",), default_target="flac", hint="Apple PCM-Audio"),
    "alac": FormatSpec("alac", "ALAC", "audio", ("alac",), ("audio/mp4",), can_input=False, default_target="flac", hint="Apple Lossless", already_compressed=True),
    "wma": FormatSpec("wma", "WMA", "audio", ("wma",), ("audio/x-ms-wma",), can_output=False, default_target="mp3", hint="Windows Media Audio", already_compressed=True),

    # --- Video ---
    "mp4": FormatSpec("mp4", "MP4", "video", ("mp4", "m4v"), ("video/mp4",), default_target="webm", hint="Universell (H.264/H.265)", already_compressed=True),
    "mkv": FormatSpec("mkv", "MKV", "video", ("mkv",), ("video/x-matroska",), default_target="mp4", hint="Flexibler Container", already_compressed=True),
    "webm": FormatSpec("webm", "WebM", "video", ("webm",), ("video/webm",), default_target="mp4", hint="Web-Video (VP9/AV1)", already_compressed=True),
    "mov": FormatSpec("mov", "MOV", "video", ("mov",), ("video/quicktime",), default_target="mp4", hint="Apple QuickTime", already_compressed=True),
    "avi": FormatSpec("avi", "AVI", "video", ("avi",), ("video/x-msvideo",), default_target="mp4", hint="Klassischer Container"),
    "wmv": FormatSpec("wmv", "WMV", "video", ("wmv",), ("video/x-ms-wmv",), can_output=False, default_target="mp4", hint="Windows Media Video", already_compressed=True),
    "flv": FormatSpec("flv", "FLV", "video", ("flv",), ("video/x-flv",), can_output=False, default_target="mp4", hint="Flash Video", already_compressed=True),

    # --- Documents & Markup ---
    "pdf": FormatSpec("pdf", "PDF", "document", ("pdf",), ("application/pdf",), default_target="png", hint="Portables Dokument", already_compressed=True),
    "docx": FormatSpec("docx", "DOCX", "document", ("docx",), ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",), default_target="pdf", hint="Microsoft Word", already_compressed=True),
    "doc": FormatSpec("doc", "DOC", "document", ("doc",), ("application/msword",), can_output=False, default_target="pdf", hint="Aelteres Word-Format"),
    "odt": FormatSpec("odt", "ODT", "document", ("odt",), ("application/vnd.oasis.opendocument.text",), default_target="pdf", hint="OpenDocument Text", already_compressed=True),
    "rtf": FormatSpec("rtf", "RTF", "document", ("rtf",), ("application/rtf", "text/rtf"), default_target="pdf", hint="Rich Text Format"),
    "txt": FormatSpec("txt", "TXT", "document", ("txt",), ("text/plain",), default_target="pdf", hint="Reiner Text"),
    "md": FormatSpec("md", "Markdown", "document", ("md", "markdown"), ("text/markdown",), default_target="pdf", hint="Formatierter Klartext"),
    "html": FormatSpec("html", "HTML", "document", ("html", "htm"), ("text/html",), default_target="pdf", hint="Web-Dokument"),
    "epub": FormatSpec("epub", "EPUB", "document", ("epub",), ("application/epub+zip",), default_target="pdf", hint="E-Book Standard", already_compressed=True),
    "pptx": FormatSpec("pptx", "PPTX", "document", ("pptx",), ("application/vnd.openxmlformats-officedocument.presentationml.presentation",), can_output=False, default_target="pdf", hint="PowerPoint-Praesentation", already_compressed=True),
    "odp": FormatSpec("odp", "ODP", "document", ("odp",), ("application/vnd.oasis.opendocument.presentation",), can_output=False, default_target="pdf", hint="OpenDocument Praesentation", already_compressed=True),
    "ods": FormatSpec("ods", "ODS", "document", ("ods",), ("application/vnd.oasis.opendocument.spreadsheet",), default_target="xlsx", hint="OpenDocument Tabelle", already_compressed=True),

    # --- Structured Data & Spreadsheets ---
    "xlsx": FormatSpec("xlsx", "XLSX", "data", ("xlsx",), ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",), default_target="csv", hint="Excel-Arbeitsmappe", already_compressed=True),
    "csv": FormatSpec("csv", "CSV", "data", ("csv",), ("text/csv",), default_target="xlsx", hint="Tabellen-Trennwerte"),
    "json": FormatSpec("json", "JSON", "data", ("json",), ("application/json",), default_target="yaml", hint="Strukturierte Daten"),
    "yaml": FormatSpec("yaml", "YAML", "data", ("yaml", "yml"), ("application/yaml", "text/yaml"), default_target="json", hint="Lesbare Konfiguration"),
    "xml": FormatSpec("xml", "XML", "data", ("xml",), ("application/xml", "text/xml"), default_target="json", hint="Strukturiertes Markup"),
}

EXTENSION_TO_FORMAT: dict[str, str] = {
    ext: spec.id
    for spec in FORMAT_SPECS.values()
    for ext in spec.extensions
}

ALREADY_COMPRESSED_FORMATS: frozenset[str] = frozenset(
    fmt_id for fmt_id, spec in FORMAT_SPECS.items() if spec.already_compressed
)


def normalize_format(fmt: str) -> str:
    cleaned = fmt.strip().lower().lstrip(".")
    return EXTENSION_TO_FORMAT.get(cleaned, cleaned)
