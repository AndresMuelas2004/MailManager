#!/bin/bash
python -c "
import sys, json, re

data = json.load(sys.stdin)
tool_name = data.get('tool_name', '')
tool_input = data.get('tool_input', {})
file_path = tool_input.get('file_path', '').replace('\\\\', '/')

def deny(reason):
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'reason': reason
        }
    }))
    sys.exit(0)

if tool_name in ('Edit', 'Write'):
    # Case-insensitive check to cover all variations (CLAUDE.md, claude.MD, etc.)
    if file_path.lower().endswith('claude.md'):
        deny('All CLAUDE.md files are fully protected and must never be modified.')

elif tool_name == 'Bash':
    command = tool_input.get('command', '')
    # Case-insensitive search for any mention of claude.md in the command
    if re.search(r'claude\.md', command, re.IGNORECASE):
        deny('Bash commands that reference CLAUDE.md files are blocked. These files are fully protected.')

sys.exit(0)
"
