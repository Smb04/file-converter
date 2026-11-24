import { FileStack, Plus, Sun, Moon, Monitor, HelpCircle } from "lucide-react";
import type { ThemePreference } from "../types";

interface HeaderProps {
  fileCount: number;
  totalBytes: number;
  theme: ThemePreference;
  onCycleTheme: () => void;
  onAddFiles: () => void;
  onOpenCapabilities: () => void;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex++;
  }
  return `${value.toFixed(value >= 10 ? 1 : 2).replace(".", ",")} ${units[unitIndex]}`;
}

export function Header({
  fileCount,
  totalBytes,
  theme,
  onCycleTheme,
  onAddFiles,
  onOpenCapabilities,
}: HeaderProps) {
  const themeLabel =
    theme === "auto" ? "Design: System" : theme === "dark" ? "Design: Dunkel" : "Design: Hell";

  return (
    <header className="app-header">
      <div className="brand">
        <div className="brand-icon" aria-hidden="true">
          <FileStack size={20} />
        </div>
        <div>
          <h1 className="brand-title">FileConverter</h1>
          <p className="brand-sub tabular">
            {fileCount > 0
              ? `${fileCount} ${fileCount === 1 ? "Datei" : "Dateien"} • ${formatBytes(totalBytes)}`
              : "Ephemerer Universal-Konverter • Zero-Persistence"}
          </p>
        </div>
      </div>

      <div className="header-actions">
        {fileCount > 0 && (
          <button type="button" className="btn btn-primary" onClick={onAddFiles}>
            <Plus size={18} aria-hidden="true" />
            <span>Hinzufuegen</span>
          </button>
        )}

        <button
          type="button"
          className="btn"
          onClick={onOpenCapabilities}
          aria-label="Unterstuetzte Formate anzeigen"
        >
          <HelpCircle size={18} aria-hidden="true" />
          <span>Formate</span>
        </button>

        <button
          type="button"
          className="btn"
          onClick={onCycleTheme}
          aria-label={`Farbschema wechseln (aktuell ${themeLabel})`}
          title={themeLabel}
        >
          {theme === "auto" ? (
            <Monitor size={18} aria-hidden="true" />
          ) : theme === "dark" ? (
            <Moon size={18} aria-hidden="true" />
          ) : (
            <Sun size={18} aria-hidden="true" />
          )}
          <span>{theme === "auto" ? "Auto" : theme === "dark" ? "Dunkel" : "Hell"}</span>
        </button>
      </div>
    </header>
  );
}
