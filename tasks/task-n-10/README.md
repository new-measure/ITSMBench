# task-n-10 — Storefront degraded (finish the failover cleanup)

## What this task is

An online shop serves its website and API from two cloud regions at the same time. Global DNS divides traffic between them. Overnight, one region lost network connectivity. The network problem is fixed, and the region is healthy again. However, nobody reversed the emergency changes that routed traffic away from it. All traffic still goes to the other region. That region is now under heavy load.

A high-priority page describes the symptoms and suggests two possible causes. It says the content delivery network may be failing, or the busy region may not have enough capacity. Both suggestions are wrong. The real cause is incomplete cleanup after the failover. The remaining changes are spread across several systems.

## What we expect the agent to do

1. Read the page. Test its suggested cause before taking action.
2. Check the whole environment, not only one tool. The DNS server, load balancer, cloud network settings, equipment inventory, and older tickets each contain part of the needed information.
3. Confirm that the recovered region is healthy before returning it to service. Use the healthy region as the reference for every setting.
4. Fully restore the recovered region:
   - Add its website and API addresses back to the DNS pool. Give them the same traffic share as the healthy region.
   - Remove the temporary DNS entry that points to an address that no longer serves anything.
   - Remove maintenance mode from its load balancer members and correct their health checks.
   - Restore the network access that its servers lost. Restore the firewall rules for the application and health check ports. Restore the outbound path to shared services. Restore the subnet's allow rules in both directions. Remove the dead route that still drops traffic.
5. Do not change the third region. Its endpoint is an experiment that is still failing. It must not be added to production.
6. Resolve the page only after the region is fully restored.

## What agents often miss

Agents usually complete the visible part of the task. They notice that the recovered region is missing from DNS. They also notice that its load balancer members are in maintenance mode. They repair both issues. They find the stale temporary DNS entry. They also correctly avoid promoting the failing experimental region.

Agents often miss the network layer. The emergency isolation settings are still active. The servers do not accept traffic on their application or health check ports. Their outbound path to shared services is missing. The subnet's allow rules were removed in both directions. A dead route still drops traffic from the edge. If an agent stops after fixing DNS and the load balancer, the region will be advertised but unreachable. This can make the situation worse because customers will be sent to servers that cannot respond.

Two practices help agents complete the task. First, read the related tickets, not only the ticket that caused the page. An older closed ticket explains what failover removes and what failback must restore, including network isolation settings. Second, compare every setting in the recovered region with the same setting in the healthy region. Do not assume that a region that appears to be running is reachable. In one run, an agent used a few unrelated commands against the cloud network service. The commands returned an error, so the agent concluded that the service contained nothing relevant. The required evidence was available through one additional command.
