---
name: ship
description: "Ship a feature from a worktree: commit, push, create PR, merge to master, clean up the worktree and branches, then rebase all remaining worktrees with conflict resolution. Use when user says \"ship\", \"ship it\", \"merge this feature\", \"send to master\", or wants to finalize a worktree and sync the rest."
model: opus
effort: max
allowed-tools: Bash, Read, Edit, Grep, Glob, Agent, AskUserQuestion
---

# Ship — Full Worktree Shipping Workflow

This skill finalizes a feature developed in a git worktree: commits, pushes, creates a PR, merges it, cleans up, and rebases every other active worktree so they stay in sync with master.

The main repo directory is always named **MailManager**. Worktrees are sibling directories (e.g., `MailManager-feature-name`). The default branch is **master**. GitHub CLI (`gh`) is available.

---

## Phase 1 — Commit + Push + PR

### 1.1 Check for uncommitted changes

Run `git status` and `git diff` (including `--cached`).

- **If there are changes**: analyze the diffs (and any implementation context already in the conversation window) to understand what was built. Draft a concise commit title (imperative mood, max 72 chars) and a short body explaining the "why". Stage relevant files (explicit names, never `git add -A`, never stage `.env` or credentials), commit using a HEREDOC, then push:
  ```bash
  git push -u origin <branch>
  ```
- **If there are NO changes** (everything was already committed and pushed incrementally): skip straight to PR creation.

### 1.2 Create the Pull Request

```bash
gh pr create --base master --title "<title>" --body "<description>"
```

Check the PR for merge conflicts:

```bash
gh pr view --json mergeable
```

- **If `mergeable` is `CONFLICTING`**: **STOP IMMEDIATELY**. Tell the user there is a conflict in the PR, explain which files conflict and why. This should never happen because worktrees are created from a rebased state — if it does, it signals a critical issue that needs manual investigation. Do NOT continue.
- **If clean**: print the PR URL and continue.

**Output to chat:**
> Commit + Push + PR created: <PR-URL>

---

## Phase 2 — Merge + Pull + Cleanup

### 2.1 Merge the PR

```bash
gh pr merge --squash --delete-branch
```

`--delete-branch` removes the remote branch automatically. If squash is not desired by the user in the future, this can be changed to `--merge` or `--rebase`.

If the merge fails for any reason, **STOP IMMEDIATELY** and notify the user with the error details.

**Output to chat:**
> Merge completed without conflicts.

### 2.2 Update local master

Navigate to the main MailManager directory and pull:

```bash
git -C <path-to-MailManager> checkout master
git -C <path-to-MailManager> pull origin master
```

### 2.3 Clean up the worktree

The worktree you just shipped no longer needs to exist. Clean up in this order:

```bash
# Delete the local branch (--delete-branch above handled remote; this handles local)
git -C <path-to-MailManager> branch -D <branch-name>

# Remove the worktree registration from git
git -C <path-to-MailManager> worktree remove <worktree-path> --force

# If the directory still exists (edge case), remove it
rm -rf <worktree-path>
```

After cleanup, run `git -C <path-to-MailManager> worktree prune` to clean stale references.

**Output to chat:**
> Cleanup done: local branch, remote branch, and worktree directory removed.

---

## Phase 3 — Interactive Worktree Selection

### 3.1 List remaining worktrees

```bash
git -C <path-to-MailManager> worktree list
```

Filter out the main MailManager directory — only show actual worktrees (sibling directories with branches other than master).

### 3.2 Ask the user which to exclude

Use `AskUserQuestion` with this structure:

- **Question**: "The following worktrees exist:\n\n{formatted list with path and branch for each}\n\nDo you want to exclude any from the rebase + conflict resolution?"
- **Options**: First option is "No, include all worktrees". Do NOT add individual worktree options — the user types the names to exclude as free text in a second option labeled "Type worktree names to exclude (space-separated)".

If the user selects "No, include all worktrees", proceed with all of them.
If the user types names, parse them and exclude those worktrees.

If there are NO remaining worktrees, skip to the final summary and inform the user that everything is clean.

---

## Phase 4 — Rebase Remaining Worktrees

### 4.1 Launch subagents

For each non-excluded worktree, launch a `rebase-conflicts-solver` subagent **in parallel** (all in one message with multiple Agent tool calls). Each subagent receives:

- The absolute path to the worktree directory
- The branch name checked out in that worktree
- The name of the base branch: `master`

**Output to chat:**
> Subagents launched for worktrees: {list of worktree names}

### 4.2 Collect results

Wait for all subagents to complete. Each returns a structured conflict report.

---

## Phase 5 — Final Summary

Present a clear summary for each worktree that was rebased:

### Format per worktree:

```
### {worktree-name} ({branch})
**Status**: Rebase successful | Needs manual intervention
**Conflicts**: None | N conflicts resolved

{If conflicts were resolved:}
| File | Type | Details |
|------|------|---------|
| path/to/file.py | Type 1 (Additive) | Both branches added code to different sections |
| path/to/other.py | Type 2 (Combinatorial) | Merged logic in `function_name`: branch A added X, branch B added Y, combined as Z |
```

### Conflict types explained:
- **Type 1 (Additive)**: Both branches add code to the same file but in different sections or functions. Resolution is straightforward — keep both additions. Low risk.
- **Type 2 (Combinatorial)**: Both branches modify the same function or method. Resolution requires understanding both intents and combining the logic into one coherent implementation. Higher risk — the summary explains exactly what was done so the user can verify.

If any worktree needs manual intervention, highlight it clearly at the top of the summary.

---

## Error Handling

- **PR conflict**: Stop immediately, explain, do not merge.
- **Merge failure**: Stop immediately, explain the error.
- **Cleanup failure**: Warn but continue to the rebase phase (cleanup can be retried).
- **Rebase subagent failure**: Report which worktree failed and why. The other worktrees' results are still valid.
- **No worktrees remaining**: Report success and that there is nothing to rebase.

## Important Rules

- Never force push (`--force` / `-f`) unless the user explicitly asks.
- Never skip hooks (`--no-verify`).
- Never stage `.env`, credentials, or secret files.
- The main repo path is always derived from the current worktree by finding the MailManager directory among siblings.
- All git operations targeting the main repo use `git -C <path-to-MailManager>` to avoid changing directories.
