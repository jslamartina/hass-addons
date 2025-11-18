# /implement-plan

Act as a senior software engineer working within this repository.
Your task: implement the tasks listed in the plan.

Steps to follow:

1. Open the plan file and locate the next unchecked task, or the section labelled “Phase: Implementation” (or similar).
2. For that task:
   - Review the description, file paths/modules listed, and any dependencies noted.
   - Execute the code changes required (create/update files, run tests, refactor), following project conventions.
   - Run the build/test suite (e.g., `npm test`, `pytest`, `dotnet test`, or your project’s build command).
   - If build/test fails, fix errors or ask for clarification.
   - Mark the task as completed in the plan file (e.g., `[x] Task description`).
   - In your chat output: state the file(s) changed, tests/build status, and task marked completed.
3. After finishing the task, check if there is another unchecked item in the plan.
   - If yes: respond “Ready for next task.”
   - If no: respond “All tasks in plan are complete.”

Constraints:

- Do not modify other tasks in the plan unless explicitly instructed.
- Do not create a new plan file.
- If you encounter ambiguous or missing information (file paths, dependencies, etc), respond with a clarifying question instead of proceeding.
- Do NOT stage or commit changes.
