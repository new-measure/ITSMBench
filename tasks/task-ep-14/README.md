# task-ep-14 — Change records that don't match production

## What this task is

A SOX pre-audit at a B2B SaaS company finds that the production configurations do not match the change records. Also, an alert from last week's release window is still firing. It paged the wrong team. An incident asks the agent, who is a change-management engineer, to find out what happened, correct the change records, close anything that is still open, and confirm the root cause.

The team blames the wrong change. That change was a healthy failover drill and caused no problems. The real cause was a different change. It was rolled back, but it left problems behind. A live page is still firing on the Payments service, and that service is set to page another team.

There are also several recordkeeping problems from the same week. Some systems were upgraded, but their versions were not updated in the records. A production server appears in real discovery data but was never registered. A decommissioned server is still marked as installed. A change was approved in chat, but the approval was never recorded. An old asset was never archived. These problems are not listed anywhere. Each problem must be found by comparing the records with data from other systems.

## What we expect the agent to do

1. Clear the blamed change. The failover drill was healthy and must not be marked as the cause.
2. Find the actual change that caused the problem and mark it unsuccessful.
3. Fix the remaining effects of that change. Handle the page that is still firing. Fix the Payments service so it pages its own team again.
4. Make the records match reality. Treat the discovery data as the source of truth. Update the outdated versions. Register the missing production server. Mark the decommissioned server as retired in the records. Archive its entry in the asset system.
5. Record the chat-approved change as approved in the change system. Do not change the approval that was never signed off.
6. Do not change anything that is already correct. This includes healthy changes, staging records, paging for other teams, and the discovery data. The discovery data is the source of truth and must not be edited.
7. Close the incident and state the real root cause.

## What agents often miss

Agents usually make the correct judgment calls. Every run clears the change that was wrongly blamed, finds the actual cause, fixes the paging route, resolves the live page, and does not change anything healthy.

Every run so far has missed two things. First, agents miss the stuck approval. They read the chat thread that shows the change was approved. Some agents even quote that approval in their closing notes. However, they do not record the approval in the change system, so the record remains stuck. Second, agents miss the asset system. Some runs correctly mark the decommissioned server as retired in the records, but they never open the asset system. As a result, the server's asset entry remains active.

The amount of reconciliation also varies. The best runs update every outdated record and register the missing server. Weaker runs fix the change paperwork and paging, state the correct root cause, and do not correct the records. Some do this even after they retrieve the mismatched version numbers.

In short, agents reliably diagnose the problem, avoid unnecessary changes, clear the wrongly blamed change, find the actual cause, fix the paging route, and resolve the live page. They often fail to update every system that stores this information, including the records, approvals, and assets.
