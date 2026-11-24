import { useCallback, useEffect, useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import { BatchBar } from "./components/BatchBar";
import { CapabilitiesModal } from "./components/CapabilitiesModal";
import { Dropzone } from "./components/Dropzone";
import { FileRow } from "./components/FileRow";
import { FooterBar } from "./components/FooterBar";
import { FormatPopover } from "./components/FormatPopover";
import { Header } from "./components/Header";
import { OptionsPopover } from "./components/OptionsPopover";
import { ToastContainer, type ToastMessage } from "./components/Toast";
import { useLocalPreferences } from "./hooks/useLocalPreferences";
import {
  beaconDisposeBatch,
  buildBatchZipUrl,
  buildJobDownloadUrl,
  cancelJob,
  createBatch,
  fetchCapabilities,
  purgeBatch,
  startConversion,
  uploadFileChunked,
} from "./services/api";
import {
  DEFAULT_OPTIONS,
  type BatchFileItem,
  type BatchSession,
  type CapabilitiesResponse,
  type ThemePreference,
} from "./types";

export default function App() {
  const {
    prefs,
    setTheme,
    recordRecentFormat,
    setAutoDeleteAfterDownload,
  } = useLocalPreferences();

  const [capabilities, setCapabilities] = useState<CapabilitiesResponse | null>(null);
  const [batch, setBatch] = useState<BatchSession | null>(null);
  const [items, setItems] = useState<BatchFileItem[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [mergeImagesToPdf, setMergeImagesToPdf] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(null);

  const [formatPickerId, setFormatPickerId] = useState<string | null>(null);
  const [optionsPickerId, setOptionsPickerId] = useState<string | null>(null);
  const [showCapabilities, setShowCapabilities] = useState(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [liveAnnouncement, setLiveAnnouncement] = useState("");

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const dragCounterRef = useRef(0);
  const batchRef = useRef<BatchSession | null>(null);
  batchRef.current = batch;

  const pushToast = useCallback((text: string, onUndo?: () => void) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setToasts((prev) => [...prev, { id, text, onUndo }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5500);
  }, []);

  useEffect(() => {
    fetchCapabilities()
      .then(setCapabilities)
      .catch(() => pushToast("Verbindung zum Server konnte nicht hergestellt werden."));
  }, [pushToast]);

  // Countdown ticker for ephemeral TTL
  useEffect(() => {
    if (!batch) {
      setRemainingSeconds(null);
      return;
    }
    const tick = () => {
      const rem = Math.max(0, Math.round(batch.expires_at - Date.now() / 1000));
      setRemainingSeconds(rem);
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [batch]);

  // SSE stream subscription for active batch
  useEffect(() => {
    if (!batch) return;
    const es = new EventSource(
      `/api/v1/batches/${batch.batch_id}/events?token=${encodeURIComponent(batch.batch_token)}`
    );

    const onProgress = (e: MessageEvent) => {
      const data = JSON.parse(e.data) as { job_id: string; progress: number; phase: string };
      setItems((prev) =>
        prev.map((it) =>
          it.jobId === data.job_id
            ? { ...it, stage: "running", jobProgress: data.progress, phase: data.phase }
            : it
        )
      );
    };

    const onCompleted = (e: MessageEvent) => {
      const data = JSON.parse(e.data) as {
        job_id: string;
        output_filename: string;
        output_size: number;
        is_archive: boolean;
        page_count: number | null;
      };
      setItems((prev) =>
        prev.map((it) =>
          it.jobId === data.job_id
            ? {
                ...it,
                stage: "completed",
                jobProgress: 100,
                phase: "Fertig",
                outputFilename: data.output_filename,
                outputSize: data.output_size,
                isArchive: data.is_archive,
                pageCount: data.page_count,
              }
            : it
        )
      );
      setLiveAnnouncement("Eine Datei wurde fertig konvertiert.");
    };

    const onFailed = (e: MessageEvent) => {
      const data = JSON.parse(e.data) as { job_id: string; error_message: string };
      setItems((prev) =>
        prev.map((it) =>
          it.jobId === data.job_id
            ? { ...it, stage: "failed", errorMessage: data.error_message, phase: "Fehlgeschlagen" }
            : it
        )
      );
      setLiveAnnouncement(`Fehler: ${data.error_message}`);
    };

    const onCancelled = (e: MessageEvent) => {
      const data = JSON.parse(e.data) as { job_id: string };
      setItems((prev) =>
        prev.map((it) =>
          it.jobId === data.job_id ? { ...it, stage: "ready", jobProgress: 0, phase: "Abgebrochen" } : it
        )
      );
    };

    es.addEventListener("job.progress", onProgress as EventListener);
    es.addEventListener("job.completed", onCompleted as EventListener);
    es.addEventListener("job.failed", onFailed as EventListener);
    es.addEventListener("job.cancelled", onCancelled as EventListener);

    return () => es.close();
  }, [batch]);

  // Optional clean beacon on tab close when no job is running
  useEffect(() => {
    const onUnload = () => {
      if (batchRef.current) {
        beaconDisposeBatch(batchRef.current);
      }
    };
    window.addEventListener("pagehide", onUnload);
    return () => window.removeEventListener("pagehide", onUnload);
  }, []);

  const ensureBatchSession = useCallback(async (): Promise<BatchSession> => {
    if (batchRef.current) return batchRef.current;
    const created = await createBatch();
    batchRef.current = created;
    setBatch(created);
    return created;
  }, []);

  const enqueueFiles = useCallback(
    async (fileList: File[]) => {
      if (fileList.length === 0) return;

      let activeBatch: BatchSession;
      try {
        activeBatch = await ensureBatchSession();
      } catch (err) {
        pushToast(err instanceof Error ? err.message : "Batch konnte nicht erstellt werden.");
        return;
      }

      const maxFile = capabilities?.limits.max_file_bytes ?? 524288000;
      const chunkSize = capabilities?.limits.chunk_size_default ?? 5 * 1024 * 1024;

      for (const file of fileList) {
        const localId = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
        if (file.size <= 0) {
          pushToast(`"${file.name}" ist leer und wurde uebersprungen.`);
          continue;
        }
        if (file.size > maxFile) {
          pushToast(`"${file.name}" ueberschreitet das maximale Einzeldatei-Limit.`);
          continue;
        }

        const newItem: BatchFileItem = {
          localId,
          file,
          filename: file.name || "Zwischenablage",
          size: file.size,
          uploadProgress: 0,
          validTargets: [],
          targetFormat: "",
          options: { ...DEFAULT_OPTIONS, strip_metadata: prefs.defaultStripMetadata },
          stage: "uploading",
          jobProgress: 0,
          phase: "Laedt hoch",
        };
        setItems((prev) => [...prev, newItem]);

        uploadFileChunked(activeBatch, file, chunkSize, (pct) => {
          setItems((prev) =>
            prev.map((it) => (it.localId === localId ? { ...it, uploadProgress: pct } : it))
          );
        })
          .then((res) => {
            setItems((prev) =>
              prev.map((it) =>
                it.localId === localId
                  ? {
                      ...it,
                      fileId: res.file_id,
                      detectedFormat: res.detected_format,
                      category: res.category,
                      validTargets: res.valid_targets,
                      targetFormat: res.default_target,
                      stage: "ready",
                      uploadProgress: 100,
                      phase: "Bereit",
                    }
                  : it
              )
            );
          })
          .catch((err) => {
            const msg = err instanceof Error ? err.message : "Upload fehlgeschlagen.";
            setItems((prev) =>
              prev.map((it) =>
                it.localId === localId ? { ...it, stage: "failed", errorMessage: msg } : it
              )
            );
          });
      }
    },
    [capabilities, ensureBatchSession, prefs.defaultStripMetadata, pushToast]
  );

  // Full-window drag & drop + clipboard paste
  useEffect(() => {
    const onDragEnter = (e: DragEvent) => {
      if (!e.dataTransfer?.types.includes("Files")) return;
      e.preventDefault();
      dragCounterRef.current += 1;
      setIsDragging(true);
    };
    const onDragOver = (e: DragEvent) => {
      if (!e.dataTransfer?.types.includes("Files")) return;
      e.preventDefault();
    };
    const onDragLeave = (e: DragEvent) => {
      e.preventDefault();
      dragCounterRef.current = Math.max(0, dragCounterRef.current - 1);
      if (dragCounterRef.current === 0) setIsDragging(false);
    };
    const onDrop = (e: DragEvent) => {
      e.preventDefault();
      dragCounterRef.current = 0;
      setIsDragging(false);
      const dropped = Array.from(e.dataTransfer?.files ?? []);
      void enqueueFiles(dropped);
    };
    const onPaste = (e: ClipboardEvent) => {
      const pasted = Array.from(e.clipboardData?.files ?? []);
      if (pasted.length > 0) {
        void enqueueFiles(pasted);
      }
    };

    window.addEventListener("dragenter", onDragEnter);
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("dragleave", onDragLeave);
    window.addEventListener("drop", onDrop);
    window.addEventListener("paste", onPaste);
    return () => {
      window.removeEventListener("dragenter", onDragEnter);
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("dragleave", onDragLeave);
      window.removeEventListener("drop", onDrop);
      window.removeEventListener("paste", onPaste);
    };
  }, [enqueueFiles]);

  const handleCycleTheme = () => {
    const order: ThemePreference[] = ["auto", "light", "dark"];
    const next = order[(order.indexOf(prefs.theme) + 1) % order.length];
    setTheme(next);
  };

  const handleConvertSingle = async (localId: string) => {
    if (!batch) return;
    const item = items.find((i) => i.localId === localId);
    if (!item?.fileId || !item.targetFormat) return;
    recordRecentFormat(item.targetFormat);
    try {
      const res = await startConversion(batch, {
        items: [{ file_id: item.fileId, target_format: item.targetFormat, options: item.options }],
        merge_mode: "none",
        ordered_file_ids: [],
      });
      const job = res.jobs[0];
      setItems((prev) =>
        prev.map((it) =>
          it.localId === localId
            ? { ...it, stage: "queued", jobId: job.job_id, jobProgress: 0, phase: "In Warteschlange", errorMessage: undefined }
            : it
        )
      );
    } catch (err) {
      pushToast(err instanceof Error ? err.message : "Konvertierung fehlgeschlagen.");
    }
  };

  const handleConvertAll = async () => {
    if (!batch) return;
    if (mergeImagesToPdf) {
      const imageItems = items.filter((i) => i.category === "image" && i.fileId);
      if (imageItems.length < 2) return;
      try {
        const res = await startConversion(batch, {
          items: [],
          merge_mode: "images_to_pdf",
          ordered_file_ids: imageItems.map((i) => i.fileId!),
          merge_options: imageItems[0].options,
        });
        const job = res.jobs[0];
        const firstId = imageItems[0].localId;
        setItems((prev) =>
          prev.map((it) =>
            it.localId === firstId
              ? { ...it, stage: "queued", jobId: job.job_id, targetFormat: "pdf", phase: "Erstelle PDF" }
              : it
          )
        );
      } catch (err) {
        pushToast(err instanceof Error ? err.message : "PDF-Erstellung fehlgeschlagen.");
      }
      return;
    }

    const targets = items.filter((i) => (i.stage === "ready" || i.stage === "failed") && i.fileId);
    if (targets.length === 0) return;

    try {
      const res = await startConversion(batch, {
        items: targets.map((it) => {
          recordRecentFormat(it.targetFormat);
          return { file_id: it.fileId!, target_format: it.targetFormat, options: it.options };
        }),
        merge_mode: "none",
        ordered_file_ids: [],
      });
      const jobByFile = new Map(res.jobs.map((j) => [j.file_id, j]));
      setItems((prev) =>
        prev.map((it) => {
          const job = it.fileId ? jobByFile.get(it.fileId) : undefined;
          return job
            ? { ...it, stage: "queued", jobId: job.job_id, jobProgress: 0, phase: "In Warteschlange", errorMessage: undefined }
            : it;
        })
      );
    } catch (err) {
      pushToast(err instanceof Error ? err.message : "Batch-Konvertierung fehlgeschlagen.");
    }
  };

  const handlePurgeAll = async () => {
    if (batch) {
      await purgeBatch(batch);
    }
    batchRef.current = null;
    setBatch(null);
    setItems([]);
    setMergeImagesToPdf(false);
    pushToast("Alle gepufferten Dateien wurden restlos geloescht.");
  };

  const handleRemoveItem = (localId: string) => {
    const idx = items.findIndex((i) => i.localId === localId);
    if (idx === -1) return;
    const removed = items[idx];
    setItems((prev) => prev.filter((i) => i.localId !== localId));
    pushToast(`"${removed.filename}" entfernt.`, () => {
      setItems((prev) => {
        const copy = [...prev];
        copy.splice(Math.min(idx, copy.length), 0, removed);
        return copy;
      });
    });
  };

  const handleMoveItem = (localId: string, dir: -1 | 1) => {
    setItems((prev) => {
      const idx = prev.findIndex((i) => i.localId === localId);
      const nextIdx = idx + dir;
      if (idx < 0 || nextIdx < 0 || nextIdx >= prev.length) return prev;
      const copy = [...prev];
      const [moved] = copy.splice(idx, 1);
      copy.splice(nextIdx, 0, moved);
      return copy;
    });
  };

  const formatPickerItem = items.find((i) => i.localId === formatPickerId) ?? null;
  const optionsPickerItem = items.find((i) => i.localId === optionsPickerId) ?? null;
  const totalBytes = items.reduce((acc, it) => acc + it.size, 0);
  const completedCount = items.filter((it) => it.stage === "completed").length;
  const isConvertingAny = items.some((it) => it.stage === "running" || it.stage === "queued");

  return (
    <>
      <a className="skip-link" href="#main-content">
        Direkt zum Konverter springen
      </a>

      <div className="sr-only" aria-live="polite" style={{ position: "absolute", left: -9999 }}>
        {liveAnnouncement}
      </div>

      {isDragging && (
        <div className="drag-overlay" aria-hidden="true">
          <div className="drag-overlay-box">
            <UploadCloud size={52} color="var(--accent)" />
            <h2>Dateien hier loslassen</h2>
            <p className="hint-line">Werden direkt zum aktuellen Stapel hinzugefuegt</p>
          </div>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        multiple
        hidden
        aria-hidden="true"
        onChange={(e) => {
          const selected = Array.from(e.target.files ?? []);
          void enqueueFiles(selected);
          e.target.value = "";
        }}
      />

      <div className="app-shell">
        <Header
          fileCount={items.length}
          totalBytes={totalBytes}
          theme={prefs.theme}
          onCycleTheme={handleCycleTheme}
          onAddFiles={() => fileInputRef.current?.click()}
          onOpenCapabilities={() => setShowCapabilities(true)}
        />

        <main id="main-content" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {items.length === 0 ? (
            <>
              <Dropzone isDragging={isDragging} onSelectFiles={() => fileInputRef.current?.click()} />
              <p className="ephemeral-promise">
                Ephemer-Versprechen: Keine Konten, keine Datenbank. Dateien liegen nur kurzzeitig im RAM-Buffer und
                werden automatisch oder per Klick sofort geloescht.
              </p>
            </>
          ) : (
            <>
              <BatchBar
                items={items}
                formats={capabilities?.formats ?? []}
                mergeImagesToPdf={mergeImagesToPdf}
                onToggleMergeImages={setMergeImagesToPdf}
                onApplyCategoryTarget={(cat, target) => {
                  recordRecentFormat(target);
                  setItems((prev) =>
                    prev.map((it) =>
                      it.category === cat && it.validTargets.includes(target) && it.stage === "ready"
                        ? { ...it, targetFormat: target }
                        : it
                    )
                  );
                }}
                onConvertAll={() => void handleConvertAll()}
                isConvertingAny={isConvertingAny}
              />

              <section className="card file-list" role="list" aria-label="Hochgeladene Dateien">
                {items.map((item, idx) => (
                  <FileRow
                    key={item.localId}
                    item={item}
                    index={idx}
                    totalCount={items.length}
                    mergeImagesToPdf={mergeImagesToPdf}
                    onOpenFormatPicker={setFormatPickerId}
                    onOpenOptions={setOptionsPickerId}
                    onConvertSingle={(id) => void handleConvertSingle(id)}
                    onCancel={(id) => {
                      const target = items.find((i) => i.localId === id);
                      if (batch && target?.jobId) void cancelJob(batch, target.jobId);
                    }}
                    onDownload={(id) => {
                      const target = items.find((i) => i.localId === id);
                      if (batch && target?.jobId) {
                        window.location.href = buildJobDownloadUrl(
                          batch,
                          target.jobId,
                          prefs.autoDeleteAfterDownload
                        );
                      }
                    }}
                    onRemove={handleRemoveItem}
                    onMove={handleMoveItem}
                  />
                ))}
              </section>

              <FooterBar
                remainingSeconds={remainingSeconds}
                completedCount={completedCount}
                autoDeleteAfterDownload={prefs.autoDeleteAfterDownload}
                onToggleAutoDelete={setAutoDeleteAfterDownload}
                onDownloadAllZip={() => {
                  if (batch) window.location.href = buildBatchZipUrl(batch);
                }}
                onPurgeAll={() => void handlePurgeAll()}
              />
            </>
          )}
        </main>
      </div>

      <FormatPopover
        isOpen={Boolean(formatPickerItem)}
        validTargets={formatPickerItem?.validTargets ?? []}
        currentTarget={formatPickerItem?.targetFormat ?? ""}
        allFormats={capabilities?.formats ?? []}
        recentFormats={prefs.recentFormats}
        onSelect={(fmt) => {
          if (!formatPickerItem) return;
          recordRecentFormat(fmt);
          setItems((prev) =>
            prev.map((it) =>
              it.localId === formatPickerItem.localId ? { ...it, targetFormat: fmt } : it
            )
          );
        }}
        onClose={() => setFormatPickerId(null)}
      />

      <OptionsPopover
        isOpen={Boolean(optionsPickerItem)}
        filename={optionsPickerItem?.filename ?? ""}
        category={optionsPickerItem?.category ?? "image"}
        options={optionsPickerItem?.options ?? DEFAULT_OPTIONS}
        onChange={(nextOpts) => {
          if (!optionsPickerItem) return;
          setItems((prev) =>
            prev.map((it) =>
              it.localId === optionsPickerItem.localId ? { ...it, options: nextOpts } : it
            )
          );
        }}
        onClose={() => setOptionsPickerId(null)}
      />

      <CapabilitiesModal
        isOpen={showCapabilities}
        formats={capabilities?.formats ?? []}
        onClose={() => setShowCapabilities(false)}
      />

      <ToastContainer
        toasts={toasts}
        onDismiss={(id) => setToasts((prev) => prev.filter((t) => t.id !== id))}
      />
    </>
  );
}
