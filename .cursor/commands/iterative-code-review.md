# Iterative Code Review

Review the pending git changes and perform an in-depth technical code review using the following guidelines.

Steps:

1. **CRITICAL**: Start with a clean slate. Assume no knowledge of previous code review or context about the code change.
2. Perform the Code Review as outlined in the [Code Review Guidelines](#code-review-guidelines).
3. Generate any artifacts and save to working files according to [conventions](/.cursor/rules/_00-rules-prefix.mdc).
4. Repeat steps 1-3, ensuring especially that step is adhered to, for a total of **FIVE** iterations.
5. After **FIVE** iterations, generate a final summary aggregating the results of all **FIVE** iterations.

## Code Review Guidelines

Please perform an in-depth technical code review of the pending git changes in this repository, following both general and project-specific guidelines. Your review should be structured and actionable.

### General Code Review Guidelines

- Ensure code is readable and maintainable: Use clear naming, appropriate comments, and keep functions/methods short and focused.
- Enforce SOLID principles (Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion) throughout the codebase.
- Apply DRY (Don't Repeat Yourself): Refactor duplicated logic and promote reuse where possible.
- Verify adherence to good architectural practices: Maintain separation of concerns, modular code, and layered design patterns as appropriate.
- Ensure error/exception handling is robust and consistently implemented.
- Check all code for security best practices, avoiding credential leaks, unsafe data handling, or injection vulnerabilities.
- Validate that all input/output is sanitized, encoded, and that “fail safe” defaults are in place.

### Project-Specific Requirements

- Every new function must include both entry and exit logging, with log configuration set from central config (never log secrets or sensitive data).
- All Python changes must trigger the rebuild process; config or static changes require only a restart—validate workflow compliance.
- Never edit/create any “ignore” files (.gitignore, .dockerignore, etc.). If lint errors arise, fix the underlying code, not the ignore files.
- Verify all code passes linting (`npm run lint`) and correct formatting before changes are merged.
- Confirm tests exist (preferably unit tests) for all new behaviors; avoid untested logic.
- For markdown or documentation changes, enforce formatting via Prettier and markdownlint conventions, ensuring concise and non-redundant docs.
- For MQTT and Home Assistant integration, check that discovery, cleanup, and entity management follow project rules.
- Ensure environment variables and secrets are handled via Home Assistant options/secrets, not hardcoded or exposed.

### Review Output Format

- Begin with a bulleted summary of strengths found in the changes.
- List specific findings (by file/line if possible) with references to violated general or project-specific rules.
- Reference relevant guideline or `.mdc` file for each major point.
- End with prioritized, actionable recommendations to address any identified issues.

If you encounter ambiguous code, violation of rules, or potential improvements, note them clearly and cite related documentation for developer reference.
