# task-n-2 — Payments API outage (the blamed deploy is not the cause)

## What this task is

A P1 incident in ServiceNow says customers cannot reach the Payments API. The
ticket blames a payments-app release that shipped the evening before and asks
whether the deploy broke it.

The deploy is a decoy. Later that night a maintenance window ran two changes: a
security-hardening sweep that tightened the payments network rules, and a
migration that moved the shared dependency services (auth API, database, cache)
into a new subnet with new addresses. Together they broke payments in both
directions. Customers cannot reach the service, and the service cannot reach the
things it depends on. A connection only works if every hop allows it, so the
damage is spread across firewall rules, subnet rules, routing, DNS, and the load
balancer pool.

The agent works as the network engineer on duty, with read and write access to a
cloud network API, a load balancer, a DNS system, a CMDB, security monitoring,
and ServiceNow.

## What we expect the agent to do

1. Read the incident, check the named change, and rule it out with evidence
   rather than assumption.
2. Trace the whole path: name to load balancer to backend nodes, then from the
   backends out to the services they depend on.
3. Compare the payments tier against the two similar tiers that the maintenance
   window left alone. Those tiers are the reference for what a healthy
   configuration looks like.
4. Restore every broken hop with least privilege: inbound rules from the load
   balancer subnet on the traffic, health-check and agent ports; outbound rules
   to the dependency subnet; the subnet rules that let replies come back, in
   both directions; the dead route to the dependency subnet; and the inbound
   rules on the dependency services themselves.
5. Finish the migration work the change record left open: point the dependency
   DNS names at the addresses that are actually live now, and return the nodes
   that were taken out of rotation for the window.
6. Remove what the migration left behind: an old alias record pointing at a
   retired address, and a pool member with no machine behind it.
7. Close the incident with the correct state.

## What agents often miss

Runs almost always spot the decoy and fix the edge — the inbound rules that let
the load balancer reach the backends. Then they stop, because the reported
symptom is "customers cannot reach the Payments API" and the edge appears to
explain it.

The dependency half is the real test. The change record for the migration, the
CMDB dependency list, the security monitoring alert, and the DNS records all
show that payments still points at a decommissioned address range. Weaker runs
read that evidence, describe it accurately in their summary, and then hand it
off as someone else's follow-up work instead of finishing it.

Two smaller misses repeat. Subnet rules apply in one direction only, so runs
often add the return path for one direction and forget the other. And leftovers
get ignored: the stale alias record and the pool member with no server behind it
are visible in plain listings, but runs treat them as tidy-up rather than part
of leaving the estate consistent. A closed incident with a broken dependency
path is not a fixed service.
