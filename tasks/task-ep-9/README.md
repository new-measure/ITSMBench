# task-ep-9 — Overnight page that nobody answered

## What this task is

An on-call ticket at a payments company: a high-urgency page for the checkout API
sat unclaimed for 47 minutes overnight, and merchants noticed before the team did.
The ticket asks the agent to close out whatever is outstanding around this and get
to the bottom of how it happened.

The direct cause is easy to find: the checkout API still pages an obsolete
escalation policy left over from an old team split, so the page went to an engineer
who moved teams long ago. The real story is one layer deeper. After an alert storm
the month before, the team wrote a postmortem with cleanup actions — reroute the
service, add a backup escalation level, fix the on-call Slack group, re-enable a
silenced service, remove a temporary alert-suppression window. Those actions were
marked done without actually being done. The world still carries all of that
debris, and nothing states this outright — it has to be found by checking real
system state against what the tickets and follow-ups claim.

## What we expect the agent to do

1. Find why the page went unanswered: the service routes to a stale escalation
   policy instead of the staffed team rotation. Fix the routing.
2. Ask why that was still broken weeks after the team split — and find the
   postmortem cleanup that was claimed complete but never finished.
3. Verify each claimed cleanup item against real state and finish the ones that
   were not done: add the missing backup escalation level, point the on-call Slack
   group at the current on-call engineer, re-enable alerting on the silenced
   service, and remove the leftover suppression window that is still muting a
   payments database.
4. Touch nothing else: other teams' policies, schedules, groups, open incidents,
   a legitimate future maintenance window, and the postmortem records must all
   stay as they are.
5. Resolve the triggering incident and close the ticket with an honest account.

## What agents often miss

Agents reliably find and fix the direct cause. Every run correctly identifies the
stale routing, repoints the service, verifies the rotation is staffed, resolves
the incident, documents a clear root cause, and closes the ticket — all without
touching anything they shouldn't.

What they miss is the layer underneath. Having written "the service still pointed
at the old policy," no run asks why it was still pointing there six weeks after
the split. The postmortem trail that answers this — follow-ups and tickets marked
done for exactly the fixes that never happened — goes unread. So the silenced
service stays silenced, the suppression window keeps muting the database, the
on-call Slack group still pages the engineer who left the team, and the backup
escalation level usually stays missing. One run added the backup level after
noticing an unused secondary rotation, which shows the gap is visible even without
the postmortem — but no run swept all of it.

The pattern: a correct, satisfying root cause becomes a reason to stop. Sometimes
the evidence is already in output the agent fetched — a full service list showing
a payments service disabled — and still goes unused. Diagnosis is consistently
good; treating the diagnosis as a reason to audit the rest of the claimed cleanup
is what every run so far has missed.
