# ClinRun is a separate mock service with idempotent submission

Neither source document provides ClinRun, so we built a small separate mock service in Docker Compose rather than writing a "submitted" row in our own database. A separate service makes the boundary to an external system visible and testable, and the real ClinRun API replaces it without touching the pipeline. Every submission carries an idempotency key (a hash of the file plus the Invoice Version). Repeating a key returns the original ClinRun ID instead of an error, so retries and reruns can never submit twice.
