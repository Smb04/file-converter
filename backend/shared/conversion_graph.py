"""Directed weighted conversion graph and Dijkstra shortest-path router."""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Literal

from backend.shared.formats import FORMAT_SPECS, normalize_format

WorkerType = Literal["media", "docs"]


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    engine: str
    worker: WorkerType
    cost_quality: int
    cost_time: int
    preserves_alpha: bool = True
    preserves_multipage: bool = False

    @property
    def weight(self) -> int:
        return self.cost_quality * 10 + self.cost_time


def _build_edges() -> list[Edge]:
    edges: list[Edge] = []

    # 1. Raster images via libvips (plus SVG via resvg, PSD/RAW via ImageMagick/libraw)
    vips_out = ["png", "jpg", "webp", "avif", "heic", "jxl", "tiff", "bmp", "gif"]
    vips_in = ["png", "jpg", "webp", "avif", "heic", "jxl", "tiff", "bmp", "gif", "ico"]
    for src in vips_in:
        for dst in vips_out:
            if src == dst:
                continue
            lossy_penalty = 5 if dst in {"jpg", "gif"} else (2 if dst in {"webp", "avif", "heic"} else 0)
            alpha = dst in {"png", "webp", "avif", "heic", "jxl", "tiff", "gif"}
            edges.append(Edge(src, dst, "libvips", "media", cost_quality=1 + lossy_penalty, cost_time=2, preserves_alpha=alpha))

    # Special image inputs -> png (entry into raster graph)
    edges.append(Edge("svg", "png", "resvg", "media", cost_quality=1, cost_time=2, preserves_alpha=True))
    edges.append(Edge("svg", "ico", "svg_to_ico", "media", cost_quality=2, cost_time=3, preserves_alpha=True))
    edges.append(Edge("psd", "png", "imagemagick", "media", cost_quality=1, cost_time=3, preserves_alpha=True))
    edges.append(Edge("raw", "png", "libraw", "media", cost_quality=1, cost_time=5, preserves_alpha=False))
    edges.append(Edge("raw", "jpg", "libraw", "media", cost_quality=3, cost_time=4, preserves_alpha=False))

    # Raster -> Multi-size ICO & Lossless PDF wrap
    for src in ["png", "jpg", "webp", "bmp", "tiff"]:
        edges.append(Edge(src, "ico", "pillow_ico", "media", cost_quality=2, cost_time=2, preserves_alpha=True))
    for src in ["png", "jpg", "tiff"]:
        edges.append(Edge(src, "pdf", "img2pdf", "media", cost_quality=0, cost_time=1, preserves_alpha=False, preserves_multipage=True))

    # 2. Audio <-> Audio via FFmpeg
    audio_formats = ["mp3", "wav", "flac", "m4a", "ogg", "opus", "aiff", "alac"]
    audio_in_only = ["wma"]
    for src in audio_formats + audio_in_only:
        for dst in audio_formats:
            if src == dst or (src == "alac"):
                continue
            lossless = dst in {"wav", "flac", "aiff", "alac"}
            edges.append(Edge(src, dst, "ffmpeg_audio", "media", cost_quality=0 if lossless else 3, cost_time=3))

    # 3. Video <-> Video & Video -> Audio / GIF via FFmpeg
    video_in = ["mp4", "mkv", "webm", "mov", "avi", "wmv", "flv"]
    video_out = ["mp4", "mkv", "webm", "mov", "avi"]
    for src in video_in:
        for dst in video_out:
            if src == dst:
                continue
            edges.append(Edge(src, dst, "ffmpeg_video", "media", cost_quality=4, cost_time=12))
        edges.append(Edge(src, "gif", "ffmpeg_gif", "media", cost_quality=12, cost_time=10))
        # Direct Video -> Audio extraction (WAV lossless pivot or direct target)
        for aud in ["mp3", "wav", "flac", "m4a", "ogg", "opus"]:
            edges.append(Edge(src, aud, "ffmpeg_extract_audio", "media", cost_quality=0 if aud in {"wav", "flac"} else 3, cost_time=4))

    # Animated GIF -> Video
    for dst in ["mp4", "webm"]:
        edges.append(Edge("gif", dst, "ffmpeg_video", "media", cost_quality=4, cost_time=6))

    # 4. Documents, PDF & Office
    office_text = ["docx", "doc", "odt", "rtf", "txt"]
    for src in office_text:
        edges.append(Edge(src, "pdf", "libreoffice", "docs", cost_quality=1, cost_time=6, preserves_multipage=True))
        for dst in ["docx", "odt", "rtf", "txt", "html"]:
            if src != dst:
                edges.append(Edge(src, dst, "libreoffice", "docs", cost_quality=2, cost_time=5, preserves_multipage=True))

    for src in ["pptx", "odp", "ods"]:
        edges.append(Edge(src, "pdf", "libreoffice", "docs", cost_quality=1, cost_time=6, preserves_multipage=True))
    edges.append(Edge("ods", "xlsx", "libreoffice", "docs", cost_quality=1, cost_time=4))
    edges.append(Edge("ods", "csv", "libreoffice", "docs", cost_quality=2, cost_time=4))

    # Markup & E-Books via Pandoc
    for src in ["md", "html", "epub"]:
        for dst in ["pdf", "docx", "odt", "html", "md", "txt", "epub"]:
            if src == dst:
                continue
            engine = "libreoffice" if (src == "html" and dst == "pdf") else "pandoc"
            edges.append(Edge(src, dst, engine, "docs", cost_quality=1, cost_time=4, preserves_multipage=True))
    edges.append(Edge("docx", "md", "pandoc", "docs", cost_quality=2, cost_time=3))
    edges.append(Edge("docx", "epub", "pandoc", "docs", cost_quality=2, cost_time=4))

    # PDF -> Raster images (1-to-N pages) & PDF optimization/text
    for dst in ["png", "jpg", "tiff"]:
        edges.append(Edge("pdf", dst, "poppler_pdftoppm", "docs", cost_quality=2, cost_time=6, preserves_multipage=True))
    edges.append(Edge("pdf", "txt", "poppler_pdftotext", "docs", cost_quality=3, cost_time=2))
    edges.append(Edge("pdf", "pdf", "ghostscript_compress", "docs", cost_quality=2, cost_time=4, preserves_multipage=True))

    # 5. Structured Data <-> Spreadsheets (fast pure-Python)
    data_formats = ["json", "yaml", "xml", "csv", "xlsx"]
    for src in data_formats:
        for dst in data_formats:
            if src == dst:
                continue
            edges.append(Edge(src, dst, "data_converter", "docs", cost_quality=0, cost_time=1))
    edges.append(Edge("xlsx", "pdf", "libreoffice", "docs", cost_quality=1, cost_time=5, preserves_multipage=True))

    return edges


