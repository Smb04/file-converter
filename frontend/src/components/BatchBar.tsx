import { Play, Layers } from "lucide-react";
import type { BatchFileItem, FormatSpec } from "../types";

interface BatchBarProps {
  items: BatchFileItem[];
  formats: FormatSpec[];
  mergeImagesToPdf: boolean;
  onToggleMergeImages: (value: boolean) => void;
  onApplyCategoryTarget: (category: string, target: string) => void;
  onConvertAll: () => void;
  isConvertingAny: boolean;
}

export function BatchBar({
  items,
  formats,
  mergeImagesToPdf,
  onToggleMergeImages,
  onApplyCategoryTarget,
  onConvertAll,
  isConvertingAny,
}: BatchBarProps) {
  const readyImageCount = items.filter((i) => i.category === "image" && i.fileId).length;
  const hasReadyItems = items.some((i) => i.stage === "ready" || i.stage === "failed");
  const categoriesPresent = Array.from(
    new Set(items.map((i) => i.category).filter(Boolean))
  ) as string[];

  const categoryLabels: Record<string, string> = {
    image: "Alle Bilder ->",
    audio: "Alle Audio ->",
    video: "Alle Video ->",
    document: "Alle Dokumente ->",
    data: "Alle Daten ->",
  };

  return (
    <div className="card batch-bar" role="region" aria-label="Stapel-Steuerung">
      <div className="batch-controls-left">
        {categoriesPresent.map((cat) => {
          const outOptions = formats.filter((f) => f.category === cat && f.can_output);
          if (outOptions.length === 0) return null;
          return (
            <label key={cat} className="toggle-label">
              <span>{categoryLabels[cat] ?? `${cat} ->`}</span>
              <select
                className="target-pill"
                defaultValue=""
                aria-label={`Zielformat fuer ${cat} gesamt festlegen`}
                onChange={(e) => {
                  if (e.target.value) {
                    onApplyCategoryTarget(cat, e.target.value);
                    e.target.value = "";
                  }
                }}
              >
                <option value="" disabled>
                  Ziel waehlen
                </option>
                {outOptions.map((opt) => (
                  <option key={opt.id} value={opt.id}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
          );
        })}

        {readyImageCount >= 2 && (
          <label className="toggle-label">
            <input
              type="checkbox"
              checked={mergeImagesToPdf}
              onChange={(e) => onToggleMergeImages(e.target.checked)}
            />
            <Layers size={16} aria-hidden="true" />
            <span>Bilder zu einem PDF kombinieren</span>
          </label>
        )}
      </div>

      <button
        type="button"
        className="btn btn-primary"
        disabled={!hasReadyItems || isConvertingAny}
        onClick={onConvertAll}
      >
        <Play size={16} aria-hidden="true" />
        <span>{mergeImagesToPdf ? "PDF erstellen" : "Alle konvertieren"}</span>
      </button>
    </div>
  );
}
