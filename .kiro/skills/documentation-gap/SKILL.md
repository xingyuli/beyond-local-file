---
name: documentation-gap
description: "Documentation gaps: use after implementing or reviewing changes to public CLI commands, options, configuration, APIs, or user-visible behavior, and when users ask to audit, update, or check documentation. Compare affected behavior with the README, docs, and steering; identify evidence-backed gaps and obtain per-file approval before editing."
---

# Documentation gap

Close documentation gaps with an evidence-led, per-file approval loop.

## 1. Set the evidence boundary

- When invoked from `/code-review`, use its explicit comparison range.
- When the user supplies a scope, inspect that scope.
- When the user invokes this skill without a scope, ask them to choose staged changes, all uncommitted changes, or an explicit scope.
- When model-invoked outside a review, inspect the current changes and their affected public surfaces.

Record the changed paths and each affected public CLI command, option, configuration key, API, or user-visible behavior. **Complete when every affected public surface has an evidence source.**

## 2. Discover gaps

Read the evidence and the relevant README, `docs/`, and `.kiro/steering/` files. Identify only gaps supported by the change:

- New or changed public behavior, CLI options, configuration, or APIs.
- New conventions, implicit rules, or lessons that prevent a recurring mistake.
- Steering guidance that would otherwise lead future work away from the intended pattern.
- Missing, stale, or inconsistent integration guidance.

For every gap, capture the changed behavior, the proposed target file, a one-sentence content summary, and the rationale. Treat each target file as one candidate, combining related updates for that file. Report `No documentation gaps found` when there are none. **Complete when every affected surface is either documented, a candidate, or explicitly out of scope.**

## 3. Grill and approve each candidate

For each candidate, use `/grilling` to establish shared understanding one decision at a time. Explain the evidence, proposed update, target file, and rationale. Ask whether to approve, skip, or revise that file; wait for the answer before considering another candidate.

Only an explicit approval authorizes an edit to that candidate file. A skipped candidate remains unchanged. **Complete when every candidate has an explicit decision.**

## 4. Apply approved updates

Edit only approved README, `docs/`, or `.kiro/steering/` files. Keep documentation accurate, concise, and in English. Validate relevant links, command examples, and cross-references after each edit.

Finish with the approved, skipped, and revised outcomes, plus validation results. **Complete when every approved update is validated and every decision is reported.**
