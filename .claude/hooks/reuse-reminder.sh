#!/bin/bash
python -c "
import sys, json

data = json.load(sys.stdin)
tool_input = data.get('tool_input', {})
file_path = tool_input.get('file_path', '').replace('\\\\', '/')

# Condition 1: email provider clients
client_files = (
    'backend/core/email/gmail_client.py',
    'backend/core/email/outlook_client.py',
)
if any(file_path.endswith(c) for c in client_files):
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PostToolUse',
            'additionalContext': (
                'REUSE DIRECTIVE: Before proposing any changes to this file, '
                'audit all existing methods — especially private helpers (_*). '
                'Extract shared logic into internal helpers rather than duplicating '
                'it across methods. Prefer composing small, focused helpers over '
                'large monolithic methods. Keep it simple, professional, and DRY.'
            )
        }
    }))
    sys.exit(0)

# Condition 2: database query files
if 'backend/database/queries/' in file_path and file_path.endswith('.py'):
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PostToolUse',
            'additionalContext': (
                'REUSE DIRECTIVE: Before writing or modifying queries in this file, '
                'review all existing query constants. Avoid creating similar standalone '
                'queries when an existing one can be parameterized or reused. Keep the '
                'query surface area minimal, professional, and DRY.'
            )
        }
    }))
    sys.exit(0)

# No match — exit silently
sys.exit(0)
"
