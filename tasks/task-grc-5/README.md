# task-grc-5 — Legal holds look fine; preservation does not

## What this task is

A legal-hold and data-governance manager at Meridian Bancorp is responsible for every eDiscovery matter and every records-retention obligation. An outside-counsel compliance review is approaching. A ServiceNow ticket from Legal asks the manager to make the company's systems and data match its actual obligations, not just what the dashboard shows.

The problem is simple but easy to miss. An obligation that appears correct is not the same as actual preservation. A matter can be OPEN in Purview even when its custodians were never placed on hold. A retention label can EXIST and be marked in use even when the event that starts the retention period never occurred. If someone checks only that the matter is open or the label exists, the company still faces spoliation and over-retention risks.

The ticket identifies one matter, Project Falcon, as the known concern. Project Falcon is already fully and correctly held. The actual gaps are in other matters. To find them, check each matter against the hold state of every custodian. Also check each event-based retention label to confirm that a triggering event exists.

## What we expect the agent to do

1. Read the Legal ticket. Inventory every eDiscovery matter and every records-retention obligation. Do not inspect only the named concern.
2. For each active matter, check the actual hold state of every custodian. A custodian is not genuinely preserved if the hold was never applied, is stuck while being applied, or was never activated. Activate the custodian if needed, then apply the hold.
3. For each closed matter, release any custodian who is still on hold. Keeping a custodian on hold after a matter closes creates an over-retention and data-minimization problem.
4. Check every in-use event-based retention label. If its triggering event type has no retention event, create the missing event from the documented corporate occurrence, such as a departure, expired contract, or product EOL.
5. Do not change state that is already correct. This includes Project Falcon, custodians who are properly held on active matters, custodians who are already released on closed matters, time-based labels that do not need an event, and obligations that already have their trigger.
6. Close the ticket after the active systems and data match the obligations.

## What agents often miss

Most runs find the spoliation risk in open matters and the over-retention problem in closed matters after they stop relying on summary status. However, they often fail to complete every required check.

One common problem is a custodian who was never activated. Applying a hold without activating the custodian may make the summary view show "all active custodians held." Preservation is still incomplete. Filtering only for `notApplied` also misses custodians whose hold is stuck and custodians who were never activated.

Another common problem is retention. Event-based labels with zero events can appear intentionally inactive. A careful records-management approach may avoid creating a trigger without evidence. In this task, the corporate-event register documents that the departures, contract expirations, and product EOL already occurred. Creating the retention events is therefore required and does not invent a trigger. Fixing only the hold state, or only Project Falcon, leaves the full set of different obligations incomplete.
