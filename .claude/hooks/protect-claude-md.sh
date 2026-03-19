#!/bin/bash
python -c "
import sys, json, os

data = json.load(sys.stdin)
tool_name = data.get('tool_name', '')
tool_input = data.get('tool_input', {})
file_path = tool_input.get('file_path', '').replace('\\\\', '/')

# Only applies to CLAUDE.md files
if not file_path.endswith('CLAUDE.md'):
    sys.exit(0)

SECTION2_MARKER = '## Section 2'

def deny(reason):
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'reason': reason
        }
    }))
    sys.exit(0)

# Determine if this is the root CLAUDE.md or a subdirectory one.
# Root CLAUDE.md: only the filename, no directory separators before it,
# or the parent directory is the project root.
# Subdirectory CLAUDE.md files (layer rules) are fully protected.
parts = file_path.replace('\\\\', '/').rstrip('/').split('/')
claude_idx = len(parts) - 1  # last element is 'CLAUDE.md'
# Check if parent directory is the project root by looking for common
# project root indicators. A simple heuristic: if the CLAUDE.md is NOT
# directly inside the repo root, it is a subdirectory CLAUDE.md.
# We detect root by checking if the parent contains typical root markers
# or by counting depth relative to known structure.
# Simpler approach: root CLAUDE.md has no 'backend' or similar in its path
# before the filename. Most reliable: check if the file is at repo root.
import subprocess
try:
    repo_root = subprocess.check_output(
        ['git', 'rev-parse', '--show-toplevel'],
        stderr=subprocess.DEVNULL
    ).decode().strip().replace('\\\\', '/')
except Exception:
    repo_root = None

if repo_root:
    parent_dir = '/'.join(parts[:-1])
    # Normalize both paths for comparison
    repo_root_norm = repo_root.rstrip('/').lower()
    parent_norm = parent_dir.rstrip('/').lower()
    is_root_claude_md = (parent_norm == repo_root_norm)
else:
    # Fallback: if only filename with no directory, treat as root
    is_root_claude_md = (len(parts) <= 1)

if not is_root_claude_md:
    # Subdirectory CLAUDE.md — fully protected (was general_*_rules.md)
    if tool_name in ('Edit', 'Write'):
        deny('This CLAUDE.md is a layer rules file (subdirectory) and is fully protected. It must never be modified.')
    elif tool_name == 'Bash':
        command = tool_input.get('command', '')
        write_indicators = ['>', 'sed -i', 'tee ', 'mv ', 'cp ', 'rm ', 'del ']
        for indicator in write_indicators:
            if indicator in command:
                deny(f'Bash command appears to modify a protected subdirectory CLAUDE.md via \"{indicator.strip()}\".')
    sys.exit(0)

# From here on, only the root CLAUDE.md is handled.
if tool_name == 'Edit':
    old_string = tool_input.get('old_string', '')
    if not old_string:
        sys.exit(0)

    # Read the current file
    if not os.path.isfile(file_path):
        sys.exit(0)

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    section2_pos = content.find(SECTION2_MARKER)
    if section2_pos == -1:
        deny('Section 2 marker not found in CLAUDE.md — structure may be broken. Edit denied for safety.')

    old_pos = content.find(old_string)
    if old_pos == -1:
        # old_string not found — Edit will fail on its own
        sys.exit(0)

    if old_pos < section2_pos:
        deny('This edit targets Section 1 of CLAUDE.md, which is protected and must not be modified.')

    # Edit is in Section 2 — allow
    sys.exit(0)

elif tool_name == 'Write':
    content_new = tool_input.get('content', '')

    # If file doesn't exist, ensure new CLAUDE.md has Section 2 marker
    if not os.path.isfile(file_path):
        if SECTION2_MARKER not in content_new:
            deny('New CLAUDE.md must contain the Section 2 marker.')
        sys.exit(0)

    with open(file_path, 'r', encoding='utf-8') as f:
        content_old = f.read()

    section2_pos_old = content_old.find(SECTION2_MARKER)
    if section2_pos_old == -1:
        deny('Section 2 marker not found in current CLAUDE.md — structure may be broken. Write denied for safety.')

    section2_pos_new = content_new.find(SECTION2_MARKER)
    if section2_pos_new == -1:
        deny('The new content removes the Section 2 marker from CLAUDE.md. Write denied.')

    section1_old = content_old[:section2_pos_old]
    section1_new = content_new[:section2_pos_new]

    if section1_old != section1_new:
        deny('This write modifies Section 1 of CLAUDE.md, which is protected and must not be changed.')

    # Section 1 is identical — allow
    sys.exit(0)

elif tool_name == 'Bash':
    command = tool_input.get('command', '')
    claude_md_files = ['CLAUDE.md', 'claude.md']
    for fname in claude_md_files:
        if fname in command:
            write_indicators = ['>', 'sed -i', 'tee ', 'mv ', 'cp ', 'rm ', 'del ']
            for indicator in write_indicators:
                if indicator in command:
                    deny(f'Bash command appears to modify a CLAUDE.md file via \"{indicator.strip()}\". Use Edit/Write tools instead.')
    sys.exit(0)

# Unknown tool — allow
sys.exit(0)
"
