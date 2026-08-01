# task-n-15 — Subdomain-takeover audit of a DNS zone

## What this task is

A security finding identifies records in the corporate DNS zone as possible subdomain-takeover risks. These records seem to point to targets that are no longer live. The finding blames a recent cloud migration, but that claim is a decoy. It does not identify any specific records.

Audit the entire zone. For each record, decide whether its target is truly dead or still live. Remove or repoint dead records. Leave live records exactly as they are. Then resolve the finding.

A target is not dead based only on its name. A record's target is live only if something still owns it. This can be:

- An attached network interface that has the address as either its primary or a secondary address.
- An allocated public IP.
- An in-service host.

A detached interface does not count as live.

For alias, mail, and nameserver records, follow the full chain. An alias may point to another alias through several hops. Check whether the chain ends at a live target or an approved external dependency.

Dead records exist in every record type. Several live records may look external or unclaimed, but they must remain unchanged.

## What we expect the agent to do

1. Ignore the claim that the migration caused the problem. Audit every record of every type in the zone. Do not check only address and alias records.
2. Check each record's target against live infrastructure. A target is live if it is owned by an attached interface through any of its addresses, an allocated public IP, or an in-service host. Follow alias, mail, and nameserver chains one hop at a time until they reach a live end.
3. Remove or repoint every record that is truly dangling.
4. Leave all live records unchanged. This includes approved external dependencies, addresses used as secondary addresses on attached interfaces, and aliases that reach a live target only after several hops.
5. Do not change the out-of-scope zone or unrelated records. Resolve the finding.

## What agents often miss

Current runs usually handle this task well. The task is difficult because every quick method for deciding whether a target is dead gives incorrect results for some records in this zone.

Checking only the address range keeps dead hosts in the internal range and deletes live public hosts. Treating any existing interface at an address as live keeps records for detached interfaces. Checking only an interface's primary address deletes records that point to a live secondary address. Following an alias for only one hop deletes live aliases that require several hops to reach a live target. Listing only address and alias records misses dangling mail and nameserver records. Each shortcut gives a confident but incorrect result for a different group of records.

The task also requires restraint. Several records look external or unclaimed, but they are approved dependencies and must remain. An entire out-of-scope zone must not be changed. A broad cleanup fails just as much as an incomplete audit. Dangling and live records are mixed throughout the zone. Their position does not identify them, and no bulk action can replace checking each target.

This task requires a separate decision for every record. Check what actually owns each target. Follow all chains. Treat secondary addresses on attached interfaces as live. Check interface attachment state. Keep live records that only appear to be dead.
