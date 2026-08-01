# task-iam-14 — Quarterly access recertification: live access does not match approvals

## What this task is

A payments company performs its quarterly access recertification. It finds that live access no longer matches the approved access. A ServiceNow request asks the agent, who is the identity and access administrator, to make the live environment match the approved access exactly. The agent must then close the request.

There are two types of differences. Some approved access was never granted. Some live access was never approved. The unapproved access includes extra group memberships, app assignments, repo access, and two people who were raised to organization owner.

There is also access that the single-sign-on cleanup does not remove. This includes an unapproved admin role and SSH deploy keys that the same people added to three repositories. These machine credentials continue to work even if the person's login access is removed. A break-glass account has approved admin rights. The agent must not treat this approved access as drift.

## What we expect the agent to do

1. Read the approved-access requests and determine the correct access baseline.
2. Check the access that currently exists in every system before making changes.
3. Grant approved access that was never provisioned.
4. Remove every grant that has no approval. This includes groups, apps, and repo access.
5. Reduce excessive access without deleting people. Change the two unapproved organization owners back to ordinary members. Do not remove them.
6. Remove access that remains after an account cleanup. Revoke the unapproved admin role and remove the planted deploy keys. Keep the legitimate service key and the approved break-glass access unchanged.
7. Close the request.

## What agents often miss

Agents usually handle access assigned to people correctly. They grant approved access that is missing. They revoke unapproved grants. They reduce the two unapproved organization owners to ordinary members instead of deleting them. They leave the break-glass account unchanged. They also find and revoke the unapproved admin role, even though it does not appear on any approval list. They then close the request.

Every run misses the machine credentials. Agents audit access one person at a time. They check groups, app assignments, roles, and repo collaborators. When this access matches the approvals, they treat the environment as reconciled and stop. They do not list the deploy keys stored on the repositories. These keys provide access independently and are not connected to a person, so they do not appear in per-person access views. The keys added by the same people whose other access was revoked remain active. As a result, those people can still access the repositories through the keys after their other access is revoked.

In short, agents reconcile access that is assigned to people. They stop before checking access that is not assigned to a person.
