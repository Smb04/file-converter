export type Category = "image" | "audio" | "video" | "document" | "data";

export type ThemePreference = "auto" | "light" | "dark";

export interface FormatSpec {
  id: string;
  label: string;
  category: Category;
  extensions: string[];
  mime_types: string[];
  can_input: boolean;
  can_output: boolean;
  default_target: string;
  hint: string;
}

export interface CapabilitiesResponse {
  formats: FormatSpec[];
  matrix: Record<string, string[]>;
  limits: {
    max_file_bytes: number;
    max_batch_bytes: number;
    ttl_seconds: number;
    chunk_size_default: number;
    hw_accel_enabled: boolean;
  };
}

export interface ConversionOptions {
  quality: number;
  max_width: number | null;
  max_height: number | null;
  dpi: number;
  strip_metadata: boolean;
  background_color: string;
  audio_bitrate: string;
  sample_rate: number | null;
  channels: number | null;
  normalize_audio: boolean;
  video_preset: "small" | "balanced" | "high";
  video_resolution: "original" | "1080p" | "720p" | "480p";
  video_codec: "auto" | "h264" | "h265" | "vp9" | "av1";
  mute_audio: boolean;
  use_hw_accel: boolean;
  page_range: string | null;
  pdf_quality: "screen" | "ebook" | "prepress";
}

export const DEFAULT_OPTIONS: ConversionOptions = {
  quality: 85,
  max_width: null,
  max_height: null,
  dpi: 150,
  strip_metadata: false,
  background_color: "#FFFFFF",
  audio_bitrate: "192k",
  sample_rate: null,
  channels: null,
  normalize_audio: false,
  video_preset: "balanced",
  video_resolution: "original",
  video_codec: "auto",
  mute_audio: false,
  use_hw_accel: true,
  page_range: null,
  pdf_quality: "ebook",
};

export type ItemStage =
  | "uploading"
  | "ready"
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface BatchFileItem {
  localId: string;
  file: File;
  filename: string;
  size: number;
  uploadProgress: number;
  fileId?: string;
  detectedFormat?: string;
  category?: Category;
  validTargets: string[];
  targetFormat: string;
  options: ConversionOptions;
  stage: ItemStage;
  jobId?: string;
  jobProgress: number;
  phase: string;
  outputFilename?: string;
  outputSize?: number;
  isArchive?: boolean;
  pageCount?: number | null;
  errorMessage?: string;
}

export interface BatchSession {
  batch_id: string;
  batch_token: string;
  expires_at: number;
  ttl_seconds: number;
}
