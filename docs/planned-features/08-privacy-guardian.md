# 08 — Local privacy guardian

**Pitch:** Invert the screen/PC-watching power for *defense*. A local auditor that flags
suspicious activity — "this app just opened your camera", "this process is reading your
clipboard repeatedly", "an installer is writing outside its folder" — running entirely
on-device. A companion that protects you.

> **Build decision (Jun 2026).** There's an irony at the core: a privacy guardian that has
> to watch your screen constantly, where classifier false-positives turn into alert fatigue
> (the "annoying antivirus" failure). So the full guardian is **deprioritized**, and the
> cheap 80% ships first as small, standalone safety utilities — no daemon required:
> - **Secrets scrubbing** (regex pass over OCR/chat before storage — already in the ideas
>   backlog) + **clipboard-exposure warnings**. These deliver most of the protective value
>   with none of the watching cost.
> - The **full anomaly guardian** (camera/mic/outbound-net monitoring) only makes sense once
>   01's observation daemon exists — at which point it's *the same daemon with a security
>   classifier*, not a separate build. Treat it as a late, optional specialization, not a
>   committed epic.

## Why this is a Celestia feature

The same capabilities that make Celestia powerful (sees the screen, watches the system) are
exactly what a privacy guardian needs — and because it's local, the guardian itself isn't a
new data-exfiltration risk the way a cloud monitor would be.

## How it works

- **Reuses:** the **01** observation daemon — the guardian is that same loop with a
  *security classifier* instead of a helpfulness classifier.
- **Signals:** clipboard-access frequency, camera/mic activation, new outbound-network
  processes, writes outside expected paths (cross-checks `scope.py` protected paths),
  unexpected autostart entries.
- **Response tiers:** notify → recommend → (with approval) remediate via the **04**
  executor (e.g. revoke, kill, quarantine).
- **New: small rules layer** — declarative "watch for X → severity Y" rules, plus an
  LLM pass for anomalies that don't match a rule.

## Data & config

```yaml
guardian:
  enabled: false
  watch: [clipboard, camera_mic, outbound_net, protected_path_writes, autostart]
  min_severity_to_notify: medium
  allow_remediation: false   # requires scoped+ and per-action approval
```

## Security & privacy

- Observe-only by default; remediation is opt-in and gated (`scoped`+, per-action approval
  via 04).
- The guardian's own findings are local-only and honour the global pause toggle.
- Must avoid false alarms fatigue — tune severities conservatively.

## Integrates with

- **01 Ambient (●●●):** literally the same daemon; build 01 first, specialize here.
- **04 Autonomy (●●●):** remediation runs as a gated plan.
- **05 Macros (●●):** scheduled security sweeps as a ritual.
- **07 Hotkey (●●):** "what is this process / is this safe?" on demand.

## Effort / risk

Medium *if* 01 exists (mostly classifier + rules). System-signal collection on Windows
(process/network/device hooks) is the new, fiddly part and must stay within the lazy-import
rule. Phase 5 specialization.

## Open questions

- How deep into OS hooks is acceptable vs. lightweight polling?
- Where's the line between "helpful guardian" and "annoying antivirus"? Severity defaults
  are everything.
