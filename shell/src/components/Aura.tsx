import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Aura — Celestia's mark: a flat moon that changes phase with her state.
// Idle is a still waxing crescent, thinking sweeps through phases, listening
// is a full moon with a ripple, speaking is a full moon that breathes. Pure
// CSS; the moon is drawn in the active theme's --accent-warm.
// ---------------------------------------------------------------------------

export type AuraState = "idle" | "thinking" | "listening" | "speaking";
export type AuraSize = "mark" | "chat" | "brand" | "hero";

type AuraProps = {
  state?: AuraState;
  size?: AuraSize;
  className?: string;
};

export default function Aura({ state = "idle", size = "mark", className }: AuraProps) {
  return (
    <span
      className={cn("aura", `aura-${size}`, className)}
      data-state={state}
      aria-hidden
    >
      <span className="aura-glow" />
      <span className="aura-core" />
      <span className="aura-ring" />
      <span className="aura-ring aura-ring-2" />
    </span>
  );
}
