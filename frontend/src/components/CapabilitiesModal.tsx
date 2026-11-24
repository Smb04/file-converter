import { useEffect } from "react";
import { X } from "lucide-react";
import type { FormatSpec } from "../types";

interface CapabilitiesModalProps {
  isOpen: boolean;
  formats: FormatSpec[];
  onClose: () => void;
}

export function CapabilitiesModal({ isOpen, formats, onClose }: CapabilitiesModalProps) {
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const groups: Array<{ id: string; title: string }> = [
    { id: "image", title: "Bilder & Vektoren" },
    { id: "audio", title: "Audio" },
    { id: "video", title: "Video (+ Audio-Extraktion)" },
    { id: "document", title: "Dokumente, PDF & E-Books" },
    { id: "data", title: "Strukturierte Daten & Tabellen" },
  ];

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Unterstuetzte Formate" onClick={onClose}>
      <div className="popover-panel" onClick={(e) => e.stopPropagation()}>
        <div className="popover-header">
          <h3>Unterstuetzte Dateiformate</h3>
          <button type="button" className="btn btn-ghost icon-btn" onClick={onClose} aria-label="Schliessen">
            <X size={18} />
          </button>
        </div>

        <div className="popover-body">
          {groups.map((grp) => {
            const list = formats.filter((f) => f.category === grp.id);
            return (
              <div key={grp.id}>
                <strong style={{ display: "block", marginBottom: 6 }}>{grp.title}</strong>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {list.map((item) => (
                    <span
                      key={item.id}
                      style={{
                        padding: "4px 10px",
                        borderRadius: 8,
                        background: "var(--bg-secondary)",
                        fontSize: "0.82rem",
                      }}
                    >
                      {item.label}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
