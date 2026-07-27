# task-n-11 — Dispatch names resolve to the wrong place

## What this task is

A P1 ticket says users cannot reliably reach the dispatch services by name, and
some requests land on the wrong server. The ticket blames a weekend maintenance
window on the DNS appliance.

That is not the cause. A few days earlier the dispatch servers were moved onto a
new set of addresses and the old addresses were handed back to the pool. The
change that did this says, in its own closing note, that the DNS cleanup was left
for someone else. Nobody did it, so the zone now disagrees with the inventory in
several different ways at once.

## What we expect the agent to do

First, check the claim in the ticket instead of acting on it. The zone and the
nameservers are healthy, and the maintenance record says no record data was
touched, so the reported cause can be ruled out with evidence.

Then rebuild the picture of what is actually live. Two systems together tell the
truth: the asset and address inventory, and the live cloud interfaces. A host is
live if it holds a working interface and an assigned address. Compare every name
record in the zone against that picture and fix each disagreement:

- Names still pointing at addresses that were released and belong to nobody.
- Names pointing at addresses that are live but belong to a different host — this
  is why some requests land on the wrong server.
- Hosts that are running but have no record at all.
- The shared service name that spreads traffic across several addresses, one of
  which is dead.
- The IPv6 records, which are stale in the same way as the IPv4 ones.
- Aliases pointing at names that no longer exist.
- Records for hosts that really were retired, which should go.

Some things must be left alone: the healthy records, the neighbouring service tier
that was migrated correctly, the nameservers and the zone itself, and one
long-lived host that still legitimately sits on an old address. Finish by closing
the ticket with a note that states the real cause.

## What agents often miss

Ruling out the maintenance is done well. Repointing the obvious address records is
also done well. What separates runs is how completely they look, and how carefully
they finish.

The most common miss is treating "DNS" as one kind of record. Runs list the
address records, fix them, and stop — never listing the IPv6 records or the
aliases. A related trap is filtering the alias list by name: the two broken
aliases are named after customer-facing services, so a search for "dispatch"
returns only the one alias that was already fine, and the broken ones stay
invisible.

The second miss is judging a host by one system. One host has no entry in the
asset database but does hold a live interface, so it looks retired and is easy to
delete. Deleting it would take a working service off the network.

The last miss is the close-out. Some runs set the ticket state using the label
they saw in a report rather than the value the system actually stores, so the
ticket reads as closed while the stored state never changed.
