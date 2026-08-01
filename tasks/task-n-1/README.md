# task-n-1 — Decommission a service, records and all

## What this task is

A change request asks the on-call network engineer to retire a legacy billing service. This includes its hosts, subnet, and VLAN. The change lists the hosts. The engineer must remove the service completely. No decommissioned resource should remain allocated, resolvable, or marked as operational. The engineer must then close the change.

Two issues make this more than a simple checklist. One listed host is still active. It was recently moved to a production subnet and was seen yesterday. It must not be changed. The change request is outdated about this host, and the current data confirms that it is active.

Also, each host has records in several systems that do not reference each other. These records can include a device record, an address, a DNS name, a configuration item, and, for one host, a separate business-application element. There is no single view that shows every reference to a host. A complete teardown requires finding and clearing each host's records in every relevant system.

## What we expect the agent to do

1. Read the change. Verify that each listed host is actually out of service before removing it. Do not change the host that is still active.
2. Remove every record for each retired host. Archive the device, free all of its addresses, remove its DNS records, retire its configuration item, and remove its business-application element if it has one. One host has a second management address that must also be freed.
3. Remove dangling records that refer to hosts that have already been removed.
4. Free the subnet and VLAN only after every host on them has been cleared.
5. Do not change the active host, its records, or any unrelated infrastructure.
6. Close the change.

## What agents often miss

Current runs usually complete this task correctly. They verify each listed host against the current system data. They do not change the active host. They clear the retired hosts from every system and close the change.

The difficult part is that the remaining records are different for each host. One host has only a stale DNS record. One host has a second management address that is missed if the agent checks only one address. One host owns a business-application element that is separate from the host record. The subnet cannot be freed until its final child record is cleared. A process that only archives each device and clears one address will complete most of the work but leave other records behind. Those records will still refer to infrastructure that no longer exists.

The active host on the change list requires a judgment call. The change request names it, but current system data shows that it is still active. It was seen yesterday and has already moved to another subnet. Removing it would incorrectly follow outdated change wording instead of current data. The correct action is to leave it unchanged. This does not prevent the retired subnet from being freed because the active host is no longer on that subnet.

In short, removing the obvious retired hosts is simple. The main challenge is removing every separate record they left behind without removing the host that appears retired in the change request but is still active.
