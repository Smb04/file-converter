import { RotateCcw, X } from "lucide-react";

export interface ToastMessage {
  id: string;
  text: string;
  undoLabel?: string;
  onUndo?: () => void;
}

interface ToastProps {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

export function ToastContainer({ toasts, onDismiss }: ToastProps) {
  if (toasts.length === 0) return null;

  return (
    <div className="toast-container" aria-live="polite" aria-atomic="true">
      {toasts.map((t) => (
        <div key={t.id} className="toast" role="status">
          <span>{t.text}</span>
          {t.onUndo && (
            <button
              type="button"
              className="btn btn-ghost"
              style={{ minHeight: 34, padding: "0 10px" }}
              onClick={() => {
                t.onUndo?.();
                onDismiss(t.id);
              }}
            >
              <RotateCcw size={14} aria-hidden="true" />
              <span>{t.undoLabel || "Rueckgaengig"}</span>
            </button>
          )}
          <button
            type="button"
            className="btn btn-ghost icon-btn"
            style={{ minWidth: 34, minHeight: 34 }}
            onClick={() => onDismiss(t.id)}
            aria-label="Meldung schliessen"
          >
            <X size={15} />
          </button>
        </div>
      ))}
    </div>
  );
}
