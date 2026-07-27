# task-ep-22 — Traffic still landing on a dead datacenter

## What this task is

A ticket at a logistics company: the January move off the old ord1 datacenter was
supposed to leave nothing pointing at those hosts, but an API hit a dead machine there
today and returned errors. The on-call traffic engineer is asked to make sure nothing
still routes to any decommissioned host, finish whatever the move left unfinished, and
get to the bottom of how this slipped.

The move was left half done. Dead hosts are still wired into the load balancer —
including one hiding in a shared gateway pool that serves every service. Two services
were cut over onto the wrong machines: one now runs on another service's host, and one
points at the payment service's host. Some DNS names still resolve into the old
datacenter. The service registry still routes two services at dead hosts. Half the
cutover change tickets were never closed, and a stale alert is still open. One old
machine is a permanent exception: a legacy reporting host that never moved and must
keep working.

## What we expect the agent to do

1. Fix the failing service everywhere it is wired — including the dead member hidden in
   the shared gateway pool, not just its own backend.
2. Sweep every place routing lives — the load balancer, DNS, and the service registry —
   and remove or repoint everything that still targets a decommissioned host.
3. Catch the two cross-wired services and point each at its own new host, without
   breaking the services whose hosts they were borrowing.
4. Leave the legacy reporting host alone: it stays routed, its records stay, and it must
   not be retired.
5. Close out the stranded change tickets and the stale alert honestly, and explain how
   the move was left unfinished.

## What agents often miss

Runs do the visible routing well. Every run fixed the failing service in both places,
repointed the wrong-host services correctly, cleaned up DNS, spared the legacy host and
every healthy service, closed the change tickets, and told the right root-cause story.

What every run misses is the third place routing lives. The load balancer and DNS get
audited; the service registry never does — even though it comes up in searches and two
of the unfinished change tickets belong to exactly the services it still misroutes. One
run identified the two dead addresses precisely and even released them in the IP
records, but never asked what still pointed at them. Runs also closed the per-service
cutover tickets as successful while the registry still routed those services at a dead
host — the ticket got closed on the strength of the surfaces already fixed.

In short: the surfaces agents think of as "routing" get swept thoroughly; the one
system they didn't think to count stays broken, and a clean-looking audit of the other
two is taken as proof the whole estate is clean.
