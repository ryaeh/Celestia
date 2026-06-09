import { useCallback, useEffect, useState } from "react";

// ---------------------------------------------------------------------------
// Celestia theme system
// Each theme id maps to a `[data-theme="<id>"]` block in App.css that overrides
// the palette tokens. We only store the id; the CSS does the rest. The swatch
// triplet drives the picker preview (cool → mid → warm aura colors).
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
  /** [base, cool aura, warm aura] — used for the picker preview chip. */
  swatch: [string, string, string];
  hint: string;
};

export const THEMES: ThemeMeta[] = [
  { id: "aurora",   label: "Aurora",   tone: "dark",  swatch: ["#0a0912", "#b07bff", "#ff9d7a"], hint: "Warm violet & coral" },
  { id: "twilight", label: "Twilight", tone: "dark",  swatch: ["#080b16", "#7c83ff", "#4fd6e8"], hint: "Violet & cyan" },
  { id: "ember",    label: "Ember",    tone: "dark",  swatch: ["#120c0a", "#ff8a5c", "#ffd27a"], hint: "Amber & coral" },
  { id: "slate",    label: "Slate",    tone: "dark",  swatch: ["#0c0e13", "#6ea8fe", "#9fb8d6"], hint: "Cool & minimal" },
  { id: "moss",     label: "Moss",     tone: "dark",  swatch: ["#07120f", "#3fd6a8", "#b6e88a"], hint: "Calm teal & green" },
  { id: "daylight", label: "Daylight", tone: "light", swatch: ["#f6f2ec", "#7c5cff", "#ff8f6b"], hint: "Soft cream, light" },
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
