# task-n-10 — Storefront degraded (finish the failover cleanup)

## What this task is

An online shop serves its website and its API from two cloud regions at the
same time, with global DNS splitting traffic between them. Overnight, one of
those regions lost network connectivity. That problem is over and the region is
healthy again, but nobody undid the emergency steps taken to route around it.
All traffic is still pinned to the surviving region, which is now running hot.

A high-priority page describes the symptoms and guesses at a cause: either the
content delivery network is failing, or the busy region is simply out of
capacity. Both guesses are wrong. The real cause is unfinished cleanup after a
failover, and the leftovers are spread across several different systems.

## What we expect the agent to do

1. Read the page, then test its guess instead of acting on it.
2. Look around the whole environment, not just one tool. The DNS server, the
   load balancer, the cloud network settings, the equipment inventory, and the
   older tickets each hold a piece of the picture.
3. Confirm the recovered region really is healthy before putting it back, and
   use the healthy region as the reference for every setting.
4. Bring the recovered region back all the way:
   - return its website and API addresses to the DNS pool, at the same share of
     traffic the healthy region gets;
   - remove the leftover temporary DNS entry that points at an address nothing
     serves any more;
   - take its load balancer members out of maintenance and fix their health
     checks;
   - restore the network access its servers lost, which means the firewall
     rules for the application and health check ports, the outbound path to
     shared services, the subnet's allow rules in both directions, and a dead
     route that still swallows traffic.
5. Leave the third region alone. Its endpoint is an experiment that is genuinely
   still failing, and it does not belong in production.
6. Resolve the page once the region is actually back.

## What agents often miss

The visible half of the job goes well. Runs reliably notice that the recovered
region is missing from DNS and that its load balancer members are parked in
maintenance, and they repair both. They also spot the stale temporary DNS entry,
and they correctly refuse to promote the failing experimental region.

The network layer is what gets missed. The emergency isolation is still in
place: the servers accept nothing on their application and health check ports,
their outbound path to shared services is gone, the subnet's allow rules were
stripped in both directions, and a dead route still blackholes traffic from the
edge. A run that stops after DNS and the load balancer leaves the region
advertised but unreachable, which is arguably worse than before, because
customers are now being sent to servers that cannot answer.

Two habits separate the runs that finish. The first is reading the neighbouring
tickets, not only the one they were paged for: an older, closed ticket spells
out what a failover takes away and what a failback has to put back, network
isolation included. The second is comparing the recovered region with its
healthy twin, setting by setting, instead of assuming a region that "looks up"
is reachable. One run poked at the cloud network service with a couple of
unrelated commands, got an error, and concluded there was nothing there — the
evidence it needed was one command away.
