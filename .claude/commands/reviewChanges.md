Launch the `changes-reviewer` agent to review all current changes (staged, unstaged, and untracked files) since the last commit. Run it in the background.

After launching, your response MUST END IMMEDIATELY. Write a brief message telling the user the agent was launched and that you will report when it finishes — then STOP. Do NOT add any more tool calls.

Do NOT poll, retry, resume, or call any tool after launching the agent. The main thread must be completely idle until the automatic completion notification arrives.
