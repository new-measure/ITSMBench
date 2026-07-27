# task-n-6 — Payment outage after a network migration

## What this task is

A P1 incident says payment processing is failing across the platform. The
incident blames the previous evening's app deploy. The deploy is a decoy — the app
is fine. Overnight, a maintenance window rebuilt the peering between the
production network and the shared-services network and re-applied segmentation.
Two app tiers were reconciled correctly as the reference; the payments tier was
left half-connected.

The break is symmetric. A connection across the peering only works if every hop
allows it — the near side's outbound rules and route, and the far side's inbound
rules, return route, and both directions of the stateless network ACLs on both
subnets. The incident names only payments, which tempts a run to fix the near side
and stop, leaving the far side — the shared endpoints' inbound rules and the
return path — still closed, so payments stays down. There are also a few DNS
records left pointing at hosts the migration retired, which should be cleaned up.

## What we expect the agent to do

1. Confirm the app deploy is not the cause and move on.
2. Restore the full payments path in both directions: the outbound rules to each
   dependency, the route off the dead peering, and both directions of the network
   ACLs on the payments subnet.
3. Fix the far side too: the return route to payments, the shared subnet's ACLs,
   and each shared endpoint's inbound rule for the payments subnet.
4. Model the fix on the reference tiers that already work, and grant payments only
   what those tiers get — no wider.
5. Clean up the DNS records left pointing at retired hosts.
6. Leave the reference tiers, the decoy, and everything already correct untouched,
   and resolve the incident.

## What agents often miss

Current runs handle this well: they reject the blamed deploy, work out that the
peering path is broken, and restore both sides of it.

What makes it hard is that the fix is symmetric while the incident is one-sided.
The ticket is about payments, so the obvious work is the payments side — its
outbound rules and its route. But a connection only completes if the destination
allows it back: the shared endpoints have to admit the payments subnet, the
shared network needs a return route, and because the network ACLs are stateless,
both directions have to be opened on both subnets. Stop at the near side and
payments still cannot complete a round trip, even though everything on the side
the incident names now looks correct.

The correct shape is not guesswork — the two reference tiers were reconciled
properly during the same maintenance window, so they show exactly what payments
should look like. The task is mirroring that onto payments in full, granting no
more than the reference tiers get, and then clearing the DNS records the
migration left pointing at retired hosts.

In short: the side the incident names is the visible half. Completing the
symmetric path — the far side and the return direction — is what the task tests.
