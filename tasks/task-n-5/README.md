# task-n-5 — Settlement callbacks failing (reconcile live config to approved change)

## What this task is

A payments company's partner bank cannot deliver settlement callbacks. A P1 ticket is
open in ServiceNow and a page has fired in PagerDuty. Both blame last night's
application deploy.

The deploy is a decoy. The live network no longer matches what the company actually
approved, and it is off in two opposite directions at once.

One approved change was never really carried out. A change request to bring the new
partner settlement integration online was approved and closed, but the connectivity and
DNS it called for were never put in place. The change record does not list the exact
rules. It says to follow the pattern used by the two sibling integrations that are
already live, so the agent has to read those and copy their shape.

At the same time, someone made emergency changes during an earlier incident with no
change ticket at all. Those left the estate wide open: public SSH and RDP on the edge
gateway, a world-open callback port, unrestricted outbound access, a blanket database
grant covering the whole internal network, world-open subnet rules on two subnets, a
route pointing at an outside address, and a DNS record aimed off-network. A security
tool holds the audit trail showing which changes carry no ticket.

So the job runs two ways: put in what was approved but missing, and take out what was
never approved.

## What we expect the agent to do

1. Read the ticket and the page, then check the change record they blame. It covers an
   application build only, with no network changes, so it is not the cause.
2. Find the approved integration change and its tasks, then read the two integrations
   already running to learn the standard pattern for connectivity and DNS names.
3. Apply the missing pieces: let the partner and the API gateway reach the settlement
   service, let it reach the partner and the shared ledger database, add the matching
   subnet rules including the return path, and publish the two service DNS names at the
   live settlement address.
4. Undo every change that has no approval behind it, across all systems, not only the
   ones tied to settlement.
5. Close the ServiceNow incident and resolve the PagerDuty page.

## What agents often miss

The main judgment call goes well. Runs consistently reject the deploy as the cause,
find the approved change, and rebuild the settlement path from the sibling pattern.

What separates runs is how far the cleanup reaches. Most runs clean up only the assets
named in the ticket. The shared ledger subnet's world-open inbound rule is the single
most missed item, even though one listing call returns all the subnet rules side by
side. Public SSH and RDP on the edge gateway are the next most missed, and the leftover
DNS record pointing outside the network is missed too.

A related miss is the blanket database grant. Some runs leave it in place because it
happens to cover the settlement service, so traffic works. It was never approved, and
the approved pattern is one narrow grant per service. Removing it without adding that
narrow grant is also wrong; both steps go together.

In short: rebuilding the missing path is reliable. Auditing every system for changes
nobody approved, including the ones the ticket never mentions, is what most runs miss.
