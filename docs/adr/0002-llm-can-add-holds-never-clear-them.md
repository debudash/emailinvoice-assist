# The LLM can add Holds but never clear the hard checks

With no human gate (ADR-0001), submitting to ClinRun is outward-facing and hard to undo, so the submit/hold Decision is a hybrid: deterministic hard checks (Unmatched, Ambiguous, Price Variance, uncertain Context, site not linked to study, totals inconsistent, unverified extraction, Possible Duplicate) force a Hold, and only when none fire does the LLM review the Invoice, where it may still Hold but can never turn a failed check into Submit. The brief asks for an "AI decision"; this keeps the AI's judgement in the loop while making a False Submit impossible to cause by a prompt slip, and it is why the eval gate requires zero False Submits.

## Considered Options

- **LLM decides with rule results as input:** rejected; more "AI", but one bad generation could submit a held invoice.
- **Rules only, LLM writes the explanation:** rejected; predictable, but not the AI decision the brief asks for, and it would miss concerns the rules don't encode.

## Amendment (2026-10-19, S1): the review always runs

The LLM review runs on every Invoice, not only when no hard check fires, because it writes the
rationale for every Decision. It is told the outcome the hard checks determine, and whether a
Reviewer has corrected the Context. The guarantee is unchanged: the outcome is computed in code, any
finding means Hold, and the review can only add an `llm_concern`. A test asserts that a review saying
"all fine" leaves a hard-check Hold in place.
