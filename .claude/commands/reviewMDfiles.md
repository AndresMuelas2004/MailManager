---
name: reviewMDfile
disable-model-invocation: true
---

Review Markdown documentation for accuracy, completeness, and clarity by cross-referencing source code.

Usage: `/reviewMDfile directory1 directory2 ...`

Each argument is a .md path. The agent will find and review all `.md` files inside that directory recursively.

Directories to review:

$ARGUMENTS

CRITICAL EXECUTION RULE — follow this EXACTLY:

1. Parse $ARGUMENTS into individual directory paths (space-separated).
2. Launch one `md-reviewer` agent per directory, all in parallel, using `run_in_background: true` with `subagent_type: "md-reviewer"`. Pass the directory path as the prompt for each agent.
3. After launching, your response MUST END IMMEDIATELY. Write a brief message listing the directories being reviewed and that you will report when all agents finish — then STOP. Do NOT add any more tool calls.
4. Do NOT poll, retry, resume, or call any tool after launching the agents. The main thread must be completely idle until the automatic completion notifications arrive.
5. Only when ALL agents have completed (via automatic notifications), summarize the results to the user.
