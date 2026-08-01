# task-alloc-3 — Free eight addresses in a full production subnet

## What this task is

NetOps needs eight usable addresses in the prod-app-a subnet (`10.20.30.0/26`) for a checkout rollout. IPAM shows that the subnet is full. Many addresses are still assigned to equipment from a spring datacenter consolidation. That equipment was supposed to be retired.

The task is not simply to free every address marked decommissioned. Some decommissioned hosts still carry live traffic through the load balancer. This includes a payments VIP that appears only as a frontend bind. It also includes a pool member that uses a hostname instead of a raw IP address. Other candidates may appear live because they are in an HAProxy backend, but no frontend routes traffic to that backend. Stale DNS records must also be removed for reclaimed addresses. Otherwise, a new checkout host could receive an old name.

Capacity is limited. Exactly eight addresses can be safely reclaimed. Reclaiming fewer than eight does not meet the deployment goal. Reclaiming more than eight affects production.

## What we expect the agent to do

1. Find the prod-app-a subnet in IPAM. List the addresses assigned to decommissioned equipment.
2. Check each candidate against the live load balancer. Check backend servers, whether a frontend routes to those backends, and whether a frontend bind still listens on the address.
3. Resolve pool members that use hostnames before deciding whether they are inactive.
4. Reclaim exactly the eight addresses that are safe to release in IPAM.
5. Remove leftover forward DNS records for every freed address. Do not remove live production names.
6. Do not change anything that carries live traffic. This includes payments backends, the payments VIP, and normal in-service hosts.

## What agents often miss

Agents usually identify most of the correct reclaim set. They also clean up Infoblox for the addresses they free. However, binary reward still fails because they consistently replace one correct address with one incorrect address.

Common mistakes include:

- They assume that every enabled HAProxy backend member is live production. As a result, they do not reclaim an address that exists only in an unrouted legacy backend. They finish with one fewer address than required.
- They trust the ticket’s claim that `hv-edge-1` (`.40`) has been inactive since May. A check of HAProxy servers alone also shows that it is not in any backend. They then reclaim it and often delete the `payments` DNS record. They do this without checking frontend binds, where the address is still used as the public HTTPS VIP.
- When they find the hostname-addressed payments member, they may make the opposite mistake. They may mark it as stale and remove a live pool entry.

Agents do check IPAM, HAProxy, and DNS. However, they often use an incomplete rule for deciding whether traffic is live. They may treat any enabled server as live, or assume that an address is inactive if it is not in a backend. Instead, they must check routing and binds from end to end.
