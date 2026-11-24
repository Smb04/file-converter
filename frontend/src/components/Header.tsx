import { FileStack, Plus, Sun, Moon, Monitor, HelpCircle, Users, LogOut } from "lucide-react";
import type { ThemePreference } from "../types";

interface HeaderProps {
  fileCount: number;
  totalBytes: number;
  theme: ThemePreference;
  username: string | null;
  canManageUsersLocal: boolean;
  onCycleTheme: () => void;
  onAddFiles: () => void;
  onOpenCapabilities: () => void;
  onOpenUsersModal: () => void;
  onLogout: () => void;
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
  username,
  canManageUsersLocal,
  onCycleTheme,
  onAddFiles,
  onOpenCapabilities,
  onOpenUsersModal,
  onLogout,
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
              : `Angemeldet als ${username || "Benutzer"} • Zero-Persistence`}
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

        {canManageUsersLocal && (
          <button
            type="button"
            className="btn"
            onClick={onOpenUsersModal}
            aria-label="Lokale Benutzerverwaltung oeffnen"
          >
            <Users size={18} aria-hidden="true" />
            <span>Benutzer</span>
          </button>
        )}

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

        <button
          type="button"
          className="btn"
          onClick={onLogout}
          aria-label="Abmelden"
          title="Abmelden"
        >
          <LogOut size={18} aria-hidden="true" />
          <span>Abmelden</span>
        </button>
      </div>
    </header>
  );
}
