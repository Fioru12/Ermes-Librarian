# Northstar Works demo library

This folder contains entirely fictional documents for demonstrating Ermes Knowledge. They are safe to upload to a local library, commit to source control and use in screenshots or automated evaluations.

## Demo flow

1. Create a library named `Northstar Works`.
2. Upload the three Markdown documents in this folder.
3. Keep the assistant policy on `evidence_only` for the first demonstration.
4. Ask the questions in [questions.md](questions.md).
5. Open each citation and verify the document title and section locator.

The expected behaviour is not just a plausible response: each answer should be supported by the selected library. Questions outside these documents should result in an abstention.

## The abstention step needs the evidence verifier

Measured on this corpus on 11 September 2026, and stated here because the demo
script is otherwise misleading: with the shipped defaults the six evidence
questions all answer correctly with the right citation, but the abstention
question (`What is the parental leave policy?`) does **not** abstain. It cites
the annual-leave passage, because a chunk is admitted as evidence when it
shares a single term with the question — here, *leave*.

To demonstrate the abstention, enable the evidence verifier before starting:

```
ERMES_EVIDENCE_VERIFIER=1
ERMES_EVIDENCE_VERIFIER_MODEL=qwen3.5:4b
```

With that, all seven questions behave as this file describes (verified: 6/6
citations correct, abstention with zero citations). The second variable matters
in practice: the verification is a yes/no question repeated per candidate
passage, so it wants a small, fast model. With the 9B model the Ollama
`/api/generate` calls failed on the test machine and the verifier degraded to
"unchecked" — which looks exactly like no verifier at all, apart from a warning
in the log.

## Follow-up questions

With `ERMES_CONVERSATION_MEMORY=1` the chat also handles refinement questions.
After *How much notice is required for annual leave?*, ask simply *And for
remote work?* — the question is rewritten to a standalone one using the last
exchanges, and the answer cites the remote-work section. The rewritten
question is shown in the response metadata (`meta.conversation`), so it is
always visible what the system actually searched for. The conversation is sent
by the browser with each request; the server keeps none of it.

The underlying limitation, and the measurements behind it, are in
`docs/RETRIEVAL_EVALUATION.md` and under T9 in `docs/THREAT_MODEL.md`.

All names, addresses, numbers and policies are fictional.
