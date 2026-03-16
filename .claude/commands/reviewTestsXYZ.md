---
name: reviewTestsXYZ
disable-model-invocation: true
---

Audit test quality, review tests, check test coverage, and identify test gaps for each of the following directories — run all reviews in parallel, one independent review per directory:

$ARGUMENTS

CRITICAL EXECUTION RULE — follow this EXACTLY:

1. Launch all review agents in parallel (one test-quality-reviewer agent per directory) using `run_in_background: true`.
2. After launching, your response MUST END IMMEDIATELY. Write a brief message telling the user the agents were launched and that you will report when they finish — then STOP. Do NOT add any more tool calls.
3. Do NOT poll, retry, resume, or call any tool after launching the agents. The main thread must be completely idle until the automatic completion notifications arrive.
4. Only when ALL agents have completed (via automatic notifications), summarize the results to the user.
