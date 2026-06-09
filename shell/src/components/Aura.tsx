import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Aura — Celestia's living presence.
// A layered gradient orb that breathes when idle, quickens when thinking,
// ripples when listening, and shimmers when speaking. Pure CSS/animation;
// colors come from the active theme's --aura-* tokens so it adapts per theme.
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
