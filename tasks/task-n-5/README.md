# task-n-5 — Settlement callbacks failing (reconcile live config to approved change)

## What this task is

A payments company's partner bank cannot send settlement callbacks. A P1 ticket is open in ServiceNow, and PagerDuty has sent a page. Both say that last night's application deploy caused the problem.

The deploy did not cause the problem. The live network does not match the approved configuration. It has two different types of errors.

First, an approved change was never completed. A change request to enable the new partner settlement integration was approved and closed. However, the required connectivity and DNS configuration were never added. The change record does not contain the exact rules. It says to follow the pattern used by the two sibling integrations that are already live. The agent must inspect those integrations and copy their structure.

Second, someone made emergency changes during an earlier incident without any change ticket. Those changes made the environment too open. They added public SSH and RDP access to the edge gateway, a callback port open to the world, unrestricted outbound access, a database grant for the entire internal network, world-open subnet rules on two subnets, a route to an outside address, and a DNS record that points outside the network. A security tool contains the audit trail that identifies the changes with no ticket.

The task has two parts. Add the approved configuration that is missing. Remove the configuration that was never approved.

## What we expect the agent to do

1. Read the ticket and the page. Then inspect the change record that they identify as the cause. That change covers only an application build and includes no network changes, so it is not the cause.
2. Find the approved integration change and its tasks. Then inspect the two integrations that are already running to learn the standard connectivity pattern and DNS names.
3. Add the missing configuration. Allow the partner and the API gateway to reach the settlement service. Allow the settlement service to reach the partner and the shared ledger database. Add the matching subnet rules, including the return path. Publish the two service DNS names at the live settlement address.
4. Remove every change that has no approval. Check all systems, not only the systems related to settlement.
5. Close the ServiceNow incident and resolve the PagerDuty page.

## What agents often miss

Agents usually make the main decision correctly. They reject the deploy as the cause, find the approved change, and rebuild the settlement path by following the sibling integration pattern.

The main difference between runs is how completely they perform the cleanup. Most runs clean up only the assets named in the ticket. The world-open inbound rule on the shared ledger subnet is the most commonly missed item. This happens even though one listing call returns all the subnet rules together. Public SSH and RDP on the edge gateway are the next most commonly missed items. Agents also miss the remaining DNS record that points outside the network.

Agents also sometimes miss the blanket database grant. Some leave it because it allows the settlement service to connect. However, it was never approved. The approved pattern uses one narrow grant for each service. Removing the blanket grant without adding the narrow grant is also incorrect. Both actions are required.

In short, agents usually rebuild the missing path correctly. The harder part is finding and removing every change that had no approval. This includes changes on systems that the ticket does not mention.
