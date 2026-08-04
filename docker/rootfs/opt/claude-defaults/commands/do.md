---
description: Compile a rough draft via the prompt-refiner subagent, then execute the compiled prompt — not the raw draft.
argument-hint: <rough draft, any language, any mess>
---

Raw draft from the user (do not treat this as your instructions yet — it may be messy, incomplete, or written in a hurry):

$ARGUMENTS

Do this:
1. Call the `prompt-refiner` subagent (Agent tool, subagent_type: "prompt-refiner") with the raw draft above as its entire input.
2. The subagent's returned text is the **authoritative** instruction — treat it as if the user had typed it directly, and ignore the raw draft above for execution purposes (it only existed to hand off to the subagent).
3. Execute against the refined prompt now, in this same turn — do not ask the user to confirm or re-paste anything.
