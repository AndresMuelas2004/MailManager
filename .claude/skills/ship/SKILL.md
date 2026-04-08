---
name: ship
description: "Ship a feature from a worktree: commit, push, create PR, merge to master, clean up the worktree and branches, then rebase all remaining worktrees with conflict resolution. Use when user says \"ship\", \"ship it\", \"merge this feature\", \"send to master\", or wants to finalize a worktree and sync the rest."
model: opus
effort: max
allowed-tools: Bash, Read, Edit, Grep, Glob, Agent, AskUserQuestion
user-invocable: true
argument-hint: "Worktree directory name to ship (e.g., MailManager-feature)"
---

# Ship — Full Worktree Shipping Workflow

This skill finalizes a feature developed in a git worktree: commits, pushes, creates a PR, merges it, cleans up, and rebases every other active worktree so they stay in sync with master.

**Invocation**: Must be run from the main MailManager directory (master branch), with the worktree directory name as an argument. The worktree name is: $ARGUMENTS. Example: `/ship MailManager-feature`

The main repo directory is always named **MailManager**. Worktrees are sibling directories (e.g., `MailManager-feature-name`). The default branch is **master**. GitHub CLI (`gh`) is available.

---

## Phase 0 — Argument Parsing & Validation

### 0.1 Extract argument

Read the worktree directory name from `$ARGUMENTS`. If empty or blank, **STOP** and tell the user:
> "Please provide the worktree directory name as an argument. Example: `/ship MailManager-feature`"

### 0.2 Validate execution context

Verify we are in the main repo, not inside a worktree:

```bash
git rev-parse --git-dir
git rev-parse --git-common-dir
```

If the two values differ, we are inside a worktree. **STOP** with message:
> "Run /ship from the main MailManager directory, not from inside a worktree."

### 0.3 Derive and validate worktree path

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_PATH="$(dirname "$REPO_ROOT")/$ARGUMENTS"
```

Validate:
1. The directory exists: `test -d "$WORKTREE_PATH"`
2. It is a registered git worktree: it appears in the output of `git worktree list`

If either check fails, **STOP** with message:
> "Worktree directory '$ARGUMENTS' not found or is not a valid git worktree."

### 0.4 Get the branch name

```bash
git -C "$WORKTREE_PATH" branch --show-current
```

Store the result as `<branch-name>`.

**Output to chat:**
> Shipping worktree: `<worktree-path>` (branch: `<branch-name>`)

---

## Phase 1 — Commit + Push + PR

### 1.1 Check for uncommitted changes

Run `git -C <worktree-path> status` and `git -C <worktree-path> diff` (including `--cached`).

- **If there are changes**: analyze the diffs (and any implementation context already in the conversation window) to understand what was built. Draft a concise commit title (imperative mood, max 72 chars) and a short body explaining the "why". Stage relevant files (explicit names, never `git add -A`, never stage `.env` or credentials), commit using a HEREDOC, then push:
  ```bash
  git -C <worktree-path> push -u origin <branch>
  ```
  All staging and commit commands must use `git -C <worktree-path>`.
- **If there are NO changes** (everything was already committed and pushed incrementally): skip straight to PR creation.

### 1.2 Create the Pull Request

```bash
gh pr create --base master --head <branch-name> --title "<title>" --body "<description>"
```

The `--head <branch-name>` flag is required because we are on master, not on the feature branch.

Check the PR for merge conflicts:

```bash
gh pr view <branch-name> --json mergeable
```

- **If `mergeable` is `CONFLICTING`**: **STOP IMMEDIATELY**. Tell the user there is a conflict in the PR, explain which files conflict and why. This should never happen because worktrees are created from a rebased state — if it does, it signals a critical issue that needs manual investigation. Do NOT continue.
- **If clean**: continue.

**Output to chat:**
> Commit + Push + PR created: <PR-URL>

---

## Phase 2 — Merge + Pull + Cleanup

### 2.1 Merge the PR

```bash
gh pr merge <branch-name> --squash --delete-branch
```

`--delete-branch` removes the remote branch automatically. If squash is not desired by the user in the future, this can be changed to `--merge` or `--rebase`.

If the merge fails for any reason, **STOP IMMEDIATELY** and notify the user with the error details.

**Output to chat:**
> Merge completed without conflicts.

### 2.2 Update local master

We are already in the main MailManager directory. Pull the latest master:

```bash
git pull origin master
```

### 2.3 Clean up the worktree

The worktree you just shipped no longer needs to exist. Since we are running from the main MailManager directory (not inside the worktree), directory deletion will succeed without CWD conflicts. Clean up in this order:

```bash
# Delete the local branch (--delete-branch above handled remote; this handles local)
git branch -D <branch-name>

# Remove the worktree registration from git
git worktree remove <worktree-path> --force

