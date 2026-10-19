# No human gate before matching; hold on uncertain Context instead

The starter README makes user confirmation of metadata a hard gate before line-item matching; the brief says humans are not a required gate and QC happens after the AI decides. We follow the brief: invoices run straight through to a Decision, and the starter's gate survives only as a Hold when any Context field's computed confidence is below threshold, in which case matching is skipped until a reviewer corrects the Context. A reader who knows the starter will expect a confirmation step; its absence is deliberate, because a wrong Context selects the wrong Catalog and the only safe place to stop is where the system itself is unsure.

## Considered Options

- **Starter's hard gate on every invoice:** rejected; contradicts the brief's core principle and puts a human in front of invoices the AI resolves confidently.
- **Configurable gate (off by default, pausing on low confidence):** agreed first, then dropped. With the gate on, an invoice pauses on the same trigger and at the same stage as the uncertain-Context Hold, and the reviewer does the same thing, so the setting would change nothing observable.
