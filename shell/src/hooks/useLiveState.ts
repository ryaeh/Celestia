import { useEffect, useState } from "react";
import { connectStateChannel, type LiveState } from "../api";

export type LiveStateResult = {
  /** Latest merged state. Empty object until the first frame arrives. */
  state: LiveState;
  /** Whether the /ws/state socket is currently connected. While false, callers
   *  may fall back to polling fetchStatus(). */
  connected: boolean;
};

/**
 * Subscribes to the /ws/state live-state channel for the lifetime of the
 * component and exposes the merged state plus link status. Frames are partial
 * (only changed keys), so we merge each into the running value rather than
 * replacing it. One socket per mount; cleaned up on unmount.
 */
export function useLiveState(): LiveStateResult {
  const [state, setState] = useState<LiveState>({});
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const stop = connectStateChannel(
      (partial) => setState((prev) => ({ ...prev, ...partial })),
      setConnected,
    );
    return stop;
  }, []);

  return { state, connected };
}
