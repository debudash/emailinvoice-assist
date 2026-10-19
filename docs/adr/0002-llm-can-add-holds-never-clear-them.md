# The LLM can add Holds but never clear the hard checks

With no human gate (ADR-0001), submitting to ClinRun is outward-facing and hard to undo, so the submit/hold Decision is a hybrid: deterministic hard checks (Unmatched, Ambiguous, Price Variance, uncertain Context, site not linked to study, totals inconsistent, unverified extraction, Possible Duplicate) force a Hold, and only when none fire does the LLM review the Invoice, where it may still Hold but can never turn a failed check into Submit. The brief asks for an "AI decision"; this keeps the AI's judgement in the loop while making a False Submit impossible to cause by a prompt slip, and it is why the eval gate requires zero False Submits.

## Considered Options

- **LLM decides with rule results as input:** rejected; more "AI", but one bad generation could submit a held invoice.
- **Rules only, LLM writes the explanation:** rejected; predictable, but not the AI decision the brief asks for, and it would miss concerns the rules don't encode.
