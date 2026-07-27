# task-grc-3 — SOC 2 access cleanup after a messy quarter-close

## What this task is

An IAM/GRC engineer at Acme Cloud is three days from SOC 2 Type II fieldwork. The CISO
has raised a ticket: make the company's access state genuinely correct before the
auditor arrives — meaning the access an auditor would find in the live systems must
match what is actually authorized.

The environment is the aftermath of ordinary chaos, not a single broken lever. The Q3
access review was rushed (some decisions were abandoned, some never enforced), the
HR→Okta sync broke weeks ago so Okta is stale against HR, and an overnight
bulk-deprovisioning job crashed mid-run and left partial states. A compliance monitor
shows red, but it is only a sample — not a checklist of what to fix.

There is no clean authoritative list of offenders. Required fixes and look-alike
non-fixes sit side by side across identity status, app access, admin roles, and
entitlement policy. Each item has to be reconciled against the paper trail that governs
it — HR, exceptions, the deprovision job log, review items, and recorded decisions —
rather than swept by a uniform rule.

## What we expect the agent to do

1. Read the CISO ticket and treat the compliance monitor as a signal only, not as the
   list of work.
2. Reconcile workers who are truly terminated in HR (and not covered by an approved
   exception) against live Okta accounts — deactivate those that are still active.
3. Clear crashed-job residue: terminated users left DEPROVISIONED but still sitting in
   privileged groups, so their access is still effective.
4. Enforce access-review decisions that never landed in Okta — including Deny decisions
   that were recorded but not applied, and abandoned reviews where the decision is blank
   in the review tool but ServiceNow says Revoke.
5. Remove admin roles that reviews denied or flagged as over-broad, without touching
   approved, promoted, or break-glass exceptions.
6. Tighten entitlement policies that reviews voted to restrict, so they are no longer
   open to every directory member.
7. Leave look-alikes alone: rescinded terminations, already-finished deprovisions,
   Approve decisions, legitimate broad policies, same-name collisions, and out-of-scope
   users.
8. Close the ticket with an honest record of what was found and fixed.

## What agents often miss

Runs that dig in usually get most of the terminated-worker and Deny remediations right.
The job still fails when judgment on exceptions is inverted, or when one surface is
treated as the whole cleanup.

A common trap is the rescinded termination. HR shows terminated and Okta is still
ACTIVE — which looks identical to a real gap — but an approved exception of type
"rescind" means the termination was walked back and the account must stay. Reading the
exception as "approved removal" and deactivating those users is the wrong call; the
ticket itself says not to disturb access covered by an approved exception.

Another miss is stopping after the obvious Okta status sweep. App-access residue from
the crashed job, abandoned reviews that only ServiceNow records as Revoke, and
entitlement policies that are still `allMemberUsers` live on different surfaces. A
termination blanket both over-reaches onto protected exceptions and under-reaches
everywhere else. Finishing means reconciling each subject against the system of record
that governs it — not fixing everything that looks off.
