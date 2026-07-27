# task-n-1 — Decommission a service, records and all

## What this task is

A change request asks the on-call network engineer to retire a legacy billing
service — its hosts, its subnet, and its VLAN. The change lists the hosts. The job
is to tear the service down so that nothing decommissioned is still allocated,
still resolvable, or still marked operational, and then close the change.

Two things make it more than a checklist. One host on the list is not actually
dead — it was recently migrated onto a production subnet, was seen yesterday, and
must be left alone; the change wording is stale on that point, and the world's own
data shows it. And a host's footprint is spread across systems that do not
cross-reference each other: a device record, an address, a DNS name, a
configuration item, and, for one host, a separate business-application element.
There is no single "what references this host" view, so a full teardown means
chasing each host through every system it touches.

## What we expect the agent to do

1. Read the change, then verify each listed host is genuinely out of service
   before removing it — and spare the one that is still live.
2. For each retired host, clear its footprint everywhere: archive the device,
   free its addresses (including a second management address where one exists),
   remove its DNS records, retire its configuration item, and remove the
   business-application element where one exists.
3. Clean up the dangling records that point at hosts already gone.
4. Free the subnet and VLAN only once every host on them is cleared.
5. Leave the live host, its records, and all unrelated infrastructure untouched.
6. Close the change.

## What agents often miss

Current runs handle this task well: they verify each listed host against what the
world actually reports, spare the one that is still live, clear the retired hosts
across every system, and close the change.

What makes it non-trivial is that a host's debris is uneven. One carries only a
stale DNS record, one has a second management address that a single-address pass
skips, one owns a business-application element that is not the host record at all,
and the subnet can only be freed once its last child is cleared. A uniform
"archive the device and clear one address" loop gets most of the way and quietly
leaves the rest — records still referencing infrastructure that no longer exists.

The judgment call is the live host on the change list. Removing it because the
ticket named it means acting on stale wording the world contradicts: the host was
seen yesterday and has already moved to a different subnet. Sparing it is correct,
and it does not block freeing the retired subnet, because it is no longer on it.

In short: retiring the obvious hosts is straightforward. Finishing every scattered
record they leave behind, and not tearing down the host that only looks retired,
is what the task is really testing.
