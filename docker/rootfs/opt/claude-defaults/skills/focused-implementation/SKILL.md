---
name: focused-implementation
description: >-
  Deliver the smallest complete implementation. Modify only required files,
  reuse existing patterns, update docs when needed, and validate changes.
  Use when implementing a feature, fix, or refactor.
---

# Focused implementation

Deliver the smallest complete solution that meets the goal.

## Steps

1. Confirm the goal and the files that must change.
2. Modify only required files. Avoid unrelated refactoring.
3. Reuse existing patterns, helpers, and conventions in the project.
4. Update documentation only when user-facing behavior or commands changed.
5. Run available checks for the area you touched.
6. Review the final diff before reporting completion.

## Rules

- Do not add files unless they have a clear long-term purpose.
- Do not create planning or progress Markdown in the repository.
- Do not claim validation passed unless commands actually ran.
