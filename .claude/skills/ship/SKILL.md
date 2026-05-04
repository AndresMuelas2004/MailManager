---
name: ship
description: "Ship a feature from a worktree: commit, push, create PR, merge to master, clean up the worktree and branches, then rebase all remaining worktrees with conflict resolution. Use when user says \"ship\", \"ship it\", \"merge this feature\", \"send to master\", or wants to finalize a worktree and sync the rest."
model: opus
effort: max
allowed-tools: Bash, Read, Edit, Grep, Glob, Agent, AskUserQuestion
user-invocable: true
argument-hint: "[worktree-dir] (e.g., feature-name)"
---

# Ship — Full Worktree Shipping Workflow

This skill finalizes a feature developed in a git worktree: commits, pushes, creates a PR, merges it, cleans up, and rebases every other active worktree so they stay in sync with master.

**Invocation**: Must be run from the main MailManager directory (master branch), with the worktree directory name as an argument. The worktree name is: $ARGUMENTS. Example: `/ship feature-name`

The main repo directory is always named **MailManager**. Worktrees are sibling directories named directly after the feature (e.g., `feature-name`, `fix-bug-123`) — there is no `MailManager-` prefix. The default branch is **master**. GitHub CLI (`gh`) is available.

---

## Phase 0 — Argument Parsing & Validation

### 0.1 Extract argument

Read the worktree directory name from `$ARGUMENTS`. If empty or blank, **STOP** and tell the user:
> "Please provide the worktree directory name as an argument. Example: `/ship feature-name`"

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

### 1.2 Create or reuse the Pull Request

Before creating a new PR, check whether one already exists for this exact branch — a previous `/ship` run may have aborted between PR creation and merge, in which case `gh pr create` would fail with `a pull request for branch "<branch-name>" already exists`.

```bash
gh pr list --head <branch-name> --state open --json number,url
```

- **If the output contains a PR for `<branch-name>`**: reuse it. Capture its URL/number and skip the `gh pr create` call. The `--head <branch-name>` filter must match the branch being shipped exactly — never auto-pick up an open PR for any other branch.
- **If the output is empty**: create a new PR:

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
> Commit + Push + PR ready: <PR-URL>  *(created | reused existing)*

---

## Phase 2 — Merge + Pull + Cleanup

The cleanup order matters: **the worktree must be removed before the local branch can be deleted, and the local branch must be deleted before the remote branch is removed**. Otherwise `git branch -D` errors with "branch in use by worktree" and that error masks the remote deletion (so passing `--delete-branch` to `gh pr merge` ends up doing neither). The steps below enforce that order explicitly.

### 2.1 Merge the PR

```bash
gh pr merge <branch-name> --squash
```

**Do NOT pass `--delete-branch` here.** It would try to delete the local branch first, which fails because the worktree still has it checked out, and that masks the remote deletion. Branch deletion (local then remote) happens in 2.4 and 2.5 below, in the correct order.

If the merge fails for any reason, **STOP IMMEDIATELY** and notify the user with the error details.

**Output to chat:**
> Merge completed without conflicts.

### 2.2 Update local master

We are already in the main MailManager directory. Pull the latest master with `--ff-only` so an unexpectedly divergent local master fails loudly instead of producing a silent merge commit:

```bash
git pull --ff-only origin master
```

If `--ff-only` rejects (local master has commits not on origin/master, which should never happen in this workflow), **STOP IMMEDIATELY** and report the divergence to the user — do not auto-resolve.

### 2.3 Remove the worktree

The worktree no longer needs to exist. Remove the git registration first, then the directory:

```bash
git worktree remove <worktree-path> --force
```

`git worktree remove --force` does two things at once: it deletes the directory contents AND removes the registration from `.git/worktrees/<name>`. On Windows, when the directory cannot be deleted because some process holds an open handle, git will still print a "Permission denied" / "failed to delete" error — but the registration is usually removed anyway, leaving an orphan empty directory on disk. Verify with `git worktree list`.

If the directory is gone, jump to **2.4**.

If the directory is still on disk, also try:

```bash
rm -rf <worktree-path>
```

If `rm -rf` fails too with `Device or resource busy` / `Permission denied`, follow the **Locked Directory Recovery** procedure below before continuing.

#### Locked Directory Recovery (Windows)

Some other process has an open handle on the worktree path — typically its current working directory (CWD) — which prevents Windows from deleting the directory entry even though it is empty. The order below has been tried and verified to work; follow it exactly.

**Step 1 — Identify the processes whose CWD is inside the worktree.**

