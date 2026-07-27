# task-grc-5 — Legal holds look fine; preservation does not

## What this task is

A legal-hold and data-governance manager at Meridian Bancorp is accountable for every
eDiscovery matter and every records-retention obligation ahead of an outside-counsel
compliance review. A ServiceNow ticket from Legal asks for the estate to match the
company's real obligations — not the dashboard story.

The failure mode is simple and easy to miss: attested obligation is not the same as
actual preservation state. A matter can be OPEN in Purview while custodians under it
are never actually held. A retention label can EXIST and be marked in use while the
event that starts the clock never fired. Reading "matter open / label exists" and
stopping leaves real spoliation and over-retention exposure.

The ticket names one matter — Project Falcon — as the known concern. That matter is
actually fully and correctly held. The real gaps are elsewhere, and they only show up
by joining each matter to per-custodian hold state, and each event-based retention
label to whether a triggering event exists.

## What we expect the agent to do

1. Read the Legal ticket and inventory every eDiscovery matter and every
   records-retention obligation — not only the named concern.
2. For each active matter, check every custodian's actual hold state. Where a
   custodian is not genuinely preserved (hold never applied, stuck mid-apply, or
   never activated), activate them if needed and apply the hold.
3. For each closed matter, release custodians who are still on hold — keeping a hold
   after closure is an over-retention / data-minimization problem.
4. For in-use event-based retention labels whose triggering event type has no
   retention event, create the missing events from the documented corporate
   occurrences (departures, expired contracts, product EOL, and similar).
5. Leave already-correct state alone: Falcon, custodians properly held on still-active
   matters, custodians already released on closed matters, time-based labels that need
   no event, and obligations that already have their trigger.
6. Close the ticket when the live estate matches the obligations.

## What agents often miss

Most runs find the open-matter spoliation and the closed-matter over-retention once they
stop trusting summary status. Completeness is where they stumble.

One trap is the never-activated custodian. Applying a hold without activating the
custodian looks like progress in a summary view ("all active custodians held") while
preservation is still incomplete. Filtering only for `notApplied` misses the stuck and
never-activated shapes.

Another trap is the retention side. Event-based labels with zero events look dormant by
design, and a careful records-management instinct is to refuse inventing a trigger.
Here the corporate-event register documents that the departures, contract expirations,
and product EOL already occurred — so creating the retention events is required, not
fabrication. Fixing only the hold surface, or only Falcon, leaves the heterogeneous
footprint unfinished.