EDGES: list[Edge] = _build_edges()
ADJACENCY: dict[str, list[Edge]] = {}
for _edge in EDGES:
    ADJACENCY.setdefault(_edge.src, []).append(_edge)


def find_conversion_path(src_format: str, dst_format: str) -> list[Edge]:
    """Return shortest-cost list of Edges converting src_format -> dst_format via Dijkstra."""
    src = normalize_format(src_format)
    dst = normalize_format(dst_format)

    if src not in FORMAT_SPECS or dst not in FORMAT_SPECS:
        raise ValueError(f"Unsupported format pair: {src} -> {dst}")

    # Allow explicit PDF compression (pdf -> pdf)
    if src == dst:
        for e in ADJACENCY.get(src, []):
            if e.dst == dst:
                return [e]
        raise ValueError(f"Identical source and target format: {src}")

    heap: list[tuple[int, int, str, list[Edge]]] = [(0, 0, src, [])]
    best_cost: dict[str, int] = {src: 0}
    counter = 0

    while heap:
        cost, _, node, path = heapq.heappop(heap)
        if node == dst and path:
            return path
        if cost > best_cost.get(node, 10**9):
            continue
        for edge in ADJACENCY.get(node, []):
            if edge.dst == edge.src:
                continue
            # Avoid absurd cycles or excessive hops
            if len(path) >= 3:
                continue
            new_cost = cost + edge.weight
            if new_cost < best_cost.get(edge.dst, 10**9):
                best_cost[edge.dst] = new_cost
                counter += 1
                heapq.heappush(heap, (new_cost, counter, edge.dst, [*path, edge]))

    raise ValueError(f"No conversion path available for {src} -> {dst}")


def get_valid_targets(src_format: str) -> list[str]:
    """Return all reachable target formats for src_format using BFS."""
    src = normalize_format(src_format)
    if src not in FORMAT_SPECS:
        return []
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(src, 0)]
    targets: set[str] = set()

    while queue:
        node, depth = queue.pop(0)
        if depth >= 3:
            continue
        for edge in ADJACENCY.get(node, []):
            if edge.dst == src and src == "pdf":
                targets.add("pdf")
                continue
            if edge.dst == src:
                continue
            targets.add(edge.dst)
            if edge.dst not in visited:
                visited.add(edge.dst)
                queue.append((edge.dst, depth + 1))

    order = list(FORMAT_SPECS.keys())
    return sorted(targets, key=lambda f: order.index(f) if f in order else 999)


def export_capabilities(settings_dict: dict[str, object] | None = None) -> dict[str, object]:
    """Export format catalog and conversion matrix for GET /api/v1/capabilities."""
    formats = [
        {
            "id": spec.id,
            "label": spec.label,
            "category": spec.category,
            "extensions": list(spec.extensions),
            "mime_types": list(spec.mime_types),
            "can_input": spec.can_input,
            "can_output": spec.can_output,
            "default_target": spec.default_target,
            "hint": spec.hint,
        }
        for spec in FORMAT_SPECS.values()
    ]
    matrix = {
        fmt_id: get_valid_targets(fmt_id)
        for fmt_id, spec in FORMAT_SPECS.items()
        if spec.can_input
    }
    return {
        "formats": formats,
        "matrix": matrix,
        "limits": settings_dict or {},
    }
