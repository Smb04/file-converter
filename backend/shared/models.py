"""Pydantic schemas shared across API, workers, and tests."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class ConversionOptions(BaseModel):
    # Image options
    quality: int = Field(default=85, ge=1, le=100)
    max_width: int | None = Field(default=None, ge=16, le=16000)
    max_height: int | None = Field(default=None, ge=16, le=16000)
    dpi: int = Field(default=150, ge=72, le=600)
    strip_metadata: bool = False
    background_color: str = "#FFFFFF"

    # Audio options
    audio_bitrate: str = "192k"
    sample_rate: int | None = Field(default=None, ge=8000, le=192000)
    channels: int | None = Field(default=None, ge=1, le=2)
    normalize_audio: bool = False

    # Video options
    video_preset: Literal["small", "balanced", "high"] = "balanced"
    video_resolution: Literal["original", "1080p", "720p", "480p"] = "original"
    video_codec: Literal["auto", "h264", "h265", "vp9", "av1"] = "auto"
    mute_audio: bool = False
    use_hw_accel: bool = True

    # Document / PDF options
    page_range: str | None = None
    pdf_quality: Literal["screen", "ebook", "prepress"] = "ebook"


class BatchCreateResponse(BaseModel):
    batch_id: str
    batch_token: str
    expires_at: float
    ttl_seconds: int


class UploadInitRequest(BaseModel):
    batch_id: str
    filename: str
    size: int = Field(ge=1)
    declared_mime: str = "application/octet-stream"
    chunk_size: int = Field(ge=1024, le=25 * 1024 * 1024)
    total_chunks: int = Field(ge=1, le=5000)


class UploadInitResponse(BaseModel):
    upload_id: str
    chunk_size: int
    total_chunks: int


class UploadCompleteResponse(BaseModel):
    file_id: str
    filename: str
    size: int
    detected_format: str
    category: str
    valid_targets: list[str]
    default_target: str


class ConvertItem(BaseModel):
    file_id: str
    target_format: str
    options: ConversionOptions = Field(default_factory=ConversionOptions)


class ConvertRequest(BaseModel):
    items: list[ConvertItem] = Field(default_factory=list)
    merge_mode: Literal["none", "images_to_pdf"] = "none"
    ordered_file_ids: list[str] = Field(default_factory=list)
    merge_options: ConversionOptions = Field(default_factory=ConversionOptions)


class JobSummary(BaseModel):
    job_id: str
    file_id: str | None = None
    source_format: str
    target_format: str
    status: JobStatus
    progress: int = 0
    phase: str = ""
    output_filename: str | None = None
    output_size: int | None = None
    is_archive: bool = False
    page_count: int | None = None
    error_message: str | None = None


class ConvertResponse(BaseModel):
    batch_id: str
    jobs: list[JobSummary]


class JobPayload(BaseModel):
    job_id: str
    batch_id: str
    file_ids: list[str]
    input_paths: list[str]
    original_filename: str
    source_format: str
    target_format: str
    pipeline: list[dict[str, Any]]
    step_index: int = 0
    current_input_path: str
    output_dir: str
    options: ConversionOptions = Field(default_factory=ConversionOptions)
    merge_mode: Literal["none", "images_to_pdf"] = "none"
