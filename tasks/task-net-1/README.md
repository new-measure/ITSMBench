# task-net-1 — Checkout outage after a "successful" renumbering wave

## What this task is

An on-call network operations engineer at Meridian Foods Group receives a store-ops incident. Checkout has failed intermittently since last night's approved VLAN shutdown. The VLAN change appears consistent and complete, but it is not the root cause. It exposed an incomplete migration from an earlier renumbering program.

Meridian is integrating another company's network. It moved Hall 1 servers off an old subnet so that the range could be reserved for the integration. Device42 already contains the correct new address for every host. Automation updated DNS, load balancers, egress, and security groups in waves. One wave completed successfully. The next wave crashed before it finished, but its change request was closed as successful. A name filter also silently skipped a group of legacy hosts in every wave. Both subnets remained routed at the same time for weeks. This hid every stale record until the old VLAN was shut down.

The outage is intermittent because the checkout backend still contains one migrated server and one stale server. These servers were at the point where the failed wave stopped. References to the old subnet remain in DNS, load-balancer config, load-balancer runtime, egress firewall rules, and cloud security groups. Each host has a different set of remaining references. Fixing one system does not update the others.

## What we expect the agent to do

1. Read the incident and the VLAN change that was blamed. Then investigate what still depends on the retired subnet instead of reverting the change.
2. Use Device42 as the authority for addresses. The current IP for every host is already recorded there. Its audit trail also contains the old-to-new address history.
3. Fix checkout and other load-balancer backends whose config still points to old addresses. Also clear stale runtime rows. Config and runtime are separate planes.
4. Use the automation records and address history to reconstruct the failed wave and identify the skipped legacy hosts. Automation re-created some records and then stopped before completing the run. The wave change lists never include the `mfg-*` names that Device42 had already renumbered.
5. Find every remaining reference to the old subnet in DNS, load balancers, egress firewall rules and groups, and security-group ingress. Repoint each reference to the address recorded in Device42, or to the new /24 for the hall group.
6. If a security group still allows an old /32, revoke it and authorize the new /32 on the same port. Follow the pattern used for hosts that already completed migration.
7. Activate the egress policy after editing it. Otherwise, the rule changes are staged but not live.
8. Do not change fully migrated hosts, hand-fixed DNS records that are already correct, similar-looking live subnets, or Device42 itself. Resolve the incident only when nothing depends on the dark range.

## What agents often miss

Many agents correctly avoid undoing the VLAN change and fix the obvious checkout config mismatch. They often fail to complete the independent work required in every system.

Load-balancer config can be correct while runtime rows still serve old addresses. Reading the config again does not show the runtime plane. Egress rule changes can appear complete in a rule readback, but they remain pending until the policy is explicitly activated. Fixing DNS or the load balancer does not remove the same old /32 from a security group. Fixing the security group does not update DNS or the load balancer.

The skipped legacy hosts and deeply listed firewall rules are easy to miss. Some hosts have no DNS or load-balancer entry. They appear only when searching egress or security groups for the old subnet. Some rules are beyond the first page of an unfiltered list. If the closed "successful" change request is treated as correct, the investigation stops before these remaining references are found. Deleting working records to remove the old address also does not achieve the goal. Services must be repointed, not removed.
