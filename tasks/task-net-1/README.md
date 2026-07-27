# task-net-1 — Checkout outage after a "successful" renumbering wave

## What this task is

An on-call network operations engineer at Meridian Foods Group picks up a store-ops
incident: checkout has been intermittently failing since last night's approved VLAN
shutdown. The change looks coherent and complete — and it is not the root cause. It
exposed a latent half-migration from an earlier renumbering program.

Meridian is absorbing another company's network and moved Hall 1 servers off an old
subnet so the range could be reserved for the integration. Device42 already holds the
correct new addresses for every host. Automation pushed DNS, load balancer, egress,
and security-group updates in waves. One wave finished cleanly. The next crashed
mid-flight — yet its change request closed as successful. A name filter also silently
skipped a set of legacy hosts in every wave. Both subnets stayed routed in parallel for
weeks, masking every stale record until the old VLAN went dark.

The outage is intermittent because the checkout backend still has one migrated server
and one stale one — the seam of that crashed wave. Residual old-subnet references are
scattered across DNS, load-balancer config, load-balancer runtime, egress firewall
rules, and cloud security groups, with a different leftover set per host. Cleaning one
system never cues the others.

## What we expect the agent to do

1. Read the incident and the blamed VLAN change, then shift suspicion to what still
   depends on the retired subnet rather than reverting the change.
2. Use Device42 as the address authority: every host's current IP is already there,
   including the old→new lineage in the audit trail.
3. Fix the checkout (and other) load-balancer backends where config still points at old
   addresses, and clear stale runtime rows — config and runtime are separate planes.
4. Reconstruct the failed wave and the skipped legacy hosts from provenance (automation
   re-created some records and stopped mid-run; wave change lists never mention the
   `mfg-*` names that Device42 already renumbered).
5. Sweep every remaining reference to the old subnet across DNS, load balancer, egress
   firewall rules and groups, and security-group ingress; repoint each to the Device42
   address (or the new /24 for the hall group).
6. Where a security group still allows the old /32, revoke it and authorize the new /32
   on the same port — matching hosts that already finished migration.
7. Activate egress policy after edits so rule changes are live, not merely staged.
8. Leave fully migrated hosts, hand-fixed DNS that is already correct, lookalike live
   subnets, and Device42 itself untouched. Resolve the incident when nothing depends on
   the dark range.

## What agents often miss

Many runs correctly refuse to undo the VLAN change and fix the loud checkout config
mismatch. Orthogonality is what breaks completeness.

Load-balancer config can look fixed while runtime rows still serve the old addresses —
re-reading config never shows that plane. Egress rule edits can look done in a rule
readback while activation stays pending until explicitly activated. Cleaning DNS or the
load balancer never cues the same old /32 lingering in a security group, and the reverse
is also true.

The skipped legacy hosts and the deep firewall rules are easy to under-discover: some
have no DNS and no load-balancer entry and only appear when sweeping the old subnet in
egress or security groups; some rules sit past the first page of an unfiltered list.
Treating the closed "successful" change request as ground truth stops the investigation
before those residues are found. Deleting working records to clear the old address also
fails the real goal — services must be repointed, not removed.
