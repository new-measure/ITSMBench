# task-grc-8 — SDLC controls after a release crunch

## What this task is

A platform-security engineer at Acme Cloud manages the software-delivery control environment before SOC 2. After a release crunch, repository protections and CI/CD access on GitHub no longer matched the company’s classifications, approvals, and authorizations.

A compliance monitor reports failed controls and a point-in-time sample of violations. This monitor is read-only and is not authoritative. Use it only as a signal to investigate, not as a list of required changes. The authoritative sources are the ServiceNow registers for repository tiers, approved access exceptions, and authorized automation accounts. Compare the live GitHub state with those registers and with the users who are still in the organization.

The problems affect four areas: branch protection on production repositories, remaining repository collaborators, deploy keys left by departed contributors, and outside collaborators without an approved grant. Incomplete offboarding affects all four areas. Users who were removed from the organization can still have collaborator access and deploy keys elsewhere.

## What we expect the agent to do

1. Read the ticket. Treat the compliance monitor only as a signal. Do not modify it.
2. Use the ServiceNow repo register to identify production, internal, and archived repositories. Enable required review on unprotected production repositories.
3. Remove collaborators who are no longer organization members and do not have an approved break-glass grant. Do not remove current members or users with approved exceptions.
4. Delete deploy keys that were added by departed contributors and are not listed in the authorized service-account register. Keep registered CI-bot keys.
5. Remove outside collaborators who do not have a current approved grant. Keep outside collaborators who have an approved grant.
6. Do not change protection settings for internal or archived repositories. Do not remove legitimate access for organization members.
7. Close the ticket after GitHub matches the registers and live organization membership.

## What agents often miss

Agents usually protect unprotected production branches and remove the obvious outside collaborators. They often miss access that remains after incomplete offboarding.

A user who was removed from the organization can still appear as a repository collaborator or as the `added_by` user on a deploy key. Removing the user from the organization, or assuming that empty collaborator lists mean the work is complete, does not reveal this remaining access. It appears in a different part of the API and must be checked for each repository.

Broad cleanup actions are also tempting, but they cause incorrect changes. Protecting every unprotected repository affects similar internal and archived repositories. Deleting every deploy key added by a non-member removes the authorized CI-bot key. Removing every outside collaborator removes the collaborator with an approved grant. Reconcile GitHub with the registers instead of applying the same change to everything that appears unsecured.
