import { useCallback, useEffect, useState } from "react";

// ---------------------------------------------------------------------------
// Celestia theme system
// Each theme id maps to a `[data-theme="<id>"]` block in App.css that overrides
// the palette tokens. We only store the id; the CSS does the rest. The swatch
// drives the picker preview: a hard two-tone split of ground | accent.
// ---------------------------------------------------------------------------

export type ThemeId =
  | "aurora"
  | "twilight"
  | "ember"
  | "slate"
  | "moss"
  | "daylight";

export type ThemeMeta = {
  id: ThemeId;
  label: string;
  tone: "dark" | "light";
  /** [ground, accent, moon] — the picker chip shows ground | accent. */
  swatch: [string, string, string];
  hint: string;
};

export const THEMES: ThemeMeta[] = [
  { id: "aurora",   label: "Aurora",   tone: "dark",  swatch: ["#151311", "#e8946a", "#e2bd78"], hint: "Charcoal & clay" },
  { id: "twilight", label: "Twilight", tone: "dark",  swatch: ["#10131a", "#8fb3e8", "#e6d29a"], hint: "Night ink & starlight" },
  { id: "ember",    label: "Ember",    tone: "dark",  swatch: ["#16110d", "#eda55f", "#f0d49a"], hint: "Hearth & amber" },
  { id: "slate",    label: "Slate",    tone: "dark",  swatch: ["#131416", "#9ab4cf", "#cfc6b4"], hint: "Graphite & steel" },
  { id: "moss",     label: "Moss",     tone: "dark",  swatch: ["#111410", "#9cc49a", "#d8cf92"], hint: "Moss & sage" },
  { id: "daylight", label: "Daylight", tone: "light", swatch: ["#f3eee5", "#a34a24", "#8a6414"], hint: "Paper & ink" },
];

export const DEFAULT_THEME: ThemeId = "aurora";

const STORAGE_KEY = "celestia.shell.theme";

function isThemeId(v: string | null): v is ThemeId {
  return !!v && THEMES.some((t) => t.id === v);
}

export function getStoredTheme(): ThemeId {
  if (typeof window === "undefined") return DEFAULT_THEME;
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (isThemeId(stored)) return stored;
  } catch {
    /* ignore */
  }
  return DEFAULT_THEME;
}

/** Apply a theme to <html> and persist it. Safe to call before React mounts. */
export function applyTheme(id: ThemeId): void {
  if (typeof document !== "undefined") {
    const meta = THEMES.find((t) => t.id === id);
    document.documentElement.dataset.theme = id;
    document.documentElement.style.colorScheme = meta?.tone ?? "dark";
  }
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* ignore */
  }
}

/** Read the stored theme and apply it immediately (call once at startup). */
export function initTheme(): ThemeId {
  const id = getStoredTheme();
  applyTheme(id);
  return id;
}

export function useTheme(): [ThemeId, (id: ThemeId) => void] {
  const [theme, setThemeState] = useState<ThemeId>(getStoredTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const setTheme = useCallback((id: ThemeId) => setThemeState(id), []);
  return [theme, setTheme];
}
