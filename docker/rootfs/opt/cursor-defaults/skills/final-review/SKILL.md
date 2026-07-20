---
name: final-review
description: >-
  Review work before reporting completion. Inspect the diff, remove temporary
  code, check documentation consistency, and report validation honestly.
  Use before finishing a task or opening a pull request.
---

# Final review

Review your work before you report completion.

## Checklist

1. Inspect the final diff. Remove debug code, dead paths, and accidental edits.
2. Remove duplicated logic introduced during iteration.
3. Confirm documentation matches the real commands and paths.
4. Check error handling on paths you changed.
5. List what was verified, what was assumed, and what was not checked.

## Report format

Keep the closing report short:

| Section | Content |
| --- | --- |
| Changed | Brief list of meaningful changes |
| Verified | Commands that ran and passed |
| Not verified | Checks skipped and why |
| Limits | Environment or scope constraints |

Do not repeat the full plan or implementation walkthrough.
