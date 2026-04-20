---
name: reviewDiffsBeforeCommitAll
description: "Full pre-commit review covering both backend and frontend in parallel. Runs the backend architectural review (spawning background subagents across layers, tests, docs, and queries) and the frontend CLAUDE.md compliance review at the same time, then merges both into one consolidated report."
disable-model-invocation: true
---

Orchestrates the two existing pre-commit skills so backend and frontend are reviewed concurrently, and their results are merged into a single report.

The two child skills have very different shapes:

- **`/reviewDiffsBeforeCommitBackend`** is asynchronous: it spawns many background subagents (`run_in_background: true`) across the affected backend layers, tests, docs, and queries, then waits for their automatic completion notifications before consolidating.
- **`/reviewDiffsBeforeCommitFrontend`** is synchronous and read-only: it just reads every `frontend/**/CLAUDE.md` and the frontend diffs, then emits a compliance report inline.

Because of this asymmetry, do not literally call both skills as if they were symmetric. Instead, follow the phased workflow below: kick off the backend's background agents first (so they run while you do other work), then do the frontend review inline, then wait for the backend agents and merge.

Usage: `/reviewDiffsBeforeCommitAll` (same optional `$ARGUMENTS` as the backend skill: `--tests dir1 dir2 ...` and `--md path1 path2 ...`).

---

## PHASE 1 — Detect scope

Run in parallel:
- `git diff --cached --name-only`
- `git diff --name-only`

Combine and deduplicate. If empty → "No diffs found (staged or unstaged). Nothing to review." and STOP without launching anything.

Split the changed files into:
- **Backend files**: paths starting with `backend/`.
- **Frontend files**: paths starting with `frontend/`.
- **Other**: everything else (report them as "out of scope" at the end; neither child skill reviews them).

Print a short summary to the user: total changed files, backend count, frontend count, other count.

Decide which child reviews to run:
- If there are backend files → run the backend phase.
- If there are frontend files → run the frontend phase.
- If only one side has changes, run only that side and skip the other entirely.
- If neither side has changes (only "other" files) → report "No backend or frontend files to review." and STOP.

---

## PHASE 2 — Kick off the backend review (background)

Only if there are backend files.

Read `.claude/skills/reviewDiffsBeforeCommitBackend/SKILL.md` and execute its **PHASE 1** (diff analysis) and **PHASE 2** (launch all agents) inline, passing through any `--tests` / `--md` values from `$ARGUMENTS`. Every agent the backend skill launches uses `run_in_background: true`, so after this phase you have a fleet of backend subagents running asynchronously.

Do NOT execute the backend skill's PHASE 3 (consolidation) yet — leave the agents running and move on to Phase 3 of *this* skill while they work. This is the whole reason for running "All": the frontend review fills the time the backend agents take.

Print a brief note listing the backend agents launched, then continue immediately to Phase 3.

---

## PHASE 3 — Run the frontend review (foreground, while backend agents work)

Only if there are frontend files.

Read `.claude/skills/reviewDiffsBeforeCommitFrontend/SKILL.md` and execute its workflow inline end-to-end: load every `frontend/**/CLAUDE.md`, map each frontend diff against the rules, and produce the frontend compliance report.

Do NOT print the frontend report to the user yet — hold it in working memory. It will be merged with the backend report in Phase 5.

Important: while executing the frontend review, do **not** poll, check, or wait on the backend agents. They will report back automatically.

---

## PHASE 4 — Wait for backend agents to finish

If backend agents were launched in Phase 2, wait for all of their automatic completion notifications before continuing. Do not call any tool purely to check on them.

If there were no backend files in Phase 1, skip this phase.

---

## PHASE 5 — Merge and present a single consolidated report

Once the frontend phase is done AND all backend agents have returned, produce ONE report with this structure:

```
## Pre-Commit Review Report (Backend + Frontend)

### Executive Summary
- Backend (Group A / new code): X blockers, Y majors, Z minors, W suggestions
- Backend (Group B / pre-existing): X blockers, Y majors, Z minors, W suggestions
- Frontend: X violations, Y ambiguities, Z pass
- Files out of scope (neither backend nor frontend): N — listed at the bottom
- Overall verdict: BLOCK COMMIT / REVIEW BEFORE COMMIT / SAFE TO COMMIT

### Backend
<Backend skill's full consolidated report here — Group A and Group B, per-layer, per-category, exactly as produced by its PHASE 3.>

### Frontend
<Frontend skill's full compliance report here — Scope, CLAUDE.md files consulted, Findings per file, Verdict.>

### Out-of-scope files (not reviewed by either skill)
<bullet list of paths, if any>
```

### Overall verdict rules

Combine the two child verdicts:

- If backend verdict is `BLOCK COMMIT` **or** frontend verdict is `BLOCKED` → overall **BLOCK COMMIT**.
- Else if backend verdict is `REVIEW BEFORE COMMIT` **or** frontend verdict is `NEEDS USER DECISION` → overall **REVIEW BEFORE COMMIT**.
- Else → overall **SAFE TO COMMIT**.

Only Group A backend findings count toward the backend verdict (Group B is informational, same rule as the backend skill).

If one side was skipped because it had no changes, omit that side's section and base the verdict on the side that ran.

---

## Important rules

- Do not run the two child skills sequentially in full — that would serialise all the waiting time. The whole point is overlap: backend agents run in the background while you handle the frontend review on the main thread.
- Do not modify any file. This skill, like its two children, is read-only.
- Never propose edits to any `CLAUDE.md` or `*_guide.md`. If docs seem outdated, that is itself a finding in the report (backend side via md-reviewer, frontend side via the compliance report's notes).
- Pass `$ARGUMENTS` (`--tests`, `--md`) through to the backend phase only. The frontend skill takes no arguments.
- If either child phase crashes or returns nothing, report it explicitly in the Executive Summary and still present whatever the other side produced; do not silently drop a side.
