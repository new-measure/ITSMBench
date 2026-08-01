# task-n-2 — Payments API outage (the blamed deploy is not the cause)

## What this task is

A P1 incident in ServiceNow says that customers cannot reach the Payments API. The ticket blames a payments-app release from the previous evening. It asks whether that deploy caused the outage.

The deploy did not cause the outage. Later that night, a maintenance window included two changes. A security-hardening sweep made the payments network rules stricter. A migration moved the shared dependency services into a new subnet with new addresses. These services are the auth API, database, and cache. Together, these changes broke payments traffic in both directions. Customers cannot reach the service. The service also cannot reach its dependencies. A connection works only when every hop allows it. The problems affect firewall rules, subnet rules, routing, DNS, and the load balancer pool.

The agent is the network engineer on duty. The agent has read and write access to a cloud network API, a load balancer, a DNS system, a CMDB, security monitoring, and ServiceNow.

## What we expect the agent to do

1. Read the incident. Check the named change. Use evidence to rule it out instead of making an assumption.
2. Trace the complete path. Start with the name, then check the load balancer and backend nodes. Next, trace the path from the backends to the services they depend on.
3. Compare the payments tier with the two similar tiers that the maintenance window did not change. Use those tiers as examples of a healthy configuration.
4. Restore every broken hop with least privilege. Add inbound rules from the load balancer subnet for the traffic, health-check, and agent ports. Add outbound rules to the dependency subnet. Add subnet rules that allow replies in both directions. Fix the dead route to the dependency subnet. Add inbound rules on the dependency services.
5. Complete the migration work that the change record left unfinished. Update the dependency DNS names to use the addresses that are currently live. Return the nodes that were removed from rotation during the maintenance window.
6. Remove the items left behind by the migration. Remove the old alias record that points to a retired address. Remove the pool member that has no machine behind it.
7. Close the incident with the correct state.

## What agents often miss

Agents almost always identify that the deploy did not cause the outage. They also fix the edge by restoring the inbound rules that allow the load balancer to reach the backends. Then they stop. They do this because the reported symptom is “customers cannot reach the Payments API,” and the edge problem seems to explain it.

The dependency path is the main test. The migration change record, CMDB dependency list, security monitoring alert, and DNS records all show that payments still points to a decommissioned address range. Less effective agents read this evidence and describe it correctly in their summary. However, they leave the work for someone else instead of completing it.

Agents also often miss two smaller issues. Subnet rules apply in only one direction. Agents often add the return path for one direction but forget the other direction. Agents also ignore leftover items. The stale alias record and the pool member with no server behind it are visible in the listings. Agents treat these items as optional cleanup instead of required work to keep the environment consistent. The service is not fixed if the incident is closed while the dependency path is still broken.
