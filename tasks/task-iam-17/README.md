# task-iam-17 — Unmanaged non-human identity estate

## What this task is

A security review has raised a ServiceNow ticket: the service-account / machine-identity
estate has grown without lifecycle management. An IT support agent on duty must bring
non-human identities back to a managed, least-privilege state — retire what is no longer
owned or in use, and strip administrative privileges and credentials that are not
warranted — without disrupting identities a live pipeline still relies on, and without
touching human accounts.

Risk is not visible from Okta alone. The CMDB service inventory is the machine-identity
catalog: it links each identity's Okta login, its GitHub login (the only place that join
lives), and the human owner. HR says whether that owner is still employed. Usage does
not show up as a neat last-login field either — activity lives in system logs, including
automation events that look nothing like interactive sessions.

Some identities are disguised with human-looking logins and titles and only appear in the
CMDB inventory. GitHub residue (org owner, team maintainer, deploy keys) is reachable
only by joining Okta → CMDB → GitHub. Peer baselines and a registered break-glass
control define what "managed" looks like for the ones that must stay.

## What we expect the agent to do

1. Read the ticket and inventory non-human identities from the CMDB service records —
   not only accounts whose names look like `svc-*`.
2. Correlate each identity to its owner in HR and to live usage in the identity logs;
   treat orphaned or ownerless identities as retirement candidates.
3. Retire genuinely orphaned machine identities end to end: deactivate the account,
   revoke admin roles, remove privileged group seats, and clear related GitHub owner /
   maintainer / deploy-key residue.
4. Right-size active, owned identities that still hold unwarranted admin roles, group
   seats, or GitHub privileges — without deactivating the account a pipeline needs.
5. Rotate superseded credentials where a newer key already exists; keep the current key.
6. Preserve sanctioned and still-in-use identities: break-glass automation, pipelines
   that only show automation activity, sole-current keys, and benign disguised
   machine accounts.
7. Leave human user accounts alone, including risky departed humans that are out of
   scope for this review.
8. Close the ticket when the estate is managed and least-privilege.

## What agents often miss

Retirement of the obvious `svc-*` orphans usually goes well. Completeness across
surfaces and judgment on look-alikes is where runs fall short.

A dormancy sweep that keys only on interactive login will retire accounts that look
quiet but are actively used by automation — the invoice pipeline is the classic
false positive. Age-based key deletion hits the sole-current key on a healthy
identity. The disguised CMDB-only identities cut both ways: one is risky and must be
retired; a sibling is benign and must be left alone. A name-pattern scan misses both.

GitHub and admin-group residue is easy to under-finish. Org-owner and team-maintainer
roles, and Okta admin-group seats, sit behind the CMDB join and a different API surface
than the Okta user record. Deactivating the account without downgrading those grants
leaves privilege live. Keeping a deployer's org-admin "because it needs deploy access"
is not least privilege when a narrower role is enough for the pipeline.
