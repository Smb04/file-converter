import { useState, type FormEvent } from "react";
import { Lock, ShieldAlert, UserPlus, Eye, EyeOff, FileStack } from "lucide-react";
import type { AuthStatus } from "../types";
import { login, registerUser } from "../services/api";

interface LoginScreenProps {
  authStatus: AuthStatus;
  onSuccess: () => void;
}

export function LoginScreen({ authStatus, onSuccess }: LoginScreenProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isFirstSetup = !authStatus.has_users && authStatus.can_register_local;
  const blockedSetupRemote = !authStatus.has_users && !authStatus.can_register_local;

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password, rememberMe);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Anmeldung fehlgeschlagen.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleRegisterFirst = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < 10) {
      setError("Passwort muss mindestens 10 Zeichen lang sein.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Die Passwoerter stimmen nicht ueberein.");
      return;
    }
    setSubmitting(true);
    try {
      await registerUser(username, password);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Konto konnte nicht angelegt werden.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-shell">
      <div className="card auth-card">
        <div className="auth-brand">
          <div className="brand-icon" aria-hidden="true">
            <FileStack size={22} />
          </div>
          <div>
            <h1 className="brand-title">FileConverter</h1>
            <p className="brand-sub">Geschuetzter Zugang</p>
          </div>
        </div>

        {blockedSetupRemote && (
          <div className="auth-blocked" role="status">
            <ShieldAlert size={28} color="var(--status-warning)" aria-hidden="true" />
            <h2>Ersteinrichtung nur im Heimnetz moeglich</h2>
            <p>
              Es existiert noch kein Benutzerkonto. Aus Sicherheitsgruenden koennen Benutzername und
              Passwort ausschliesslich ueber die direkte lokale IP-Adresse (z. B.{" "}
              <code>http://&lt;ZIMAOS-LAN-IP&gt;:8095</code>) festgelegt werden — nicht ueber DuckDNS.
            </p>
          </div>
        )}

        {isFirstSetup && (
          <form
            method="post"
            action="/api/v1/auth/register"
            autoComplete="on"
            onSubmit={(e) => void handleRegisterFirst(e)}
            className="auth-form"
          >
            <div className="auth-heading">
              <UserPlus size={20} color="var(--accent)" aria-hidden="true" />
              <h2>Erstes Konto im lokalen LAN anlegen</h2>
            </div>
            <p className="hint-line">
              Dieses Konto kannst du direkt in Vaultwarden speichern und danach ueber deine
              DuckDNS-Adresse zur Anmeldung nutzen.
            </p>

            {error && (
              <div className="auth-error" role="alert">
                {error}
              </div>
            )}

            <div className="option-field">
              <label htmlFor="setup-username">Benutzername</label>
              <input
                id="setup-username"
                name="username"
                type="text"
                className="field-input"
                autoComplete="username"
                required
                minLength={3}
                maxLength={32}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>

            <div className="option-field">
              <label htmlFor="setup-password">Passwort (mind. 10 Zeichen)</label>
              <div className="password-wrap">
                <input
                  id="setup-password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  className="field-input"
                  autoComplete="new-password"
                  required
                  minLength={10}
                  maxLength={128}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  className="btn btn-ghost icon-btn"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Passwort verbergen" : "Passwort anzeigen"}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <div className="option-field">
              <label htmlFor="setup-password-confirm">Passwort bestaetigen</label>
              <input
                id="setup-password-confirm"
                name="password_confirm"
                type={showPassword ? "text" : "password"}
                className="field-input"
                autoComplete="new-password"
                required
                minLength={10}
                maxLength={128}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </div>

            <button type="submit" className="btn btn-primary" disabled={submitting}>
              <span>{submitting ? "Lege Konto an..." : "Konto anlegen & anmelden"}</span>
            </button>
          </form>
        )}

        {authStatus.has_users && (
          <form
            method="post"
            action="/api/v1/auth/login"
            autoComplete="on"
            onSubmit={(e) => void handleLogin(e)}
            className="auth-form"
          >
            <div className="auth-heading">
              <Lock size={20} color="var(--accent)" aria-hidden="true" />
              <h2>Anmelden</h2>
            </div>

            {error && (
              <div className="auth-error" role="alert">
                {error}
              </div>
            )}

            <div className="option-field">
              <label htmlFor="login-username">Benutzername</label>
              <input
                id="login-username"
                name="username"
                type="text"
                className="field-input"
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>

            <div className="option-field">
              <label htmlFor="login-password">Passwort</label>
              <div className="password-wrap">
                <input
                  id="login-password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  className="field-input"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  className="btn btn-ghost icon-btn"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Passwort verbergen" : "Passwort anzeigen"}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <label className="toggle-label">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
              />
              <span>Angemeldet bleiben (30 Tage)</span>
            </label>

            <button type="submit" className="btn btn-primary" disabled={submitting}>
              <span>{submitting ? "Pruefe..." : "Anmelden"}</span>
            </button>

            <p className="hint-line">
              {authStatus.can_register_local
                ? "Lokales Netzwerk erkannt: Kontoverwaltung nach Anmeldung verfuegbar."
                : "Zugriff ueber DuckDNS/Proxy: Registrierung und Passwortaenderung sind deaktiviert."}
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
