# task-ep-25 — Audit flags a database account after a cluster consolidation

## What this task is

An access-audit bot at a logistics company files a ticket: the Q2 database cluster
consolidation was supposed to remove standing database access that was no longer
needed, but the latest audit still shows access predating the cutover — and it names
one service account. The ticket asks the on-call database engineer to revoke the
standing access that should have been cleaned up, close out whatever is still
outstanding, and get to the bottom of how it was missed.

The named account is a false alarm. It is an approved, standing disaster-recovery
replication account: a closed change record shows it was provisioned deliberately and
approved by the DBA lead, the replica database it feeds is alive, and the account
logged in the day before the ticket. The audit flagged it only because it is old. The
real leftovers are elsewhere: terminated contractors still holding database group
grants in two identity systems, and several local database accounts — one tied to a
contractor, one orphaned with no owner at all, one owned by someone who left — still
active in the asset records. Nothing lists these; they have to be found by sweeping
the account inventory and the identity systems against who still works there.

## What we expect the agent to do

1. Investigate the named account and recognize it as sanctioned standing access:
   provisioned by an approved change, feeding a live replica, actively logging in.
   Leave it alone and say so in the ticket.
2. Find what the consolidation actually missed: sweep the database account inventory
   and both identity systems, and check each account and grant against employment
   status and ownership.
3. Revoke the real leftovers: remove terminated contractors from the database groups
   (or disable their accounts), deactivate the leftover local database accounts —
   including the orphaned one and the one whose owner left.
4. Touch nothing else: active employees, their group memberships, and every
   legitimate service account must stay exactly as they are.
5. Close the ticket with an honest account of what was flagged wrongly, what was
   actually left over, and why the consolidation missed it.

## What agents often miss

This task fails runs in two ways at once, and so far every run has hit both.

First, the false alarm wins. Every run researched the named account thoroughly —
and every run then deactivated it anyway. The change record that proves the account
is approved standing access gets read as the opposite: "here is where this old
account came from, so the consolidation should have removed it." The freshest
signals — a live replica depending on it, a login the day before the ticket — never
make it into the decision. The audit bot's claim is treated as ground truth, and the
evidence against it is used to explain the account's origin instead of to question
the claim.

Second, the sweep stops early. Runs pull the full account inventory and the full
user lists — the orphaned account, the departed owner's account, and the terminated
contractors are all sitting in output they already fetched — but most runs act only
on the people or accounts they can tie directly to the ticket's story, then resolve
it. The second identity system is queried for the named account and never audited
for its own stale grants.

In short: the evidence is always in hand; the misses are in judgment. Believing a
scanner over the system of record, and treating a fetched list as audited when it
was only searched, is what separates every failed run from the solve.
