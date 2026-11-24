"""Magic-byte file detection independent of untrusted file extensions."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

try:
    import magic as _libmagic  # type: ignore
except ImportError:  # pragma: no cover - pure-python fallback covers test env
    _libmagic = None

from backend.shared.formats import EXTENSION_TO_FORMAT, normalize_format


_OOXML_AND_ODF_MAP = {
    "word/": "docx",
    "xl/": "xlsx",
    "ppt/": "pptx",
}

_ODF_MIME_MAP = {
    "application/vnd.oasis.opendocument.text": "odt",
    "application/vnd.oasis.opendocument.spreadsheet": "ods",
    "application/vnd.oasis.opendocument.presentation": "odp",
    "application/epub+zip": "epub",
}


def _inspect_zip(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            if "mimetype" in names:
                mime = zf.read("mimetype").decode("utf-8", errors="ignore").strip()
                if mime in _ODF_MIME_MAP:
                    return _ODF_MIME_MAP[mime]
            for prefix, fmt in _OOXML_AND_ODF_MAP.items():
                if any(name.startswith(prefix) for name in names):
                    return fmt
    except (zipfile.BadZipFile, OSError):
        return None
    return None


def _inspect_text(head: bytes, original_filename: str) -> str | None:
    try:
        text = head.decode("utf-8-sig").strip()
    except UnicodeDecodeError:
        return None
    if not text:
        return None

    low = text.lower()
    if "<svg" in low[:512]:
        return "svg"
    if low.startswith("<!doctype html") or "<html" in low[:512]:
        return "html"
    if text.startswith("<?xml") or (text.startswith("<") and ">" in text[:256] and "</" in text):
        return "xml"

    if text[0] in ("{", "["):
        try:
            json.loads(text)
            return "json"
        except json.JSONDecodeError:
            pass

    ext = Path(original_filename).suffix.lower().lstrip(".")
    if ext in {"yaml", "yml"}:
        return "yaml"
    if ext == "csv":
        return "csv"
    if ext in {"md", "markdown"}:
        return "md"
    if ext == "json":
        return "json"
    if ext in {"html", "htm"}:
        return "html"
    if ext == "svg":
        return "svg"
    if ext == "xml":
        return "xml"

    # Heuristic YAML/CSV detection when extension is missing or misleading
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if len(lines) >= 2 and all("," in ln for ln in lines[:3]):
        counts = {ln.count(",") for ln in lines[:3]}
        if len(counts) == 1 and next(iter(counts)) >= 1:
            return "csv"
    if lines and ":" in lines[0] and not lines[0].startswith("{"):
        if ext != "txt":
            return "yaml"

    return "txt"


def detect_format(path: Path, original_filename: str = "") -> str:
    """Detect canonical format from magic bytes, falling back to safe inspection."""
    with path.open("rb") as fh:
        head = fh.read(8192)

    if not head:
        raise ValueError("Empty file cannot be identified")

    # 1. Exact binary signatures
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "gif"
    if head.startswith(b"BM"):
        return "bmp"
    if head.startswith((b"II*\x00", b"MM\x00*")):
        ext = Path(original_filename).suffix.lower().lstrip(".")
        if ext in {"cr2", "nef", "arw", "dng", "orf"}:
            return "raw"
        return "tiff"
    if head.startswith(b"\x00\x00\x01\x00"):
        return "ico"
    if head.startswith(b"8BPS"):
        return "psd"
    if head.startswith((b"\xff\x0a", b"\x00\x00\x00\x0cJXL ")):
        return "jxl"
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"{\\rtf"):
        return "rtf"
    if head.startswith(b"fLaC"):
        return "flac"
    if head.startswith(b"OggS"):
        if b"OpusHead" in head[:128]:
            return "opus"
        return "ogg"
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        # Distinguish ADTS AAC vs MP3 frame sync when extension hints AAC
        ext = Path(original_filename).suffix.lower().lstrip(".")
        if ext == "aac":
            return "m4a"
        return "mp3"
    if head.startswith(b"RIFF") and len(head) >= 12:
        chunk_type = head[8:12]
        if chunk_type == b"WEBP":
            return "webp"
        if chunk_type == b"WAVE":
            return "wav"
        if chunk_type == b"AVI ":
            return "avi"
    if head.startswith(b"FORM") and len(head) >= 12 and head[8:12] in (b"AIFF", b"AIFC"):
        return "aiff"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        if b"webm" in head[:256].lower():
            return "webm"
        return "mkv"
    if head.startswith(b"\x30\x26\xb2\x75\x8e\x66\xcf\x11"):
        ext = Path(original_filename).suffix.lower().lstrip(".")
        return "wma" if ext == "wma" else "wmv"
    if head.startswith(b"FLV\x01"):
        return "flv"
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "doc"

    # 2. ISO Base Media File Format (ftyp box: HEIC, AVIF, MP4, M4A, MOV)
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12].decode("ascii", errors="ignore").lower()
        compat = head[8:64].lower()
        if brand in {"heic", "heix", "hevc", "hevx", "mif1", "msf1"} or b"heic" in compat:
            return "heic"
        if brand in {"avif", "avis"} or b"avif" in compat:
            return "avif"
        if brand == "qt  ":
            return "mov"
        if brand in {"m4a ", "m4b "}:
            return "m4a"
        return "mp4"

    # 3. ZIP containers (DOCX, XLSX, PPTX, ODT, ODS, ODP, EPUB)
    if head.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        zip_fmt = _inspect_zip(path)
        if zip_fmt:
            return zip_fmt

    # 4. libmagic if available for additional binary formats
    if _libmagic is not None:
        try:
            mime = _libmagic.from_file(str(path), mime=True)
            if mime == "image/svg+xml":
                return "svg"
            if mime == "application/pdf":
                return "pdf"
        except Exception:
            pass

    # 5. Text-based formats (SVG, HTML, XML, JSON, YAML, CSV, MD, TXT)
    text_fmt = _inspect_text(head, original_filename)
    if text_fmt:
        return text_fmt

    ext = Path(original_filename).suffix.lower().lstrip(".")
    if ext in EXTENSION_TO_FORMAT:
        return normalize_format(ext)

    raise ValueError("Unsupported or unrecognized file format")
