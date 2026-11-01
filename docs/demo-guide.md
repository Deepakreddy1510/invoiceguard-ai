# Five-minute InvoiceGuard demonstration

Use only synthetic documents. For hosted access, open the **verified provider-assigned HTTPS address** supplied after deployment and sign in with your individual invited account. There is currently no hosted URL or Codex preview. Local startup is documented in the README.

1. **Overview:** show the selected synthetic workspace, persisted invoice outcome counts, separate processing-run and duplicate metrics, and worker heartbeat. Explain that a successful processing run can end in VALIDATED, BLOCKED or NEEDS_REVIEW; technical failure is separate.
2. **Process Invoice:** upload a newly generated invoice, not just a renamed fixture. Watch the real stored timeline, open the PDF, inspect source quotes/page references and field verification. Explain that fallback is active without a Gemini key.
3. **Decision:** open the vendor and PO match, gross calculation, rule results and reservation. A validation reserves capacity; the app never executes payments. A repeated byte-identical upload reuses its run, while a re-exported business duplicate receives a separate blocked assessment without reserving twice.
4. **Exceptions:** open the missing-number demonstration. Compare the source, supply only a number verified from independent synthetic vendor evidence, add a meaningful comment, attest, and submit. Open the new run and previous decision; demonstrate full financial revalidation and attributed correction history. If a scan contains a correct unverified field, explicitly confirm it against evidence. Do not invent missing facts to obtain a green result.
5. **Purchase Orders / Audit:** show cumulative partial-invoice commitments, available capacity, a blocked overrun and persisted reviewer actions. Refresh or restart a service and show the same history. End with the measured extraction limitations rather than an unsupported accuracy claim.

## Prepared expanded workspace

`python -m scripts.seed_workspace --process-examples` creates 18 vendors, 36 POs, eight real baseline partial-invoice runs and eight demonstration submissions: valid digital, different-bytes duplicate, missing field, overrun, real scanned invoice, and three partial invoices. IDs are printed by the command. Repeating the command is safe byte replay and does not reset financial records. The default workspace is `3c54d1c9-a0b2-57c9-bf7c-2d63178807d3`.

For new independent PDFs in a chosen workspace, use `scripts.seed_workspace.document` with public `backend/demo/procurement.json` inputs and a new invoice number/quantity, or create your own invoice. Choose a matching open PO and calculate currency-specific net/tax/gross accurately. Synthetic catalogue POs expire at the end of 2026; later demonstrations need new procurement, not retroactive changes to immutable decisions.

## Cases to explain

- Exact replay: same document/run, another submission, no additional commitment.
- Business duplicate: unique vendor + normalized number, different bytes; BLOCKED, original reservation intact.
- Near duplicate/conflicting identity: review; no automatic additional reservation.
- Overbilling: BLOCKED based on current consuming commitments, even with concurrent workers.
- Missing/ambiguous evidence: NEEDS_REVIEW, never a fabricated value.
- Valid correction: old decision retained, new decision, old hold atomically replaced only after controls pass.
- Rejected correction: hold retained until the reviewer explicitly rejects/releases; rejection is a real BLOCKED disposition, not a fabricated extraction run.
- Provider failure: bounded Gemini adapter failure routes to conservative fallback. A technical OCR/storage failure is FAILED with retry, not a financial approval.

This is an invoice-verification demonstration, not a payment platform or proof of real-world extraction generalization. Live Gemini, actual hosted sign-in and external deployment must be verified with configured credentials before a case-study claim is made.
