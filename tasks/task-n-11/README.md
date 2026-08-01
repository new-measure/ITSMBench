# task-n-11 — Dispatch names resolve to the wrong place

## What this task is

A P1 ticket says users cannot reliably reach the dispatch services by name. Some requests also go to the wrong server. The ticket says a weekend maintenance window on the DNS appliance caused the problem.

That is not the cause. A few days before the maintenance window, the dispatch servers moved to a new set of addresses. The old addresses were returned to the pool. The closing note for that change says the DNS cleanup was left for someone else. Nobody completed it. As a result, the zone now conflicts with the inventory in several ways.

## What we expect the agent to do

First, verify the claim in the ticket instead of accepting it. The zone and the nameservers are healthy. The maintenance record says no record data was changed. Use this evidence to rule out the reported cause.

Next, determine what is currently live. Use both the asset and address inventory and the live cloud interfaces. A host is live if it has a working interface and an assigned address. Compare every name record in the zone with this information. Fix every mismatch:

- Names that still point to released addresses that belong to nobody.
- Names that point to live addresses assigned to a different host. This causes some requests to go to the wrong server.
- Running hosts that have no record.
- The shared service name that distributes traffic across several addresses, including one dead address.
- Stale IPv6 records with the same problems as the IPv4 records.
- Aliases that point to names that no longer exist.
- Records for hosts that were actually retired. Remove these records.

Leave these items unchanged: healthy records, the neighboring service tier that was migrated correctly, the nameservers, the zone itself, and one long-lived host that still correctly uses an old address. Finish by closing the ticket. Add a note that states the real cause.

## What agents often miss

Agents usually rule out the maintenance correctly. They also usually update the obvious address records correctly. The main differences between runs are how completely agents check the records and how carefully they finish the task.

The most common mistake is treating all DNS records as one record type. Agents list and fix the address records, then stop. They do not list the IPv6 records or the aliases. Another common mistake is filtering the alias list by name. The two broken aliases have customer-facing service names. A search for "dispatch" finds only the alias that is already correct. The broken aliases remain unchanged.

The second mistake is deciding whether a host is live by checking only one system. One host has no asset database entry, but it has a live interface. It can look retired and may be deleted by mistake. Deleting it would remove a working service from the network.

The final mistake happens when closing the ticket. Some agents set the ticket state using the label shown in a report instead of the value stored by the system. The ticket then appears closed, but its stored state does not change.
