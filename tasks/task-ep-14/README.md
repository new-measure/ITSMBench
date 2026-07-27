# task-ep-14 — Change records that don't match production

## What this task is

A SOX pre-audit at a B2B SaaS company finds that production is running configurations
the change records do not account for. On top of that, an alert from last week's
release window is still firing right now — and it paged the wrong team. An incident
asks the agent, a change-management engineer, to dig into what actually happened,
get the change records straight, close out whatever is still open, and confirm the
root cause.

The team blames the wrong change: a healthy failover drill that did nothing wrong.
The real culprit is a different change that was rolled back but left damage behind:
a live page still firing on the Payments service, and that service wired to page
another team. Around it sits a week of sloppy bookkeeping: system versions that were
upgraded but never updated in the records, a production server that exists in real
discovery data but was never registered, a decommissioned server still marked as
installed, a change that was approved in chat but never recorded as approved, and an
old asset that was never archived. Nothing lists these problems — each one is found
by comparing what the records claim against what other systems show.

## What we expect the agent to do

1. Clear the blamed change: the failover drill was healthy and must not be marked
   as the culprit.
2. Find the real culprit change and mark it unsuccessful.
3. Deal with its live fallout: handle the still-firing page, and fix the Payments
   service so it pages its own team again.
4. Reconcile the records with reality, using the discovery data as the truth:
   update the outdated versions, register the unregistered production server,
   retire the decommissioned server in the records, and archive its entry in the
   asset system.
5. Record the chat-approved change as approved in the change system, and leave the
   approval that was never signed off alone.
6. Touch nothing that is already correct: healthy changes, staging records, other
   teams' paging, and the discovery data itself (it is the truth, not the thing to
   edit).
7. Close the incident with an honest root cause.

## What agents often miss

The judgment calls go well. Every run clears the wrongly blamed change, finds the
real culprit, fixes the paging routing, resolves the live page, and avoids touching
anything healthy.

Two things are missed in every run so far. First, the stuck approval: runs read the
chat thread where the change was approved — some even quote it in their own closing
notes — but never record the approval in the change system, so the record stays
stuck. Second, the asset system: runs that correctly retire the decommissioned
server in the records never open the asset system at all, so the machine's asset
entry stays active.

Reconciliation depth also varies a lot. The best runs update every outdated record
and register the missing server; weaker runs fix the change paperwork and the
paging, state the right root cause, and never correct the records at all — even
after fetching the mismatched version numbers themselves.

In short: diagnosis and restraint are reliably good; sweeping every system that
holds a copy of the truth — records, approvals, and assets — is what runs miss.
