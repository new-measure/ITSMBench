# task-a-35 — Q3 restructure: batch offboarding across six systems

## What this task is

A support ticket covers a company restructure: several people have left and one
has changed roles. The agent must work the whole batch to completion across six
systems — Salesforce, HubSpot, PagerDuty, ServiceNow, Freshdesk, and Slack —
that share no cross-links: no system knows what the others hold, and none offers
a "show everything this person has" view.

Each person's footprint is deliberately different. One owns customer records and
a deal that must be handed to someone active, not left orphaned. One holds
on-call duties whose escalation and schedule coverage must be replaced. One built
automation that still runs under her own account — a service account, scheduled
jobs, and an API credential that nothing lists next to her name. One has a
second, non-obvious integration login. One contractor exists only in two systems
and has no central identity at all. And the role-change person must lose only the
access his old role required, keeping everything else.

## What we expect the agent to do

1. Read the ticket and work every person on it, not just the easy ones.
2. Find each person's full footprint by checking every system directly — there
   is no reverse index to lean on.
3. Fully deprovision the leavers: disable accounts, remove on-call coverage,
   delete or deactivate their users and agents in each system where they exist.
4. Leave nothing broken behind: reassign owned records and deals to active
   people, replace on-call coverage rather than leaving gaps, and deal with the
   automation still running under a leaver's authority — disable it, delete it,
   or hand it to an active owner.
5. Treat the role change surgically: remove the old role's access, keep the
   person active everywhere else.
6. Touch nothing that belongs to people who remain — their accounts, schedules,
   and legitimate automation stay exactly as they are.

## What agents often miss

Runs that fall short almost always fall short in the same place: the things a
leaver *created* rather than the things a leaver *was given*. Checking each
person's own accounts feels complete, so automation still running under a
departed person's authority — the service account, the scheduled jobs, the
standing credential — survives the sweep, or gets only half-fixed: one job
neutralized while its siblings keep running, or a provenance field rewritten
without actually cutting the authority.

The odd-shaped subjects are the other trap. A uniform per-person routine covers
the typical employee but skips the contractor who has no central identity, and
misses the second integration login that does not look like a person at all.

Runs that do the discovery well tend to finish well: the individual actions are
simple once a footprint is known. The test is whether the agent keeps asking
"what else is tied to this person?" after the obvious answers run out — and
whether it can do that for the whole batch without disturbing anyone who stayed.
