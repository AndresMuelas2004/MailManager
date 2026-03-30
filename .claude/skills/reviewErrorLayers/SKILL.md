---
name: reviewErrorLayers
description: "Audit error handling compliance and coverage for each of the following directories — run all reviews in parallel, one independent review per directory."
argument-hint: [DirectoryLayer-1] [DirectoryLayer-2] [...]
disable-model-invocation: true
---

Audit error handling compliance and coverage for each of the following directories — run all reviews in parallel, one independent review per directory:

Usage: /reviewErrorLayers backend/api backend/core backend/database

$ARGUMENTS

CRITICAL EXECUTION RULE — follow this EXACTLY:

1. Parse $ARGUMENTS into individual paths (space-separated).
2. Launch one error-structure-reviewer agent per path, all in parallel, using `run_in_background: true`.
3. After launching, your response MUST END IMMEDIATELY. Write a brief message telling the user the agents were launched and that you will report when they finish — then STOP. Do NOT add any more tool calls.
4. Do NOT poll, retry, resume, or call any tool after launching the agents. The main thread must be completely idle until the automatic completion notifications arrive.
5. Only when ALL agents have completed (via automatic notifications), summarize the results to the user.
