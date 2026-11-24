import { useEffect, useMemo, useState } from "react";
import { X } from "lucide-react";
import type { FormatSpec } from "../types";

interface FormatPopoverProps {
  isOpen: boolean;
  validTargets: string[];
  currentTarget: string;
  allFormats: FormatSpec[];
  recentFormats: string[];
  onSelect: (fmt: string) => void;
  onClose: () => void;
}

export function FormatPopover({
  isOpen,
  validTargets,
  currentTarget,
  allFormats,
  recentFormats,
  onSelect,
  onClose,
}: FormatPopoverProps) {
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!isOpen) return;
    setQuery("");
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  const specMap = useMemo(() => {
    const map = new Map<string, FormatSpec>();
    for (const f of allFormats) map.set(f.id, f);
    return map;
  }, [allFormats]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return validTargets
      .map((id) => specMap.get(id) ?? { id, label: id.toUpperCase(), hint: "", category: "image" as const })
      .filter(
        (item) =>
          !q ||
          item.id.toLowerCase().includes(q) ||
          item.label.toLowerCase().includes(q) ||
          item.hint.toLowerCase().includes(q)
      );
  }, [validTargets, specMap, query]);

  const recentValid = recentFormats.filter((r) => validTargets.includes(r));

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Zielformat waehlen" onClick={onClose}>
      <div className="popover-panel" onClick={(e) => e.stopPropagation()}>
        <div className="popover-header">
          <h3>Zielformat waehlen</h3>
          <button type="button" className="btn btn-ghost icon-btn" onClick={onClose} aria-label="Schliessen">
            <X size={18} />
          </button>
        </div>

        <div className="popover-body">
          <input
            type="search"
            className="search-input"
            autoFocus
            placeholder="Format suchen (z. B. webp, pdf, mp3)..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Zielformat filtern"
          />

          {!query && recentValid.length > 0 && (
            <div>
              <div className="hint-line" style={{ marginBottom: 6 }}>
                Zuletzt verwendet
              </div>
              <div className="format-grid">
                {recentValid.map((id) => {
                  const spec = specMap.get(id);
                  return (
                    <button
                      key={`rec-${id}`}
                      type="button"
                      className={`format-option ${currentTarget === id ? "selected" : ""}`}
                      onClick={() => {
                        onSelect(id);
                        onClose();
                      }}
                    >
                      <strong>{spec?.label || id.toUpperCase()}</strong>
                      <span>{spec?.hint || "Schnellwahl"}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div>
            <div className="hint-line" style={{ marginBottom: 6 }}>
              Alle moeglichen Zielformate ({filtered.length})
            </div>
            <div className="format-grid">
              {filtered.map((spec) => (
                <button
                  key={spec.id}
                  type="button"
                  className={`format-option ${currentTarget === spec.id ? "selected" : ""}`}
                  onClick={() => {
                    onSelect(spec.id);
                    onClose();
                  }}
                >
                  <strong>{spec.label}</strong>
                  <span>{spec.hint}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
