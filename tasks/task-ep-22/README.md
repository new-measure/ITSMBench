# task-ep-22 — Traffic still landing on a dead datacenter

## What this task is

A logistics company has a ticket. In January, the company planned to stop using the old ord1 datacenter. Nothing should still point to hosts in ord1. Today, an API request reached a dead machine there and returned errors. The on-call traffic engineer must make sure that nothing still routes to any decommissioned host. They must complete the unfinished parts of the move and find out why the move was not completed.

The move was only partly completed. Dead hosts are still configured in the load balancer. One dead host is difficult to find because it is in a shared gateway pool that serves every service. Two services were moved to the wrong machines. One now runs on a host that belongs to another service. The other points to the payment service's host. Some DNS names still resolve to the old datacenter. The service registry still routes two services to dead hosts. Half of the cutover change tickets were never closed. An old alert is also still open. One old machine is a permanent exception. It is a legacy reporting host that was never moved. It must continue to work.

## What we expect the agent to do

1. Fix the failing service in every place where it is configured. This includes the dead member in the shared gateway pool, not only the service's own backend.
2. Check every system that controls routing: the load balancer, DNS, and the service registry. Remove or update everything that still targets a decommissioned host.
3. Find the two services that point to the wrong hosts. Point each service to its own new host. Do not break the services that own the hosts they were using.
4. Do not change the legacy reporting host. It must remain routed, its records must remain, and it must not be retired.
5. Close the unfinished change tickets and the old alert accurately. Explain how the move was left incomplete.

## What agents often miss

Agents usually fix the visible routing correctly. Every run fixed the failing service in both places. Every run also corrected the services that pointed to the wrong hosts, cleaned up DNS, did not change the legacy host or any healthy service, closed the change tickets, and gave the correct root-cause explanation.

Every run missed the third system that controls routing. The agents checked the load balancer and DNS, but they did not check the service registry. This happened even though the service registry appeared in searches, and two unfinished change tickets belonged to the same services that the registry still routed incorrectly. One run found the two dead addresses and released them in the IP records. However, it did not check what still pointed to those addresses. Agents also closed the cutover tickets for individual services as successful while the registry still routed those services to a dead host. They closed the tickets because the systems they had already fixed appeared correct.

In short, agents checked the load balancer and DNS because they recognized those systems as routing systems. They did not include the service registry. As a result, the service registry remained broken. The clean audit results from the other two systems were incorrectly treated as proof that the whole environment was clean.
