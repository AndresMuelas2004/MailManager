#!/bin/bash
python -c "
import sys, json, re

data = json.load(sys.stdin)
file_path = data.get('tool_input', {}).get('file_path', '')

# Normalize backslashes to forward slashes for consistent matching
normalized = file_path.replace('\\\\', '/')
filename = normalized.split('/')[-1] if '/' in normalized else normalized

if re.match(r'^general_\w+_rules\.md$', filename):
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': 'Editing general_*_rules.md files is forbidden. These are non-negotiable architectural rules and must never be modified.'
        }
    }))
"
