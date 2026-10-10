import { openUrl } from "@tauri-apps/plugin-opener";
import type { OllamaPull } from "../api";

/** Open the Ollama download page in the system browser (Tauri), or a new tab in plain `vite`. */
export function openDownload(url: string): void {
  openUrl(url).catch(() => {
    window.open(url, "_blank", "noopener");
  });
}

function gb(bytes: number): string {
  return bytes >= 1024 ** 3
    ? `${(bytes / 1024 ** 3).toFixed(1)} GB`
    : `${Math.max(1, Math.round(bytes / 1024 ** 2))} MB`;
}

type PullProgressProps = {
  pull: OllamaPull;
  onCancel?: () => void;
};

/** Live download progress for the model pull — aggregated across the model's layers. */
export function PullProgress({ pull, onCancel }: PullProgressProps) {
  const pct = pull.percent;
  const many = pull.models.length > 1;
  const label = pull.current
    ? `Downloading ${pull.current}${many ? ` (${pull.index + 1} of ${pull.models.length})` : ""}`
    : "Downloading…";
  return (
    <div className="ollama-progress">
      <div className="ollama-progress-head">
        <span>{label}</span>
        {pct !== null && <span>{pct}%</span>}
      </div>
      <div
        className="ollama-bar"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct ?? undefined}
      >
        <div
          className={pct === null ? "ollama-bar-fill ollama-bar-indeterminate" : "ollama-bar-fill"}
          style={pct === null ? undefined : { width: `${pct}%` }}
        />
      </div>
      <div className="ollama-progress-foot">
        <span>
          {pull.total > 0 ? `${gb(pull.completed)} / ${gb(pull.total)} · ` : ""}
          {pull.status}
        </span>
        {onCancel && (
          <button type="button" className="ollama-link" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}
