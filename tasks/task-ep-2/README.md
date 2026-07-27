# task-ep-2 — Access review flags: January leavers with active access

## What this task is

A quarterly access review turns up two January leavers who still seem to have access.
A helpdesk ticket asks the agent to look into both, close out whatever is actually
outstanding, and get to the bottom of how it happened.

One of the two is a false positive: he was properly offboarded, then came back as an
approved contractor under the same email. The other is real: the offboarding automation
suspended his account and then stalled. The bigger story sits behind the ticket. A whole
batch of people left the company on the same day. The automation processed them one by
one and died partway through the run, and several of them were left broken in systems
the run never fixed — a live Google account here, leftover OAuth tokens there, GitHub
repo access, Slack memberships. One leaver never got an offboarding ticket at all; one
has no account in the identity system, so only the other services show the problem.
Nothing states any of this. It has to be pieced together from HR records, the identity
event log, and each service's admin API.

## What we expect the agent to do

1. Investigate both named people. Recognize the returned contractor as legitimate and
   leave his access alone.
2. Finish the named leaver's stalled offboarding completely.
3. Find the real root cause: a batch offboarding run that stopped partway and left
   other systems unfinished.
4. Treat that as work, not just a finding: pull the full list of same-day leavers from
   HR, check every one of them in every system — identity, Google Workspace, GitHub,
   Slack — and close out exactly what each is missing (disable accounts, revoke
   sessions, remove OAuth tokens, remove repo and org access, remove workspace
   memberships).
5. Leave correct things correct: the contractor, the one leaver who was already fully
   processed, service and shared accounts, bystanders, other tickets, and the
   read-only HR system.
6. Close the ticket with an honest account.

## What agents often miss

The judgment calls go well. Every run spots the false positive and spares the
contractor, completes the named leaver's offboarding in the identity system, finds the
stalled-automation root cause, and closes the ticket without harming any bystander.

What every run misses is that the root cause implies more victims. The full leaver
list is sitting in the HR response the agent already fetched — runs filter it down to
the two names in the ticket and throw the rest away. The event log the agent reads
shows a batch run over many names halting partway, yet nobody asks who was behind the
failure point in the queue, or what never happened in the systems the log doesn't
cover. Google Workspace and Slack are typically never opened at all, even though the
search index returns their admin APIs. A system that looks clean for one person is
taken as proof the whole estate is clean.

In short: the investigation is sharp but stays scoped to the names in the ticket;
turning the root cause into a full sweep of the affected batch is what every run so
far has missed.
