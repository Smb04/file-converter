import type {
  BatchSession,
  CapabilitiesResponse,
  ConversionOptions,
} from "../types";

export interface UploadCompleteResult {
  file_id: string;
  filename: string;
  size: number;
  detected_format: string;
  category: "image" | "audio" | "video" | "document" | "data";
  valid_targets: string[];
  default_target: string;
}

export async function fetchCapabilities(): Promise<CapabilitiesResponse> {
  const res = await fetch("/api/v1/capabilities");
  if (!res.ok) throw new Error("Unterstuetzte Formate konnten nicht geladen werden.");
  return res.json();
}

export async function createBatch(): Promise<BatchSession> {
  const res = await fetch("/api/v1/batches", { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Batch-Session konnte nicht erstellt werden.");
  }
  return res.json();
}

export async function uploadFileChunked(
  batch: BatchSession,
  file: File,
  chunkSize: number,
  onProgress: (pct: number) => void
): Promise<UploadCompleteResult> {
  const totalChunks = Math.max(1, Math.ceil(file.size / chunkSize));
  const initRes = await fetch("/api/v1/uploads/init", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Batch-Token": batch.batch_token,
    },
    body: JSON.stringify({
      batch_id: batch.batch_id,
      filename: file.name || "clipboard-file",
      size: file.size,
      declared_mime: file.type || "application/octet-stream",
      chunk_size: chunkSize,
      total_chunks: totalChunks,
    }),
  });
  if (!initRes.ok) {
    const body = await initRes.json().catch(() => ({}));
    throw new Error(body.detail || `Upload fehlgeschlagen (HTTP ${initRes.status}).`);
  }
  const { upload_id } = (await initRes.json()) as { upload_id: string };

  for (let index = 0; index < totalChunks; index++) {
    const start = index * chunkSize;
    const end = Math.min(file.size, start + chunkSize);
    const slice = file.slice(start, end);

    let uploaded = false;
    let lastError = "Chunk-Uebertragung fehlgeschlagen.";
    for (let attempt = 0; attempt < 3 && !uploaded; attempt++) {
      try {
        const chunkRes = await fetch(`/api/v1/uploads/${upload_id}/chunks/${index}`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/octet-stream",
            "X-Batch-Token": batch.batch_token,
          },
          body: slice,
        });
        if (chunkRes.ok) {
          uploaded = true;
        } else {
          lastError = `Chunk ${index + 1} abgelehnt (HTTP ${chunkRes.status}).`;
        }
      } catch {
        lastError = "Netzwerkunterbrechung waehrend des Uploads.";
      }
    }
    if (!uploaded) {
      throw new Error(lastError);
    }
    onProgress(Math.round(((index + 1) / totalChunks) * 100));
  }

  const completeRes = await fetch(`/api/v1/uploads/${upload_id}/complete`, {
    method: "POST",
    headers: { "X-Batch-Token": batch.batch_token },
  });
  if (!completeRes.ok) {
    const body = await completeRes.json().catch(() => ({}));
    throw new Error(body.detail || "Dateipruefung fehlgeschlagen.");
  }
  return completeRes.json();
}

export async function startConversion(
  batch: BatchSession,
  payload: {
    items: Array<{ file_id: string; target_format: string; options: ConversionOptions }>;
    merge_mode: "none" | "images_to_pdf";
    ordered_file_ids: string[];
    merge_options?: ConversionOptions;
  }
) {
  const res = await fetch(`/api/v1/batches/${batch.batch_id}/convert`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Batch-Token": batch.batch_token,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Konvertierung konnte nicht gestartet werden.");
  }
  return res.json() as Promise<{
    batch_id: string;
    jobs: Array<{ job_id: string; file_id: string | null; status: string; phase: string }>;
  }>;
}

export async function cancelJob(batch: BatchSession, jobId: string): Promise<void> {
  await fetch(`/api/v1/jobs/${jobId}/cancel`, {
    method: "POST",
    headers: { "X-Batch-Token": batch.batch_token },
  });
}

export async function purgeBatch(batch: BatchSession): Promise<void> {
  await fetch(`/api/v1/batches/${batch.batch_id}`, {
    method: "DELETE",
    headers: { "X-Batch-Token": batch.batch_token },
  });
}

export function beaconDisposeBatch(batch: BatchSession): void {
  if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
    navigator.sendBeacon(
      `/api/v1/batches/${batch.batch_id}/dispose?token=${encodeURIComponent(batch.batch_token)}`
    );
  }
}

export function buildJobDownloadUrl(batch: BatchSession, jobId: string, autoDelete: boolean): string {
  const params = new URLSearchParams({ token: batch.batch_token });
  if (autoDelete) params.set("auto_delete", "true");
  return `/api/v1/jobs/${jobId}/download?${params.toString()}`;
}

export function buildBatchZipUrl(batch: BatchSession): string {
  return `/api/v1/batches/${batch.batch_id}/download.zip?token=${encodeURIComponent(batch.batch_token)}`;
}
