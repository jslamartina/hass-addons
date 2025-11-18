# /commit-pending

Act as a senior software engineer maintaining this repository.
Your task: stage all modified & new files, craft a high-quality commit message, and run the commit.

Format for the commit message:
$type[(scope)]: short description
Body: one-paragraph explanation of what changed and why.

Allowed types: feat | fix | chore | docs | refactor | test | perf | build | ci
Scope: optional but recommended (e.g., “api”, “ui”, “infra”, “smart-home”)
Example: `feat(infra): add Azure VM Bicep module for monitoring`

Steps to follow:

1. `git add .`
2. Review `git diff --cached` to ensure everything important is included and nothing accidental.
3. Generate the commit message per above format.
4. `git commit -m "<subject>" -m "<body>"`
5. Summarize the commit in the chat: number of files changed, main areas impacted.

Constraints:

- Do not mention this command or logging this action.
- Keep subject line ≤ 50 characters.
- Use imperative mood (“Add”, “Fix”, “Refactor”), not past tense.
- If no meaningful changes detected, respond: “No changes to commit.”
- Ensure the message reflects your coding standards and clarity for the team.
