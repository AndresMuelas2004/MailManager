---
allowed-tools: Agent
description: Launch parallel dead-code analysis on one or more directories
argument-hint: [DirectoryLayer-1] [DirectoryLayer-2] [...]
---

The user has provided one or more directory paths as arguments: $ARGUMENTS

For **each** directory path provided, launch a separate `dead-code-finder` agent **in parallel** using the Agent tool. All agents must be launched in a single message with multiple tool calls — never sequentially.

Rules:
1. Split the arguments by whitespace to get the list of directories.
2. Launch exactly **one** agent per directory — no more, no less.
3. All agents must run **in parallel** (all tool calls in one message).
4. Each agent must use `subagent_type: "dead-code-finder"`.
5. Each agent's prompt must instruct it to analyze only its assigned directory.
6. Set `run_in_background: true` on each agent so they run concurrently without blocking.
7. When all agents finish, present a unified summary to the user with the results from each directory.

Example — if the user runs `/searchDeadCode backend/api backend/core backend/database`, you must launch 3 agents simultaneously:

- Agent 1: dead-code-finder for `backend/api`
- Agent 2: dead-code-finder for `backend/core`
- Agent 3: dead-code-finder for `backend/database`