Sysinternals `handle.exe` is not assumed to be installed. Use the PowerShell snippet below (it reads each running process' PEB via `NtQueryInformationProcess` to extract the CWD — the only reliable way on Windows without third-party tools):

```powershell
$ErrorActionPreference = 'Stop'
$peb = @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class PebReader {
  [DllImport("ntdll.dll")] public static extern int NtQueryInformationProcess(IntPtr h, int c, ref PROCESS_BASIC_INFORMATION pbi, int len, out int rl);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool ReadProcessMemory(IntPtr h, IntPtr addr, IntPtr buf, int sz, out int read);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr OpenProcess(int access, bool inh, int pid);
  [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
  [StructLayout(LayoutKind.Sequential)] public struct PROCESS_BASIC_INFORMATION { public IntPtr R1; public IntPtr PebBase; public IntPtr R2a; public IntPtr R2b; public IntPtr Pid; public IntPtr R3; }
  public static string GetCwd(int pid) {
    IntPtr h = OpenProcess(0x0410, false, pid); if (h == IntPtr.Zero) return null;
    try {
      var pbi = new PROCESS_BASIC_INFORMATION(); int rl;
      if (NtQueryInformationProcess(h, 0, ref pbi, Marshal.SizeOf(pbi), out rl) != 0 || pbi.PebBase == IntPtr.Zero) return null;
      byte[] buf = new byte[8]; int read;
      var gch = GCHandle.Alloc(buf, GCHandleType.Pinned);
      try { if (!ReadProcessMemory(h, (IntPtr)((long)pbi.PebBase + 0x20), gch.AddrOfPinnedObject(), 8, out read)) return null; } finally { gch.Free(); }
      IntPtr pp = (IntPtr)BitConverter.ToInt64(buf, 0); if (pp == IntPtr.Zero) return null;
      byte[] uni = new byte[16]; gch = GCHandle.Alloc(uni, GCHandleType.Pinned);
      try { if (!ReadProcessMemory(h, (IntPtr)((long)pp + 0x38), gch.AddrOfPinnedObject(), 16, out read)) return null; } finally { gch.Free(); }
      short uLen = BitConverter.ToInt16(uni, 0); IntPtr uBuf = (IntPtr)BitConverter.ToInt64(uni, 8);
      if (uLen <= 0 || uBuf == IntPtr.Zero) return null;
      byte[] s = new byte[uLen]; gch = GCHandle.Alloc(s, GCHandleType.Pinned);
      try { if (!ReadProcessMemory(h, uBuf, gch.AddrOfPinnedObject(), uLen, out read)) return null; } finally { gch.Free(); }
      return Encoding.Unicode.GetString(s);
    } finally { CloseHandle(h); }
  }
}
'@
Add-Type -TypeDefinition $peb -Language CSharp
$target = "<WORKTREE_PATH_WITH_BACKSLASHES>"
foreach ($p in (Get-Process)) {
  try {
    $cwd = [PebReader]::GetCwd($p.Id)
    if ($cwd -and $cwd -like "*$target*") {
      $ci = Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)" -ErrorAction SilentlyContinue
      [PSCustomObject]@{ PID=$p.Id; Name=$p.Name; CWD=$cwd; Cmd=$ci.CommandLine }
    }
  } catch {}
} | Format-List
```

**Step 2 — Classify each process and act.** The lockers are almost always the same set on this machine:

| Process pattern | Action | Why |
|---|---|---|
| `glance-mcp` (any process whose name matches `glance-mcp` and whose CWD is inside the worktree — typically several from the `npx → cmd → glance-mcp.mjs` tree per Claude session) | Kill with `Stop-Process -Id <pid> -Force` | Orphan MCP servers from previous Claude Code sessions launched in this worktree. Safe to terminate. |
| `cmd /c postgres.exe -D "C:/Program Files/PostgreSQL/16/data"` (PID of the postmaster wrapper) | **DO NOT kill with `Stop-Process`.** Use the clean stop in Step 3. | This is the shared local PostgreSQL server. A forced kill can corrupt in-flight transactions and violates `common_mistakes.md #3`. |
| Anything else | Kill with `Stop-Process -Id <pid> -Force` AND notify the user in chat with one line: `Killed unexpected locker: PID=<pid> Name=<name> Cmd=<cmdline>`. The user wants to know about novel offenders so future runs can predict them. | These should not normally appear; surfacing them lets the user investigate or extend this list. |

Apply the kills in any order; only PostgreSQL is special.

**Step 3 — Stop PostgreSQL cleanly (only if it appeared in Step 1).**

```powershell
& "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" stop -D "C:\Program Files\PostgreSQL\16\data" -m fast
```

`-m fast` rolls back open transactions and shuts down ordered — it does not corrupt data. Any other process currently connected to the DB will get a connection error and need to reconnect, so warn the user before doing this if there is any chance a long transaction is in flight.

**Step 4 — Delete the orphan directory.**

```bash
rmdir "<WORKTREE_PATH>"
```

Now that no process holds the CWD handle, this succeeds.

**Step 5 — Restart PostgreSQL from a safe CWD.**

The new postmaster must inherit a CWD outside any worktree. Run from the main MailManager directory:

```powershell
Set-Location "<REPO_ROOT>"
& "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" start -D "C:\Program Files\PostgreSQL\16\data" -l "C:\Program Files\PostgreSQL\16\data\log\startup.log"
```

Verify it came back up:

```powershell
& "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" status -D "C:\Program Files\PostgreSQL\16\data"
```

**Output to chat:**
> Worktree directory locked. Killed N glance-mcp processes, restarted PostgreSQL cleanly, deleted directory.

If PostgreSQL was not in the locker list, omit Steps 3 and 5.

### 2.4 Delete the local branch

Now that the worktree is gone, the branch is no longer "in use" and can be deleted:

```bash
git branch -D <branch-name>
```

Then prune any stale worktree refs:

```bash
git worktree prune
```

### 2.5 Delete the remote branch

```bash
git push origin --delete <branch-name>
```

Verify:

```bash
git ls-remote --heads origin "refs/heads/<branch-name>"
```

- **Empty output**: deletion confirmed.
- **Branch still listed**: **WARN** the user that the remote branch could not be deleted, but continue to the next phase.

**Output to chat:**
> Remote branch `<branch-name>`: deleted (verified) | WARNING: could not delete

### 2.6 Remove PowerShell navigation shortcut

The `/creacion-worktree` skill adds a navigation function to the PowerShell profile when creating a worktree. That function must be removed now that the worktree no longer exists.

- **Resolve the profile path dynamically** — never hardcode it. The actual path depends on the Windows user account and can be redirected by OneDrive:
  ```bash
  powershell -NoProfile -Command "Write-Output \$PROFILE"
  ```
  Capture the output as `<profile-path>`.
- Read `<profile-path>` with the Read tool.
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
> Cleanup done: worktree removed, local branch deleted, remote branch deleted, PowerShell shortcut removed.

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

### 4.1 Check for uncommitted changes

Before launching any rebase subagent, inspect each non-excluded worktree for uncommitted changes:

```bash
git -C <worktree-path> status --porcelain
```

- **If all worktrees are clean**: continue directly to 4.2.
- **If any worktree has uncommitted changes**: use `AskUserQuestion` to ask:

> "Los siguientes worktrees tienen cambios sin commitear ni pushear:\n\n{list with name and branch of each dirty worktree}\n\n¿Quieres que haga commit + push de cada uno antes de iniciar el rebase + resolución de conflictos?"

With exactly two options:
1. "Sí, commit + push antes de rebasear"
2. "No, excluir esos worktrees del rebase"

**If the user chooses option 1 (commit + push):**
For each dirty worktree, invoke the `/commit-push` skill in the context of that worktree (using `git -C <worktree-path>` for all git commands within that worktree). All commits and pushes must complete before launching any rebase subagents.

**If the user chooses option 2 (exclude):**
Remove those worktrees from the rebase list and output to chat for each one:
> Excluido del rebase: `<worktree-name>` (branch: `<branch-name>`) — tiene cambios sin commitear.

**Rationale**: The rebase + conflict resolution process only operates on committed code. WIP changes that are not committed are invisible to the rebase and cannot be checked against incoming conflicts, which may cause silent data loss or conflicts.

### 4.2 Launch subagents

For each non-excluded worktree, launch a `rebase-conflicts-solver` subagent **in parallel** (all in one message with multiple Agent tool calls). Each subagent receives:

- The absolute path to the worktree directory
- The branch name checked out in that worktree
- The name of the base branch: `master`

**Output to chat:**
> Subagents launched for worktrees: {list of worktree names}

### 4.3 Collect results

Wait for all subagents to complete. Each returns a structured conflict report.

### 4.4 Sync local worktree directories

After all subagents complete, the remote branches are updated but local worktree directories may not reflect the rebased state. For each worktree where the rebase reported **SUCCESS**:

```bash
git -C <worktree-path> fetch origin <branch-name>
git -C <worktree-path> pull --ff-only origin <branch-name>
```

`--ff-only` succeeds in the happy path (the rebase subagent left the worktree on a state that is a strict ancestor of `origin/<branch-name>`) and **fails loudly** when there is unexpected divergence — for example, a commit made locally in the worktree between the subagent's push and this step, or a file edited outside the normal flow. On rejection, do **NOT** fall back to `git reset --hard`:

1. Report the affected worktree with the exact `git pull` error.
2. Leave the local state intact (no automatic recovery).
3. Continue with the remaining worktrees — one divergent worktree must not block the others.

**Skip** worktrees that reported **MANUAL_INTERVENTION_NEEDED** — their local state was already restored by `git rebase --abort` in the subagent, so they remain on their pre-rebase commit (which is correct and safe).

**Why `--ff-only` and not `--hard`**: the project's parent `CLAUDE.md` forbids `git reset --hard` in any automated workflow because it silently destroys uncommitted edits and local commits made outside the normal flow. `--ff-only` reaches the same desired state (local matches remote) when nothing unexpected happened, and surfaces the anomaly when something did — without any data loss.

**Output to chat (per worktree):**
> Synced local directory: `<worktree-path>` (branch: `<branch-name>`)  *or*
> Divergence detected, left intact: `<worktree-path>` — <error>; please reconcile manually.

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
- Pull: `git pull --ff-only origin master` — local master updated to `<short-hash>`
- Worktree removed: `<worktree-path>` | required Locked Directory Recovery (killed N glance-mcp + cleanly restarted PostgreSQL) | failed (<reason>)
- Local branch `<branch-name>`: deleted
- `git worktree prune`: done
- Remote branch `<branch-name>`: deleted (verified) | WARNING: could not delete
- PowerShell shortcut: removed | not found (skipped)

### Phase 3 — Worktree Selection
- Remaining worktrees: <N> | None (nothing to rebase)
- Excluded: none | <list of excluded names>

### Phase 4 — Rebase (only if worktrees exist)
#### <worktree-name> (`<branch>`)
- **Status**: SUCCESS | MANUAL INTERVENTION NEEDED
- **Conflicts**: None | <N> resolved
- **Local sync**: `git pull --ff-only origin <branch>` completed | divergence — left intact (<error>) | skipped (manual intervention)
(If conflicts were resolved, include a detail table:)
| File | Type | Details |
|------|------|---------|
| path/to/file.py | Type 1 (Additive) | Both branches added code to different sections |
| path/to/other.py | Type 2 (Combinatorial) | Merged logic in `function_name`: branch A added X, branch B added Y, combined as Z |
```

### Rules for the summary:
- Every action from every phase must appear — nothing omitted.
- If a step was skipped, say so explicitly with the reason (e.g., "No uncommitted changes (skipped)").
- If a step failed, say so explicitly with the error (e.g., "failed (Device or resource busy)").
- If Locked Directory Recovery ran, list every unexpected (non-glance-mcp, non-PostgreSQL) process that was killed — the user wants to track novel offenders.
- Phase 4 is only shown if there were worktrees to rebase. If none, Phase 3 ends with "None (nothing to rebase)" and Phase 4 is omitted entirely.
- If any worktree needs manual intervention, highlight it at the very top of the summary before Phase 0.

### Conflict types reference (for Phase 4 detail tables):
- **Type 1 (Additive)**: Both branches add code to the same file but in different sections or functions. Resolution is straightforward — keep both additions. Low risk.
- **Type 2 (Combinatorial)**: Both branches modify the same function or method. Resolution requires understanding both intents and combining the logic into one coherent implementation. Higher risk — the summary explains exactly what was done so the user can verify.
- **Type 3 (Semantic Duplication)**: Both branches independently created or modified code that serves the same or very similar purpose. Detected post-rebase by performing a **full-diff comparison** of everything each branch changed since they diverged, **across every language and every file** (Python, TypeScript/TSX, JavaScript, SQL, Markdown, configuration, migrations, etc. — not just Python). Covers same-file duplicates, same-name cross-file duplicates, different-name semantic equivalents (e.g., both branches created a helper to query the same DB table or a React hook wrapping the same endpoint under different names), and **intra-function duplication** (similar blocks of logic injected into pre-existing functions on each side, invisible to a definition-level scan). Auto-fixed when safe; flagged for manual intervention when logic diverges. This pass runs only after Step 3 has resolved all textual conflicts — correctness first, efficiency second.
- **Type 4 (Migration Chain Fork)**: Two Alembic migration files share the same `down_revision`, forking the migration chain. Invisible during development — only fails when `alembic upgrade head` runs in deployment. Auto-fixed for linear chains (renumbered); manual intervention for complex chains.
- **Type 5 (Unknown)**: The conflict does not fit any recognized type (e.g., delete/modify, rename/rename, binary). The agent aborted the rebase and provided analysis + proposed resolution without executing it. **Always requires manual intervention**.

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
- The worktree to ship is specified via `$ARGUMENTS` (the directory name, e.g., `feature-name`).
- The worktree path is derived as: `<parent-of-repo-root>/<argument>`.
- All git operations targeting the main repo can omit `git -C` since we are already in the main directory.
- All git operations targeting the worktree must use `git -C <worktree-path>`.
