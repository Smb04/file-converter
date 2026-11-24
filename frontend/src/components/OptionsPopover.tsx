import { useEffect } from "react";
import { X } from "lucide-react";
import type { Category, ConversionOptions } from "../types";

interface OptionsPopoverProps {
  isOpen: boolean;
  filename: string;
  category: Category;
  options: ConversionOptions;
  onChange: (next: ConversionOptions) => void;
  onClose: () => void;
}

export function OptionsPopover({
  isOpen,
  filename,
  category,
  options,
  onChange,
  onClose,
}: OptionsPopoverProps) {
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Erweiterte Optionen" onClick={onClose}>
      <div className="popover-panel" onClick={(e) => e.stopPropagation()}>
        <div className="popover-header">
          <h3>Optionen: {filename}</h3>
          <button type="button" className="btn btn-ghost icon-btn" onClick={onClose} aria-label="Schliessen">
            <X size={18} />
          </button>
        </div>

        <div className="popover-body">
          {category === "image" && (
            <>
              <div className="option-field">
                <label htmlFor="opt-quality">Qualitaet ({options.quality} %)</label>
                <input
                  id="opt-quality"
                  type="range"
                  min={10}
                  max={100}
                  value={options.quality}
                  onChange={(e) => onChange({ ...options, quality: Number(e.target.value) })}
                />
              </div>
              <div className="option-field">
                <label htmlFor="opt-max-width">Max. Breite in Pixeln (leer = Original)</label>
                <input
                  id="opt-max-width"
                  className="field-input"
                  type="number"
                  min={16}
                  max={16000}
                  placeholder="Original"
                  value={options.max_width ?? ""}
                  onChange={(e) =>
                    onChange({
                      ...options,
                      max_width: e.target.value ? Number(e.target.value) : null,
                    })
                  }
                />
              </div>
              <div className="option-field">
                <label htmlFor="opt-dpi">Raster-DPI (fuer SVG)</label>
                <select
                  id="opt-dpi"
                  className="field-input"
                  value={options.dpi}
                  onChange={(e) => onChange({ ...options, dpi: Number(e.target.value) })}
                >
                  <option value={72}>72 DPI (Bildschirm)</option>
                  <option value={150}>150 DPI (Standard)</option>
                  <option value={300}>300 DPI (Druck)</option>
                </select>
              </div>
              <label className="toggle-label">
                <input
                  type="checkbox"
                  checked={options.strip_metadata}
                  onChange={(e) => onChange({ ...options, strip_metadata: e.target.checked })}
                />
                <span>EXIF- & Kameradaten entfernen (Datenschutz)</span>
              </label>
            </>
          )}

          {category === "audio" && (
            <>
              <div className="option-field">
                <label htmlFor="opt-bitrate">Bitrate</label>
                <select
                  id="opt-bitrate"
                  className="field-input"
                  value={options.audio_bitrate}
                  onChange={(e) => onChange({ ...options, audio_bitrate: e.target.value })}
                >
                  <option value="128k">128 kbps</option>
                  <option value="192k">192 kbps (Standard)</option>
                  <option value="256k">256 kbps</option>
                  <option value="320k">320 kbps (Max)</option>
                </select>
              </div>
              <div className="option-field">
                <label htmlFor="opt-channels">Kanaele</label>
                <select
                  id="opt-channels"
                  className="field-input"
                  value={options.channels ?? ""}
                  onChange={(e) =>
                    onChange({ ...options, channels: e.target.value ? Number(e.target.value) : null })
                  }
                >
                  <option value="">Original beibehalten</option>
                  <option value="2">Stereo</option>
                  <option value="1">Mono (Sprache)</option>
                </select>
              </div>
              <label className="toggle-label">
                <input
                  type="checkbox"
                  checked={options.normalize_audio}
                  onChange={(e) => onChange({ ...options, normalize_audio: e.target.checked })}
                />
                <span>Lautstaerke normalisieren (EBU R128)</span>
              </label>
            </>
          )}

          {category === "video" && (
            <>
              <div className="option-field">
                <label htmlFor="opt-vpreset">Qualitaets-Preset</label>
                <select
                  id="opt-vpreset"
                  className="field-input"
                  value={options.video_preset}
                  onChange={(e) =>
                    onChange({
                      ...options,
                      video_preset: e.target.value as ConversionOptions["video_preset"],
                    })
                  }
                >
                  <option value="small">Klein (kompakt)</option>
                  <option value="balanced">Ausgewogen (Standard)</option>
                  <option value="high">Hoch (minimaler Verlust)</option>
                </select>
              </div>
              <div className="option-field">
                <label htmlFor="opt-vres">Zielaufloesung</label>
                <select
                  id="opt-vres"
                  className="field-input"
                  value={options.video_resolution}
                  onChange={(e) =>
                    onChange({
                      ...options,
                      video_resolution: e.target.value as ConversionOptions["video_resolution"],
                    })
                  }
                >
                  <option value="original">Original</option>
                  <option value="1080p">1080p (Full HD)</option>
                  <option value="720p">720p (HD)</option>
                  <option value="480p">480p (Kompakt)</option>
                </select>
              </div>
              <label className="toggle-label">
                <input
                  type="checkbox"
                  checked={options.mute_audio}
                  onChange={(e) => onChange({ ...options, mute_audio: e.target.checked })}
                />
                <span>Tonspur entfernen (Stummschalten)</span>
              </label>
            </>
          )}

          {(category === "document" || category === "data") && (
            <>
              <div className="option-field">
                <label htmlFor="opt-doc-dpi">Export-Aufloesung (PDF zu Bild)</label>
                <select
                  id="opt-doc-dpi"
                  className="field-input"
                  value={options.dpi}
                  onChange={(e) => onChange({ ...options, dpi: Number(e.target.value) })}
                >
                  <option value={72}>72 DPI (Schnellvorschau)</option>
                  <option value={150}>150 DPI (Standard)</option>
                  <option value={300}>300 DPI (Scharf / Druck)</option>
                </select>
              </div>
              <div className="option-field">
                <label htmlFor="opt-pages">Seitenbereich (optional, z. B. 1-5)</label>
                <input
                  id="opt-pages"
                  className="field-input"
                  type="text"
                  placeholder="Alle Seiten"
                  value={options.page_range ?? ""}
                  onChange={(e) => onChange({ ...options, page_range: e.target.value || null })}
                />
              </div>
              <div className="option-field">
                <label htmlFor="opt-pdfq">PDF-Komprimierung</label>
                <select
                  id="opt-pdfq"
                  className="field-input"
                  value={options.pdf_quality}
                  onChange={(e) =>
                    onChange({
                      ...options,
                      pdf_quality: e.target.value as ConversionOptions["pdf_quality"],
                    })
                  }
                >
                  <option value="screen">Stark (72 dpi Bildschirm)</option>
                  <option value="ebook">Ausgewogen (150 dpi E-Book)</option>
                  <option value="prepress">Hochwertig (300 dpi Druck)</option>
                </select>
              </div>
            </>
          )}

          <button type="button" className="btn btn-primary" onClick={onClose}>
            Uebernehmen
          </button>
        </div>
      </div>
    </div>
  );
}
