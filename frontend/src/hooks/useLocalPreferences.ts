import { useEffect, useState } from "react";
import type { ThemePreference } from "../types";

interface StoredPreferences {
  theme: ThemePreference;
  recentFormats: string[];
  autoDeleteAfterDownload: boolean;
  defaultStripMetadata: boolean;
}

const STORAGE_KEY = "converter_preferences_v1";

const DEFAULT_PREFS: StoredPreferences = {
  theme: "auto",
  recentFormats: ["webp", "jpg", "png", "pdf", "mp3", "mp4"],
  autoDeleteAfterDownload: false,
  defaultStripMetadata: false,
};

export function useLocalPreferences() {
  const [prefs, setPrefs] = useState<StoredPreferences>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) return { ...DEFAULT_PREFS, ...JSON.parse(raw) };
    } catch {
      // Ignore storage errors in private mode
    }
    return DEFAULT_PREFS;
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    } catch {
      // Ignore
    }
    const root = document.documentElement;
    if (prefs.theme === "auto") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", prefs.theme);
    }
  }, [prefs]);

  const setTheme = (theme: ThemePreference) => setPrefs((p) => ({ ...p, theme }));

  const recordRecentFormat = (fmt: string) =>
    setPrefs((p) => ({
      ...p,
      recentFormats: [fmt, ...p.recentFormats.filter((x) => x !== fmt)].slice(0, 6),
    }));

  const setAutoDeleteAfterDownload = (autoDeleteAfterDownload: boolean) =>
    setPrefs((p) => ({ ...p, autoDeleteAfterDownload }));

  const setDefaultStripMetadata = (defaultStripMetadata: boolean) =>
    setPrefs((p) => ({ ...p, defaultStripMetadata }));

  return {
    prefs,
    setTheme,
    recordRecentFormat,
    setAutoDeleteAfterDownload,
    setDefaultStripMetadata,
  };
}
