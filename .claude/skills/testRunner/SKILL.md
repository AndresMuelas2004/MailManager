---
name: testRunner
description: "Run tests for each of the following directories — launch all test runners in parallel, one independent agent per directory."
argument-hint: [DirectoryTest-1] [DirectoryTest-2] [DirectoryTest-3]
disable-model-invocation: true
---

Run tests for each of the following directories — launch all test runners in parallel, one independent agent per directory:

$ARGUMENTS

CRITICAL EXECUTION RULE — follow this EXACTLY:

1. Launch one `tests-runner` agent per directory using `run_in_background: true`, all in parallel. Pass the directory path to each agent so it knows which test suite to run.
2. After launching, your response MUST END IMMEDIATELY. Write a brief message telling the user the agents were launched and that you will report when they finish — then STOP. Do NOT add any more tool calls.
3. Do NOT poll, retry, resume, or call any tool after launching the agents. The main thread must be completely idle until the automatic completion notifications arrive.
4. Only when ALL agents have completed (via automatic notifications), summarize the results to the user.
