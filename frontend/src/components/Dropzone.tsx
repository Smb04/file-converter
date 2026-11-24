import { UploadCloud, Plus } from "lucide-react";

interface DropzoneProps {
  isDragging: boolean;
  onSelectFiles: () => void;
}

export function Dropzone({ isDragging, onSelectFiles }: DropzoneProps) {
  return (
    <section
      className={`card dropzone ${isDragging ? "active" : ""}`}
      aria-label="Dateien per Drag und Drop oder Schaltflaeche hochladen"
    >
      <div className="dropzone-icon" aria-hidden="true">
        <UploadCloud size={30} />
      </div>
      <h2>Dateien hierher ziehen oder auswaehlen</h2>
      <p>
        Konvertiere Bilder, Audio, Video, PDF, Office-Dokumente und strukturierte Daten
        untereinander — einzeln oder als kompletter Stapel.
      </p>
      <button type="button" className="btn btn-primary" onClick={onSelectFiles}>
        <Plus size={18} aria-hidden="true" />
        <span>Dateien auswaehlen</span>
      </button>
      <span className="hint-line">
        Tipp: Mehrfachauswahl moeglich • Strg/Cmd + V fuegt aus der Zwischenablage ein
      </span>
    </section>
  );
}