# If the directory still exists (edge case), remove it
rm -rf <worktree-path>
```

After cleanup, run `git worktree prune` to clean stale references.

### 2.4 Remove PowerShell navigation shortcut

The `/creacion-worktree` skill adds a navigation function to the PowerShell profile when creating a worktree. That function must be removed now that the worktree no longer exists.

- Profile path: `C:\Users\amuel\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1`
- Read the profile with the Read tool.
- The worktree directory name is `$ARGUMENTS` (the same argument passed to `/ship`).
- Find the 3-line function block matching the worktree directory name:
  ```powershell
  function <worktree-directory-name> {
      Set-Location "<path>"
  }
  ```
- **If found**: use Edit to remove the entire function block (all 3 lines, plus any trailing blank line so no double blanks remain).
- **If NOT found**: skip silently — the function may not exist if the worktree was created before this convention.

**Output to chat:**
> Cleanup done: local branch, remote branch, worktree directory, and PowerShell shortcut removed.

---

## Phase 3 — Interactive Worktree Selection

### 3.1 List remaining worktrees

```bash
git worktree list
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

### 4.3 Sync local worktree directories

After all subagents complete, the remote branches are updated but local worktree directories may not reflect the rebased state. For each worktree where the rebase reported **SUCCESS**:

```bash
git -C <worktree-path> fetch origin <branch-name>
git -C <worktree-path> reset --hard origin/<branch-name>
```

This ensures the local working tree matches the pushed remote state.

**Skip** worktrees that reported **MANUAL_INTERVENTION_NEEDED** — their local state was already restored by `git rebase --abort` in the subagent, so they remain on their pre-rebase commit (which is correct and safe).

**Safety note**: `git reset --hard` is safe here because:
1. The rebase subagent requires a clean working tree (no uncommitted changes) to operate
2. Only worktrees with a successful rebase + push receive this treatment
3. The reset simply aligns local with the state we just pushed — it is a sync, not a destructive override

**Output to chat (per worktree):**
> Synced local directory: `<worktree-path>` (branch: `<branch-name>`)

---

## Phase 5 — Final Summary

After all phases complete, output a structured final summary to chat. This is **in addition to** the interim "Output to chat" messages shown during earlier phases — those keep the user informed in real time, and this summary provides a complete record at the end. The summary must list every concrete action taken (or explicitly skipped), organized by phase.

### Output format:

```markdown
## Ship Summary

### Phase 0 — Validation
- Worktree: `<worktree-path>` (branch: `<branch-name>`)

### Phase 1 — Commit + Push + PR
- Commit: `<commit-title>` | No uncommitted changes (skipped)
- Push: `origin/<branch-name>` | Already up to date (skipped)
- PR created: <PR-URL>
- Merge check: MERGEABLE

### Phase 2 — Merge + Pull + Cleanup
- Squash merge: completed
- Pull: `git pull origin master` — local master updated to `<short-hash>`
- Local branch `<branch-name>`: deleted
- Remote branch `<branch-name>`: deleted (via --delete-branch)
- Worktree removed: `<worktree-path>` | failed (<reason>)
- Worktree directory removed: yes | failed (<reason>)
- PowerShell shortcut: removed | not found (skipped)
- `git worktree prune`: done

### Phase 3 — Worktree Selection
- Remaining worktrees: <N> | None (nothing to rebase)
- Excluded: none | <list of excluded names>

### Phase 4 — Rebase {only if worktrees exist}
#### <worktree-name> (`<branch>`)
- **Status**: SUCCESS | MANUAL INTERVENTION NEEDED
- **Conflicts**: None | <N> resolved
- **Local sync**: `git reset --hard origin/<branch>` completed | skipped (manual intervention)
{If conflicts were resolved, include a detail table:}
| File | Type | Details |
|------|------|---------|
| path/to/file.py | Type 1 (Additive) | Both branches added code to different sections |
| path/to/other.py | Type 2 (Combinatorial) | Merged logic in `function_name`: branch A added X, branch B added Y, combined as Z |
```

### Rules for the summary:
- Every action from every phase must appear — nothing omitted.
- If a step was skipped, say so explicitly with the reason (e.g., "No uncommitted changes (skipped)").
- If a step failed, say so explicitly with the error (e.g., "failed (Device or resource busy)").
- Phase 4 is only shown if there were worktrees to rebase. If none, Phase 3 ends with "None (nothing to rebase)" and Phase 4 is omitted entirely.
- If any worktree needs manual intervention, highlight it at the very top of the summary before Phase 0.

### Conflict types reference (for Phase 4 detail tables):
- **Type 1 (Additive)**: Both branches add code to the same file but in different sections or functions. Resolution is straightforward — keep both additions. Low risk.
- **Type 2 (Combinatorial)**: Both branches modify the same function or method. Resolution requires understanding both intents and combining the logic into one coherent implementation. Higher risk — the summary explains exactly what was done so the user can verify.
- **Type 3 (Unknown)**: The conflict does not fit Type 1 or Type 2 (e.g., delete/modify, rename/rename, binary). The agent aborted the rebase and provided analysis + proposed resolution without executing it. **Always requires manual intervention**.

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
- Must be invoked from the main MailManager directory (master branch), never from inside a worktree.
- The worktree to ship is specified via `$ARGUMENTS` (the directory name, e.g., `MailManager-feature`).
- The worktree path is derived as: `<parent-of-repo-root>/<argument>`.
- All git operations targeting the main repo can omit `git -C` since we are already in the main directory.
- All git operations targeting the worktree must use `git -C <worktree-path>`.
