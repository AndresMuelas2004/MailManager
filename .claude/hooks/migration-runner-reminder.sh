#!/bin/bash
python -c "
import sys, json

data = json.load(sys.stdin)
tool_input = data.get('tool_input', {})
file_path = tool_input.get('file_path', '').replace('\\\\', '/')

# Only trigger when editing Alembic migration version files
if 'backend/database/migrations/versions/' in file_path and file_path.endswith('.py'):
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PostToolUse',
            'additionalContext': (
                'MIGRATION SYNC REMINDER: You just edited an Alembic migration file. '
                'Remember to update backend/database/migrations/runner.py to match: '
                'add the equivalent DDL statement to _DDL_STATEMENTS and update the '
                'alembic_version stamp to this migration revision. The fallback runner '
                'must always reflect the same final schema as Alembic.'
            )
        }
    }))
    sys.exit(0)

# No match
sys.exit(0)
"
