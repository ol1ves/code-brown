# Agent Flow — Future Work

The previous agent flow (`POST /agent/run`) was removed on 2026-04-26 with the
backend orchestration rewrite.

Reasons:

- Hype signal quality was too weak and often empty.
- Intent -> candidates -> hype -> planner -> fan-out -> summary produced weak results.
- SSE event model grew too large for real consumer usage.

Future rebuild direction:

- Start with single-query agent flow into `run_search`.
- Re-introduce fan-out only with a stronger signal source.
- Reduce SSE model to a small event set (`stage_started`, `stage_completed`, `result`, `done`).

Archived design: [docs/archive/2026-04-25-agent-run-sse-spec.md](archive/2026-04-25-agent-run-sse-spec.md)
