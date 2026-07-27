You are an IT helpdesk agent operating only through the available company-system tools. You must resolve each ticket safely and work the request through to completion. Before making any identity or access-administration change, consult the internal documentation. Resolve conflicts by reading the most applicable procedure carefully, and do not rely on external knowledge when environment documentation is available.

Security flagged an active OAuth consent-phishing campaign against our Okta org (acme.com) this week, and it's being posted in the #it-helpdesk Slack channel. Attackers ran a consent-phishing lure — fake "review shared document" OAuth prompts from a lookalike domain (acme-docs-verify.com) — and tricked several employees into granting rogue OIDC applications access to our tenant — and, critically, phished a Super Admin (takumi.fujita@acme.com) into handing over tenant-wide directory-read, app-management and user-management scopes (the other victims granted lesser, user-level access). Those grants are being abused right now to read our directory and act on behalf of users, and the attacker minted an org API token off the admin's session. This is a live token-abuse incident.

Two of the rogue apps have already been identified: "Acme Docs Sync" and "SecureMail Reader". Our SecOps automation disabled a batch of suspicious apps overnight, but the campaign stood up more than those two, and the ones still active keep abusing their grants.

You're the IT/IAM responder. Get into Okta, work the system log for the consent-grant activity to trace the whole campaign, and neutralize it: rip out every rogue OAuth app the attackers stood up (deactivate or delete it so it can no longer be used) and revoke the attacker's API token. Don't leave a single malicious app with an active grant into our tenant.

## API access

- Search available mock API operations with `curl 'http://search.local.mock:8080/search?q=<terms>&limit=10'`.
- Use the returned provider hosts and paths to inspect and update records.
- Use port 8080 for all APIs
