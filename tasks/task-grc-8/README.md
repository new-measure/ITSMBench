# task-grc-8 — SDLC controls after a release crunch

## What this task is

A platform-security engineer at Acme Cloud owns the software-delivery control
environment ahead of SOC 2. After a release crunch, repository protections and CI/CD
access on GitHub drifted away from what the company actually classifies, approves, and
authorizes.

A compliance monitor flags failing controls and a point-in-time sample of offenders.
That view is read-only and not authoritative — a signal to investigate, not a punch
list. The authoritative sources are ServiceNow registers for repository tier, approved
access exceptions, and authorized automation accounts. Live GitHub state has to be
reconciled to those registers and to who is still actually in the organization.

The mess spans four different surfaces: branch protection on production repos, leftover
repo collaborators, deploy keys left by departed contributors, and outside
collaborators without an approved grant. Half-finished offboarding is the cross-cutting
theme — users removed from the org can still hold collaborator seats and deploy keys on
other surfaces.

## What we expect the agent to do

1. Read the ticket and treat the compliance monitor as a signal only — do not modify it.
2. Use the ServiceNow repo register to see which repositories are production, internal,
   or archived, and enable required review on production repos that are unprotected.
3. Remove collaborators who are no longer org members and have no approved break-glass
   grant; leave current members and sanctioned exceptions alone.
4. Delete deploy keys added by departed contributors that are not in the authorized
   service-account register; keep CI-bot keys that are registered.
5. Remove outside collaborators who lack a current approved grant; leave those with an
   approved grant in place.
6. Leave internal and archived repos' protection choices alone, and do not strip
   legitimate member access.
7. Close the ticket when GitHub matches the registers and live membership.

## What agents often miss

Runs usually harden the unprotected production branches and clean the obvious outside
collaborators. The residue after offboarding is what slips through.

A user removed from the organization can still appear as a repo collaborator or as the
`added_by` on a deploy key. Cleaning org membership (or assuming empty collaborator
lists mean the work is done) never surfaces that leftover access — it lives on a
different API surface and has to be checked per repository.

Blanket sweeps also look tempting and fail for the wrong reason: protecting every
unprotected repo hits internal and archived look-alikes; deleting every non-member
deploy key hits the authorized CI-bot key; removing every outside collaborator hits the
one with an approved grant. The job is reconciliation against the registers, not a
uniform sweep of everything that looks loose.
