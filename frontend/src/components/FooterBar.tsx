import { Clock, Download, Trash2 } from "lucide-react";

interface FooterBarProps {
  remainingSeconds: number | null;
  completedCount: number;
  autoDeleteAfterDownload: boolean;
  onToggleAutoDelete: (val: boolean) => void;
  onDownloadAllZip: () => void;
  onPurgeAll: () => void;
}

function formatCountdown(sec: number): string {
  const safe = Math.max(0, Math.floor(sec));
  const m = Math.floor(safe / 60);
  const s = safe % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function FooterBar({
  remainingSeconds,
  completedCount,
  autoDeleteAfterDownload,
  onToggleAutoDelete,
  onDownloadAllZip,
  onPurgeAll,
}: FooterBarProps) {
  const isWarning = remainingSeconds !== null && remainingSeconds < 180;

  return (
    <footer className="card ephemeral-footer">
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        {remainingSeconds !== null && (
          <span className={`ttl-badge tabular ${isWarning ? "warning" : ""}`}>
            <Clock size={15} aria-hidden="true" />
            <span>Verfällt in {formatCountdown(remainingSeconds)}</span>
          </span>
        )}

        <label className="toggle-label">
          <input
            type="checkbox"
            checked={autoDeleteAfterDownload}
            onChange={(e) => onToggleAutoDelete(e.target.checked)}
          />
          <span>Nach Einzeldownload sofort loeschen</span>
        </label>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <button type="button" className="btn btn-destructive" onClick={onPurgeAll}>
          <Trash2 size={16} aria-hidden="true" />
          <span>Alle Dateien jetzt loeschen</span>
        </button>

        {completedCount >= 1 && (
          <button type="button" className="btn btn-primary" onClick={onDownloadAllZip}>
            <Download size={16} aria-hidden="true" />
            <span>Alle als ZIP laden ({completedCount})</span>
          </button>
        )}
      </div>
    </footer>
  );
}
