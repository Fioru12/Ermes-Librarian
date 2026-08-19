# Meridian Precision Works demo library

A second, entirely fictional demo library — a small manufacturing quality
management system — used alongside `demo-corpus/` (Northstar Works) to show
that Ermes Knowledge's retrieval never crosses library boundaries.

## Demo flow

1. Create a library named `Meridian Precision Works`.
2. Upload the two Markdown documents in this folder.
3. Keep the assistant policy on `evidence_only`.
4. With **this** library selected, ask a Northstar-only question such as
   *"How much notice is required for annual leave?"* — the assistant must
   abstain: the answer exists in another library, and that library is not
   searched. This is the isolation moment the single-library demo cannot
   show on its own.
5. Ask a question this library actually answers, e.g. *"Who approves the
   disposition of a nonconforming batch?"* and confirm the citation points
   to `nonconformity-procedure.md`.

All names, addresses, batch numbers and policies are fictional.
