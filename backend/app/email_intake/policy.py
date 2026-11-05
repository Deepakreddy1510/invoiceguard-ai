"""email-po-review-v1 only restricts automatic validation; never grants capacity."""

POLICY_VERSION = "email-po-review-v1"


def context_for(message, attachment):
    evidence = [
        f
        for f in (attachment.classification or {}).get("evidence", [])
        if f.get("kind") == "po_number"
        and f.get("source") in ("SUBJECT", "BODY")
        and f.get("verified")
    ]
    selected = (attachment.review or {}).get("selected_po_number")
    return {
        "policy_version": POLICY_VERSION,
        "message_id": str(message.id),
        "attachment_id": str(attachment.id),
        "po_evidence": evidence,
        "selected_po_number": selected,
    }


def assess(context, extraction):
    if not context:
        return []
    if context.get("policy_version") != POLICY_VERSION:
        return [
            {
                "rule_id": "EMAIL_POLICY_VERSION",
                "outcome": "REVIEW",
                "explanation": "Unknown email matching policy requires review.",
                "actual": None,
                "expected": POLICY_VERSION,
            }
        ]
    field = (extraction or {}).get("fields", {}).get("po_number", {})
    pdf = field.get("value") if field.get("verified") else None
    refs = {e["value"] for e in context.get("po_evidence", []) if e.get("verified")}
    selected = context.get("selected_po_number")
    if selected in refs:
        refs = {selected}
    problem = len(refs) > 1 or (pdf and refs and pdf not in refs) or (not pdf and bool(refs))
    return [
        {
            "rule_id": "EMAIL_PO_CONTEXT",
            "outcome": "REVIEW" if problem else "PASS",
            "explanation": "Email-only, conflicting or multiple PO claims require review; email claims cannot replace verified PDF fields."
            if problem
            else "Email context does not conflict with the verified PDF PO.",
            "actual": ", ".join(sorted(refs)) or None,
            "expected": pdf,
            "policy_version": POLICY_VERSION,
        }
    ]
