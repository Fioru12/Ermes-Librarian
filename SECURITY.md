# Security policy

## Scope

Ermes Knowledge processes files that may contain confidential business information. Security issues affecting authentication, library isolation, document access, uploads, secrets, audit data or the LLM/provider boundary are in scope.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability and do not include documents, credentials, access tokens or personal data in a report.

Until a dedicated security contact is published, report privately to the repository owner through the contact information in the GitHub profile. Include:

- a concise description of the impact;
- reproducible steps using synthetic data only;
- affected version or commit;
- any mitigation already identified.

An acknowledgement and remediation plan should be provided before public disclosure is discussed.

## Deployment expectations

- Keep `.env`, uploaded documents, `storage/`, backups and logs out of source control.
- Use a secret manager for production credentials and rotate credentials exposed to a terminal, commit or ticket.
- Keep local LLM endpoints bound to localhost or a private authenticated network.
- Enable an external provider only after an administrator has approved the library's data policy.
- Treat every imported document as untrusted input.

## Current limitations

The current MVP is designed for a controlled local or single-tenant deployment. Before a multi-user production rollout, complete OIDC integration, enforce server-side ACL propagation during retrieval, perform a threat-model review and run external security testing.
