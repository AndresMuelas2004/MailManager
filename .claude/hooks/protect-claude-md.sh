#!/bin/bash
python -c "
import sys, json, subprocess

data = json.load(sys.stdin)
tool_name = data.get('tool_name', '')
tool_input = data.get('tool_input', {})
file_path = tool_input.get('file_path', '').replace('\\\\', '/')

# Only applies to CLAUDE.md files
if not file_path.upper().endswith('CLAUDE.MD'):
    # For Bash, check if the command modifies a CLAUDE.md file directly
    # (git commands are allowed — the protection is against editing content, not committing)
    if tool_name == 'Bash':
        command = tool_input.get('command', '')
        if 'CLAUDE.md' in command or 'claude.md' in command:
            stripped = command.strip().lstrip('!').strip()
            is_git = stripped.startswith('git ')
            if not is_git:
                write_indicators = [' > ', ' >> ', 'sed -i', 'tee ', 'mv ', 'cp ', 'rm ', 'del ']
                for indicator in write_indicators:
                    if indicator in command:
                        print(json.dumps({
                            'hookSpecificOutput': {
                                'hookEventName': 'PreToolUse',
                                'permissionDecision': 'deny',
                                'reason': f'Bash command appears to modify a CLAUDE.md file via \"{indicator.strip()}\". All CLAUDE.md files in this project are protected.'
                            }
                        }))
                        sys.exit(0)
    sys.exit(0)

# Resolve project root to scope protection to this repo only
try:
    repo_root = subprocess.check_output(
        ['git', 'rev-parse', '--show-toplevel'],
        stderr=subprocess.DEVNULL
    ).decode().strip().replace('\\\\', '/')
except Exception:
    repo_root = None

if repo_root:
    file_norm = file_path.rstrip('/').lower()
    root_norm = repo_root.rstrip('/').lower() + '/'
    if not file_norm.startswith(root_norm):
        sys.exit(0)

# Deny any Edit or Write to any CLAUDE.md inside the project
if tool_name in ('Edit', 'Write'):
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'reason': 'All CLAUDE.md files in this project are protected and must not be modified directly.'
        }
    }))
    sys.exit(0)

sys.exit(0)
"
