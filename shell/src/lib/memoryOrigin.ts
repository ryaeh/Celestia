/** Human wording for a memory's origin (T04 provenance). */
export function originLabel(origin?: string): string {
  if (!origin || origin === "unknown") return "";
  if (origin === "user") return "you";
  if (origin === "assistant") return "Celestia";
  if (origin === "consolidation") return "chat summary";
  if (origin === "screen") return "screen";
  if (origin.startsWith("tool:")) return origin.slice(5).replace(/^mcp__/, "MCP ").replace(/_/g, " ");
  return origin;
}
