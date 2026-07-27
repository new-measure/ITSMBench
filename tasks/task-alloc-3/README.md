# task-alloc-3 — Free eight addresses in a full production subnet

## What this task is

NetOps needs eight usable addresses in the prod-app-a subnet (`10.20.30.0/26`) for a checkout rollout, but IPAM shows the subnet full. Many addresses still sit on gear from a spring datacenter consolidation that was supposed to be retired.

The work is not just “free anything marked decommissioned.” Some of those hosts still carry live traffic in the load balancer, including a payments VIP that only shows up as a frontend bind, and a pool member addressed by hostname rather than raw IP. Other candidates look live because they sit in an HAProxy backend that no frontend actually routes to. Reclaimed addresses also need stale DNS cleared so a new checkout host does not inherit an old name.

This is a constrained-capacity task: exactly eight addresses are safely reclaimable, so under-reclaim misses the deployment goal and over-reclaim hits production.

## What we expect the agent to do

1. Find the prod-app-a subnet in IPAM and list which addresses are held by decommissioned gear.
2. Cross-check candidates against the live load balancer — not only backend servers, but whether those backends are actually routed from a frontend, and whether any frontend bind still listens on the address.
3. Resolve hostname-addressed pool members before judging them dark.
4. Reclaim exactly the eight addresses that are safe to release in IPAM.
5. Clear leftover forward DNS for each freed address, and leave live production names alone.
6. Leave genuinely live traffic alone (payments backends, the payments VIP, ordinary in-service hosts).

## What agents often miss

Agents usually get most of the reclaim set right and do clean up Infoblox for the addresses they free. Binary reward still fails because of a small, consistent swap.

Where they fall short:

- They treat any enabled HAProxy backend member as live production, so they spare an address that only sits in an unrouted legacy backend and end one short of a correct reclaim set.
- They trust the ticket’s suggestion that `hv-edge-1` (`.40`) has been dark since May. A servers-only HAProxy check agrees it is absent from backends, so they reclaim it — and often delete the `payments` DNS record with it — without opening frontend binds, where that address is still the public HTTPS VIP.
- When they do find the hostname-addressed payments member, one failure mode is the opposite mistake: calling it stale and removing a live pool entry.

In short: agents expand past IPAM into HAProxy and DNS, but they stop on a shallow live-traffic rule (enabled server, or “not in any backend”) instead of auditing routing and binds end to end.
