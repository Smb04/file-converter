import { useEffect, useState, type FormEvent } from "react";
import { Trash2, UserPlus, KeyRound, X } from "lucide-react";
import type { ManagedUser } from "../types";
import { changePassword, deleteUser, fetchUsers, registerUser } from "../services/api";

interface LocalUsersModalProps {
  isOpen: boolean;
  currentUsername: string;
  onClose: () => void;
  onNotify: (msg: string) => void;
}

export function LocalUsersModal({
  isOpen,
  currentUsername,
  onClose,
  onNotify,
}: LocalUsersModalProps) {
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [newUser, setNewUser] = useState("");
  const [newUserPw, setNewUserPw] = useState("");
  const [curPw, setCurPw] = useState("");
  const [nextPw, setNextPw] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loadUsers = () => {
    fetchUsers()
      .then(setUsers)
      .catch((err) => setError(err instanceof Error ? err.message : "Fehler beim Laden."));
  };

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    loadUsers();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleCreateUser = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await registerUser(newUser, newUserPw);
      setNewUser("");
      setNewUserPw("");
      onNotify("Neues Benutzerkonto wurde im lokalen Netzwerk angelegt.");
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fehler beim Anlegen.");
    }
  };

  const handleChangePassword = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await changePassword(curPw, nextPw);
      setCurPw("");
      setNextPw("");
      onNotify("Passwort aktualisiert (alte Sessions wurden abgemeldet).");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Passwortwechsel fehlgeschlagen.");
    }
  };

  const handleDelete = async (uname: string) => {
    setError(null);
    try {
      await deleteUser(uname);
      onNotify(`Konto "${uname}" geloescht.`);
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Loeschen fehlgeschlagen.");
    }
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Lokale Benutzerverwaltung" onClick={onClose}>
      <div className="popover-panel" onClick={(e) => e.stopPropagation()}>
        <div className="popover-header">
          <h3>Lokale Benutzerverwaltung (nur LAN)</h3>
          <button type="button" className="btn btn-ghost icon-btn" onClick={onClose} aria-label="Schliessen">
            <X size={18} />
          </button>
        </div>

        <div className="popover-body">
          {error && (
            <div className="auth-error" role="alert">
              {error}
            </div>
          )}

          <div>
            <strong style={{ display: "block", marginBottom: 8 }}>Aktive Konten ({users.length})</strong>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {users.map((u) => (
                <div
                  key={u.username}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "8px 12px",
                    borderRadius: 10,
                    background: "var(--bg-secondary)",
                  }}
                >
                  <span>
                    <strong>{u.username}</strong>
                    {u.username === currentUsername ? " (aktiv)" : ""}
                  </span>
                  {u.username !== currentUsername && users.length > 1 && (
                    <button
                      type="button"
                      className="btn btn-destructive icon-btn"
                      onClick={() => void handleDelete(u.username)}
                      aria-label={`Benutzer ${u.username} loeschen`}
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          <form onSubmit={(e) => void handleCreateUser(e)} autoComplete="off" className="auth-form">
            <div className="auth-heading">
              <UserPlus size={17} />
              <strong>Neuen Benutzer anlegen</strong>
            </div>
            <input
              type="text"
              className="field-input"
              placeholder="Benutzername (3-32 Zeichen)"
              required
              minLength={3}
              maxLength={32}
              value={newUser}
              onChange={(e) => setNewUser(e.target.value)}
            />
            <input
              type="password"
              className="field-input"
              placeholder="Passwort (mind. 10 Zeichen)"
              autoComplete="new-password"
              required
              minLength={10}
              maxLength={128}
              value={newUserPw}
              onChange={(e) => setNewUserPw(e.target.value)}
            />
            <button type="submit" className="btn btn-primary">
              Benutzer anlegen
            </button>
          </form>

          <form onSubmit={(e) => void handleChangePassword(e)} autoComplete="on" className="auth-form">
            <div className="auth-heading">
              <KeyRound size={17} />
              <strong>Eigenes Passwort aendern</strong>
            </div>
            <input
              type="password"
              name="current_password"
              className="field-input"
              placeholder="Aktuelles Passwort"
              autoComplete="current-password"
              required
              value={curPw}
              onChange={(e) => setCurPw(e.target.value)}
            />
            <input
              type="password"
              name="new_password"
              className="field-input"
              placeholder="Neues Passwort (mind. 10 Zeichen)"
              autoComplete="new-password"
              required
              minLength={10}
              maxLength={128}
              value={nextPw}
              onChange={(e) => setNextPw(e.target.value)}
            />
            <button type="submit" className="btn">
              Passwort speichern
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
