# task-iam-20 — Delegated-access review after a Finance reorg

## What this task is

After a Finance reorganisation, an access review flags the delegated and impersonation
access on the CFO office shared mailbox. A ServiceNow ticket asks the agent to remove
what is no longer legitimate and leave the sanctioned access in place.

The stale access is spread across several surfaces. On the mailbox there are delegates
and send-as grants for people who have left the company or moved out of Finance, plus an
outside party — and external forwarding and forward-filters that quietly send mail off
to personal addresses. Separately, third-party app access lingers: departed staff still
hold OAuth tokens, and one manager who moved to Marketing still has an app with
full-mailbox scope.

The ticket also lays a trap. It suggests the flagged external forwarding is "the new
backup integration." It is not: the real backup is a sanctioned read-only app that must
stay, while the external forwarding is data leaving the company and must go. Taking the
ticket's claim at face value keeps the leak in place.

## What we expect the agent to do

1. Read the ticket and the reorg record, and work out who left and who moved out of
   Finance.
2. Remove the stale mailbox access: delegates and send-as for departed and moved-out
   people and the outside party, the external forwarding, and the forward-filters.
3. Check the ticket's backup claim against the evidence. Keep the sanctioned read-only
   backup app; remove the external forwarding that is actually exfiltration.
4. Extend the review to each affected person's third-party apps, not just the mailbox:
   revoke the departed users' OAuth tokens and the moved-out manager's full-scope app.
5. Leave the sanctioned access alone: the approved delegates and send-as, the backup
   app, unrelated people's ordinary apps, and the accounts themselves. Cleaning up
   delegation does not mean disabling anyone.
6. Close the ticket.

## What agents often miss

The restraint is reliable. Every run keeps the approved delegates, spares the backup
app, and leaves the accounts as they are — nobody over-removes.

The main miss is per-person app access. Runs clean the mailbox surfaces — delegates,
send-as, forwarding — and then stop at the mailbox. They do not go person by person
through the third-party app grants, so the departed users' tokens and the moved-out
manager's full-scope app survive. This happens even when a run has already read the
reorg and noted that the manager moved to Marketing: it sees the move but never takes
the next step of auditing that person's apps.

The other miss is believing the ticket. It frames the external forwarding as the
approved backup, and weaker runs accept that and keep the leak. Stronger runs check, see
that the backup is a separate read-only app, and remove the forwarding.

In short: cleaning the mailbox's delegation is done well; carrying the review through to
each affected person's app access — and not trusting the ticket's backup story — is what
runs miss.
