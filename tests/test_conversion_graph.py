import pytest

from backend.shared.conversion_graph import (
    export_capabilities,
    find_conversion_path,
    get_valid_targets,
)


def test_direct_paths():
    path = find_conversion_path("png", "webp")
    assert len(path) == 1
    assert path[0].engine == "libvips"
    assert path[0].worker == "media"

    path_audio = find_conversion_path("mp4", "mp3")
    assert len(path_audio) == 1
    assert path_audio[0].engine == "ffmpeg_extract_audio"

    path_data = find_conversion_path("json", "yaml")
    assert len(path_data) == 1
    assert path_data[0].engine == "data_converter"
    assert path_data[0].worker == "docs"


def test_multi_hop_pipelines():
    # HEIC -> PNG -> PDF
    heic_pdf = find_conversion_path("heic", "pdf")
    assert len(heic_pdf) == 2
    assert [e.dst for e in heic_pdf] == ["png", "pdf"]

    # DOCX -> PDF -> PNG
    docx_png = find_conversion_path("docx", "png")
    assert len(docx_png) == 2
    assert [e.dst for e in docx_png] == ["pdf", "png"]

    # SVG -> ICO
    svg_ico = find_conversion_path("svg", "ico")
    assert svg_ico[-1].dst == "ico"

    # MOV -> FLAC (direct extract or WAV->FLAC)
    mov_flac = find_conversion_path("mov", "flac")
    assert mov_flac[-1].dst == "flac"


def test_invalid_conversion_raises():
    with pytest.raises(ValueError):
        find_conversion_path("mp3", "png")
    with pytest.raises(ValueError):
        find_conversion_path("png", "png")


def test_pdf_compression_allowed():
    path = find_conversion_path("pdf", "pdf")
    assert len(path) == 1
    assert path[0].engine == "ghostscript_compress"


def test_capabilities_export():
    caps = export_capabilities({"max_file_bytes": 100})
    assert "formats" in caps
    assert "matrix" in caps
    assert "webp" in get_valid_targets("png")
    assert "pdf" in caps["matrix"]["docx"]
