import {
  Download,
  SlidersHorizontal,
  Trash2,
  Square,
  RotateCcw,
  ChevronDown,
  ArrowUp,
  ArrowDown,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from "lucide-react";
import type { BatchFileItem } from "../types";
import { formatBytes } from "./Header";

interface FileRowProps {
  item: BatchFileItem;
  index: number;
  totalCount: number;
  mergeImagesToPdf: boolean;
  onOpenFormatPicker: (localId: string) => void;
  onOpenOptions: (localId: string) => void;
  onConvertSingle: (localId: string) => void;
  onCancel: (localId: string) => void;
  onDownload: (localId: string) => void;
  onRemove: (localId: string) => void;
  onMove: (localId: string, direction: -1 | 1) => void;
}

export function FileRow({
  item,
  index,
  totalCount,
  mergeImagesToPdf,
  onOpenFormatPicker,
  onOpenOptions,
  onConvertSingle,
  onCancel,
  onDownload,
  onRemove,
  onMove,
}: FileRowProps) {
  const isLocked = item.stage === "uploading" || item.stage === "queued" || item.stage === "running";
  const pct = item.stage === "uploading" ? item.uploadProgress : item.jobProgress;

  const savingsPct =
    item.outputSize && item.size > 0
      ? Math.round(((item.size - item.outputSize) / item.size) * 100)
      : null;

  return (
    <div className="file-row" role="listitem">
      <div className="format-badge" aria-label={`Erkanntes Format: ${item.detectedFormat || "..."}`}>
        {(item.detectedFormat || "...").toUpperCase()}
      </div>

      <div className="file-main">
        <div className="file-title-line">
          <span className="file-name" title={item.filename}>
            {item.filename}
          </span>
          <span className="file-meta tabular">{formatBytes(item.size)}</span>

          {item.stage === "completed" && item.outputSize !== undefined && (
            <span className="status-pill success tabular">
              <CheckCircle2 size={14} aria-hidden="true" />
              <span>
                Fertig • {formatBytes(item.outputSize)}
                {savingsPct !== null && savingsPct > 0 ? ` (-${savingsPct} %)` : ""}
                {item.pageCount && item.pageCount > 1 ? ` • ${item.pageCount} Seiten (ZIP)` : ""}
              </span>
            </span>
          )}

          {item.stage === "failed" && (
            <span className="status-pill error">
              <AlertCircle size={14} aria-hidden="true" />
              <span>{item.errorMessage || "Fehler bei Konvertierung"}</span>
            </span>
          )}

          {(item.stage === "uploading" || item.stage === "running" || item.stage === "queued") && (
            <span className="status-pill running tabular">
              <Loader2 size={14} aria-hidden="true" />
              <span>
                {item.stage === "uploading"
                  ? `Laedt hoch ${item.uploadProgress} %`
                  : `${item.phase || "Verarbeite"} ${item.jobProgress} %`}
              </span>
            </span>
          )}
        </div>

        {(isLocked || item.stage === "completed" || item.stage === "failed") && (
          <div className="progress-track" aria-hidden="true">
            <div
              className={`progress-fill ${
                item.stage === "uploading"
                  ? "uploading"
                  : item.stage === "completed"
                  ? "completed"
                  : item.stage === "failed"
                  ? "failed"
                  : ""
              }`}
              style={{ width: `${item.stage === "completed" ? 100 : Math.max(4, pct)}%` }}
            />
          </div>
        )}
      </div>

      <div className="file-actions">
        {mergeImagesToPdf && item.category === "image" && (
          <>
            <button
              type="button"
              className="btn icon-btn"
              disabled={index === 0 || isLocked}
              onClick={() => onMove(item.localId, -1)}
              aria-label={`${item.filename} nach oben verschieben`}
            >
              <ArrowUp size={16} />
            </button>
            <button
              type="button"
              className="btn icon-btn"
              disabled={index === totalCount - 1 || isLocked}
              onClick={() => onMove(item.localId, 1)}
              aria-label={`${item.filename} nach unten verschieben`}
            >
              <ArrowDown size={16} />
            </button>
          </>
        )}

        {!mergeImagesToPdf && item.validTargets.length > 0 && (
          <button
            type="button"
            className="target-pill"
            disabled={isLocked}
            onClick={() => onOpenFormatPicker(item.localId)}
            aria-label={`Zielformat fuer ${item.filename} aendern (aktuell ${item.targetFormat.toUpperCase()})`}
          >
            <span>{item.targetFormat.toUpperCase()}</span>
            <ChevronDown size={15} aria-hidden="true" />
          </button>
        )}

        {item.fileId && !isLocked && (
          <button
            type="button"
            className="btn icon-btn"
            onClick={() => onOpenOptions(item.localId)}
            aria-label={`Erweiterte Optionen fuer ${item.filename}`}
            title="Optionen"
          >
            <SlidersHorizontal size={16} />
          </button>
        )}

        {item.stage === "ready" && !mergeImagesToPdf && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => onConvertSingle(item.localId)}
          >
            Konvertieren
          </button>
        )}

        {item.stage === "failed" && item.fileId && (
          <button
            type="button"
            className="btn"
            onClick={() => onConvertSingle(item.localId)}
            aria-label={`Konvertierung fuer ${item.filename} erneut starten`}
          >
            <RotateCcw size={16} aria-hidden="true" />
            <span>Neu</span>
          </button>
        )}

        {(item.stage === "running" || item.stage === "queued") && item.jobId && (
          <button
            type="button"
            className="btn btn-destructive"
            onClick={() => onCancel(item.localId)}
            aria-label={`Konvertierung fuer ${item.filename} abbrechen`}
          >
            <Square size={15} aria-hidden="true" />
            <span>Stop</span>
          </button>
        )}

        {item.stage === "completed" && item.jobId && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => onDownload(item.localId)}
          >
            <Download size={16} aria-hidden="true" />
            <span>Laden</span>
          </button>
        )}

        <button
          type="button"
          className="btn btn-ghost icon-btn"
          onClick={() => onRemove(item.localId)}
          aria-label={`${item.filename} aus der Liste entfernen`}
          title="Entfernen"
        >
          <Trash2 size={16} />
        </button>
      </div>
    </div>
  );
}
