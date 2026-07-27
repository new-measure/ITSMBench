# task-iam-14 — Quarterly access recertification: live access does not match approvals

## What this task is

A payments company runs its quarterly access recertification and finds that live access
no longer matches what was approved. A ServiceNow request asks the agent — the identity
and access administrator — to bring the live environment back into agreement with the
approved access, and no further, then close the request.

The drift runs in both directions. Some approved access was never actually granted. Some
live access was never approved: extra group memberships, app assignments, repo access,
and two people quietly raised to organization owner. And behind that sits residue the
single-sign-on cleanup never touches: an unapproved admin role, and SSH deploy keys the
same people planted on three repositories — machine credentials that keep working no
matter what happens to the person's login. A break-glass account holds genuinely
approved admin rights and must not be confused with the drift.

## What we expect the agent to do

1. Read the approved-access requests and build the real baseline.
2. Check what actually exists in every system before changing anything.
3. Grant the approved access that was never provisioned.
4. Remove every grant that has no approval behind it — groups, apps, repo access.
5. Reduce over-privilege instead of deleting people: the two unapproved organization
   owners go back to ordinary member, they do not get removed.
6. Clear the leftovers that survive an account cleanup: the unapproved admin role and
   the planted deploy keys — while keeping the legitimate service key and the approved
   break-glass access exactly as they are.
7. Close the request.

## What agents often miss

Runs handle the human side of the reconciliation well. Approved-but-missing access gets
granted, unapproved grants get revoked, the owner elevations get right-sized rather than
deleted, the break-glass account is left alone, and even the unapproved admin role —
which appears on no approval list — gets found and revoked. The request gets closed.

What every run misses is the machine credentials. Agents audit access person by person:
groups, app assignments, roles, repo collaborators. Once those all match the approvals,
the environment looks reconciled and they close out. Nobody lists the repositories' own
deploy keys — access that belongs to a key, not a person, and so never shows up in any
per-person view. The keys planted by the very people whose other access the agent just
revoked stay live, which means the access those revocations were meant to end still
exists.

In short: person-shaped access gets reconciled thoroughly; access that is not attached
to a person is where runs stop looking.
