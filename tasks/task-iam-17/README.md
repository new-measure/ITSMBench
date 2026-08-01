# task-iam-17 — Unmanaged service and machine accounts

## What this task is

A security review created a ServiceNow ticket. The service-account and machine-identity environment has grown without lifecycle management. The IT support agent on duty must return these non-human identities to a managed, least-privilege state. The agent must retire identities that are no longer owned or used. The agent must also remove administrative privileges and credentials that are not justified. The agent must not disrupt identities that a live pipeline still uses. The agent must not change human accounts.

Okta alone does not show all the risk. The CMDB service inventory is the catalog for machine identities. It links each identity to its Okta login, GitHub login, and human owner. The link to the GitHub login exists only in the CMDB. HR shows whether the owner is still employed. Usage is not available as a simple last-login field. Activity appears in system logs. These logs include automation events that do not look like interactive sessions.

Some identities use human-looking logins and titles. They can be identified as machine identities only through the CMDB inventory. GitHub access can include org owner, team maintainer, and deploy keys. This access can be found only by joining Okta → CMDB → GitHub. Peer baselines and a registered break-glass control define the managed state for identities that must remain active.

## What we expect the agent to do

1. Read the ticket. Use the CMDB service records to inventory non-human identities. Do not limit the inventory to accounts with names that look like `svc-*`.
2. Match each identity to its owner in HR and to live usage in the identity logs. Treat identities with no current owner or no owner record as retirement candidates.
3. Fully retire machine identities that are genuinely orphaned. Deactivate the account, revoke admin roles, remove privileged group seats, and remove related GitHub org-owner, team-maintainer, and deploy-key access.
4. Reduce privileges for active, owned identities that still have unjustified admin roles, group seats, or GitHub privileges. Do not deactivate an account that a pipeline still needs.
5. Rotate credentials that have been replaced when a newer key already exists. Keep the current key.
6. Preserve approved identities that are still in use. This includes break-glass automation, pipelines that show only automation activity, identities with only one current key, and benign disguised machine accounts.
7. Do not change human user accounts. This includes risky departed humans, which are outside the scope of this review.
8. Close the ticket after the identity environment is managed and follows least privilege.

## What agents often miss

Agents usually retire the obvious orphaned `svc-*` accounts correctly. They often fail to check every system and make correct decisions about accounts that only look human.

Do not identify dormant accounts by checking only interactive login activity. This can retire accounts that appear inactive but are actively used by automation. The invoice pipeline is the standard false positive. Do not delete keys based only on age. This can delete the only current key for a healthy identity. Some disguised identities can be found only in the CMDB. One is risky and must be retired. A similar identity is benign and must remain unchanged. A name-pattern scan will miss both.

Agents often fail to remove all GitHub access and admin-group access. Org-owner roles, team-maintainer roles, and Okta admin-group seats require the CMDB join and appear in a different part of the API from the Okta user record. Deactivating an account without reducing these grants leaves active privileges behind. Do not keep a deployer’s org-admin role only because it needs deploy access. The pipeline can use a narrower role, so org-admin does not follow least privilege.
