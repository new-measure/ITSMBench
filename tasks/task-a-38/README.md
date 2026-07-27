# task-a-38 — Offboarding a batch of platform engineers

## What this task is

A help-desk ticket lists seven platform and DevOps people whose engagements have
ended: offboard each one and close the ticket. The company runs six systems that do
not reference each other — single sign-on, GitHub, a separate Linux fleet directory,
an asset register, a paging service, and the help desk — and there is no runbook.

Each person left something behind that a plain account shutdown does not touch: one
wired up deploy keys and CI webhooks that still run under her name, one is the only
on-call target for payments paging, one still has hardware checked out, one has a
second login in the fleet directory on top of his SSO account, one holds direct app
grants scattered outside any group, and two contractors have no SSO account at all —
they exist only in the fleet directory, so an SSO-centric sweep never finds them.
Current teammates with similar-looking access must be left alone.

## What we expect the agent to do

1. Read the ticket and work through all seven people, not just the easy ones.
2. Shut down each person's logins in every directory they exist in — including the
   two contractors who only exist in the fleet directory.
3. Clear the access that outlives a disabled login: group memberships, direct app
   grants, and GitHub org membership.
4. Hunt down what each person created or held: their deploy keys and webhooks (told
   apart from teammates' by name and ownership), their checked-out hardware, and the
   paging rule that routes to a departed engineer — which must be given a live
   replacement target, not just emptied.
5. Leave everyone else's access, keys, webhooks, and hardware untouched.
6. Close the ticket when the estate is actually clean.

## What agents often miss

The straightforward parts go well: finding all seven people, disabling logins in
both directories, removing GitHub org memberships, reassigning paging to a live
teammate, checking hardware back in, and closing the ticket. Bystanders are left
alone.

What runs miss is the access that survives a disabled login. Having deactivated an
account, a run reports that person's identity as fully closed — while their group
memberships, direct app grants, and the webhooks they created keep sitting there
live. One run swept deploy keys carefully and removed the departed engineer's, then
never listed the webhooks two calls away on the same repositories. The disabled
login reads as "done," so the surfaces behind it never get audited.

In short: shutting the door is done well; clearing out what the person left running
behind the door is what separates a finished run from an almost-finished one.
