> Implementation status (2026-11-01): the integrated backend, review, authenticated frontend and deployment image are now implemented and locally verified. This document retains the approved seven-phase sequence as historical design context. See [current verification](completion-verification.md) for actual results and [hosting](../deploy/README.md) for the remaining credentialed release checks. No external deployment has occurred.

# Revised seven-phase plan

Phases 1 and 2 are implemented locally; live Gemini verification remains pending a configured key. See phase-2-verification.md. Each phase ends with executed tests, a real application walkthrough, recorded results and review. Do not create disconnected scaffolds.

1. **Foundation:** workspace/vendor/PO/item migration; repeatable realistic procurement seed; FastAPI procurement API and connected React screen; database constraints and browser smoke test.
2. **Early full vertical slice:** add document, invoice/revision, run/stage/event, decision and commitment persistence with the minimal durable Python worker. Connect real React PDF upload, page text/OCR, genuine Gemini structured extraction with source evidence, conservative fallback, explicit seeded PO matching, required/vendor/currency/arithmetic/balance checks and atomic reservation. Display persisted stages and saved outcomes. Execute at least two invoice layouts. No sample filename routing or hardcoded decisions. Design independent evaluation expectations before tuning extraction.
3. **Financial controls:** complete tax/item controls, duplicate identities, partial billing, reservation lifecycle, synchronized concurrency tests. Add worker fencing when concurrent/stale writes become possible.
4. **Workflow and review:** immutable reviewer corrections, revalidation, explicit hold/release, bounded retries, audit history and crash recovery tests.
5. **Complete UI:** evidence viewer, exception queue, historical dashboard, PO allocations and audit views. Count unique invoices separately from submissions, retries and reviews.
6. **Independent evaluation and hardening:** held-out extraction evaluation with measured results, real-provider verification, authorization, recovery, resource limits and full browser regression.
7. **Deployment:** hosted authentication, persistent storage, managed database, API and worker, release migrations, external smoke test, interview rehearsal and candidate-narrated video. No deployment until authorized.

## Authentication and evaluator access

Use **Auth0 Universal Login**, OIDC Authorization Code + PKCE with the maintained React SDK. FastAPI verifies asymmetric JWT signatures via cached JWKS, issuer, audience and expiry. Map the verified subject to server-managed workspace memberships; never trust a browser-selected workspace without authorization. Keep tokens in memory rather than localStorage. Restrict callback/logout URLs and allowed origins. Registration alone grants no workspace access.

Invite each evaluator's email before the interview, create a dedicated synthetic workspace and assign only that membership. Send the application URL; the evaluator signs in with their own account. No shared admin password, API key or other users' records. Test two evaluator identities against cross-workspace access. Reset only an authorized demo workspace with audit records. Confirm provider setup before deployment; credentials remain in environment secret settings.

Phase 1 is unauthenticated local synthetic development only. Documented API, frontend and database bind to loopback. APP_ENVIRONMENT other than local refuses API startup; this is a development guard, not production authentication. Never expose this build publicly. Implement hosted authentication before evaluator hosting.

## Duplicate semantics

- **Exact-document replay:** workspace/hash and idempotency key return the existing run/result and an 'Already uploaded' link. A submission receipt can be recorded without inventing processing events. Same key/different bytes returns 409. No new commitment.
- **Same business invoice, different bytes:** conservative vendor/invoice-number identity links to the canonical invoice. Record a distinct duplicate assessment and show 'Blocked: duplicate business invoice' with the original link. Do not replace the canonical validated outcome with a duplicate attempt's block. Conflicting facts require review before merging.
- **Suspicious near-duplicate:** similar identifiers or vendor/date/amount create review candidates with evidence, not a confirmed block. No reservation until required identity review is resolved.
- **Missing invoice number:** provisional identity and review, never a fabricated number.

Tests cover renamed bytes, re-exported PDFs, different vendors/same number, significant punctuation/leading zeros, conflicting totals, same-key conflicts, near matches, simultaneous duplicates and retries. Canonical invoice metrics exclude confirmed duplicate attempts; provisional identities are reported separately until resolved. Preserve all submission/run events.

## Commitment lifecycle

States: **RESERVED, HELD, RELEASED, SETTLED**. RESERVED, HELD and SETTLED consume capacity; RELEASED does not. Settlement is optional and requires an authorized external AP event; validation never means payment.

- Create RESERVED only after all required checks pass, atomically with decision and completion event.
- Reprocessing the same revision reuses its commitment.
- A validated correction atomically releases/replaces the old reservation. Lock invoice and affected POs in stable ID order; exclude the invoice's own old reservation when calculating replacement capacity.
- An uncertain/blocked reassessment moves the existing reservation to HELD until an explicit disposition; a new uncertain invoice has no reservation.
- Release requires an authorized cancellation/rejection/resolution, reason and audit event. Worker failure never frees capacity.
- Settled commitments cannot be modified by ordinary review; reversal/credit handling is future scope.

Available gross = authorization minus RESERVED, HELD and SETTLED consumption. Zero overrun tolerance. All capacity mutations lock the same PO rows and recheck current amounts and quantities. Unique business identity and one-consuming-commitment-per-invoice partial indexes complement locks. No database transaction spans OCR/model calls. Decision, commitment, review and completion changes roll back together. Test competing partials, duplicate processing, crash-after-commit, correction replacement, hold/release, rollback and stale workers.

## AI extraction and independent evaluation

Gemini is a functional core adapter, not a decorative option. Use a provider-independent Pydantic schema, nulls for unknowns, source page/quote/coordinates, recorded model/prompt versions, evidence checks, bounded timeout/retry and rate-limit handling. Financial decisions remain deterministic. Fallback performs real text/OCR extraction and conservative field parsing; unresolved facts require human review. Provider mocks verify failure paths, not extraction correctness.

Create development fixtures and a separately held-out corpus before prompt tuning. Independently record expected fields and page evidence. Vary layout, vendor, column order, pagination, scan quality and tax modes; include missing facts. Keep expectations out of prompts and processing logic. Report field correctness, unsupported extractions, abstentions, review rate and technical failures with numerators/denominators, fixture IDs and normalization rules. Separate live Gemini, fallback and human-corrected outcomes. Record latency only when measured. No extraction figures are claimed in Phase 1.

## Observable history and maintainability

Every displayed stage comes from a persisted started/completed/failed/skipped event. Skips include reasons; no animation may imply work occurred. Retry/review runs reference parent and revision. Reconstruct state after browser reload. Unique invoice metrics do not count runs. Use one modular backend, one database queue and one worker; defer Redis, microservices and generic plugin frameworks. Implement reliability mechanisms alongside the workflow and failure tests they protect.
