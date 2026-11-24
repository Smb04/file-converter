import zipfile
from pathlib import Path

from backend.shared.magic_detect import detect_format


def test_png_disguised_as_jpg(tmp_path: Path):
    p = tmp_path / "fake.jpg"
    p.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    assert detect_format(p, "fake.jpg") == "png"


def test_pdf_detection(tmp_path: Path):
    p = tmp_path / "document.bin"
    p.write_bytes(b"%PDF-1.7\n%...")
    assert detect_format(p, "document.bin") == "pdf"


def test_docx_zip_container_detection(tmp_path: Path):
    p = tmp_path / "report.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", "<w:document/>")
    assert detect_format(p, "report.zip") == "docx"


def test_json_and_svg_detection(tmp_path: Path):
    j = tmp_path / "payload.txt"
    j.write_text('{"hello": "world"}', encoding="utf-8")
    assert detect_format(j, "payload.txt") == "json"

    s = tmp_path / "icon.txt"
    s.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>', encoding="utf-8")
    assert detect_format(s, "icon.txt") == "svg"
