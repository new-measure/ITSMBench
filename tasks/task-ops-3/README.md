# task-ops-3 — Sign off a weekend change window safely

## What this task is

Cobalt Financial is about to release its weekend maintenance window to implementation.
You are the change manager and CAB chair. Before anything runs, the entire set of changes
scheduled for that window must be left safe to execute: nothing that would take a service
down, nothing unauthorized, and nothing that violates an active change freeze.

Time overlap alone does not mean conflict. Two changes can run in the same hours and be
harmless if they touch unrelated systems; they are dangerous when their configuration
items collide — same CI, direct dependency, shared redundant dependency, or a multi-hop
path in the CMDB. Authorization and freeze rules are separate checks: a change may look
fine on its own fields but lack a real CAB approval record, still sit in "requested"
approval, or be a non-emergency scheduled inside the freeze.

## What we expect the agent to do

1. List every change scheduled for the maintenance window and confirm each schedule,
   CI, approval state, and freeze membership from the system of record.
2. Find pairs that overlap in time **and** whose CIs are related in the dependency graph
   — including transitive and shared-dependent collisions, not only same-CI clashes.
3. Neutralize or reschedule each real collision so the overlap no longer threatens an
   outage; leave harmless time-overlaps alone.
4. Stop changes that are not CAB-authorized, and stop non-emergency work that sits inside
   the freeze; leave legitimate approved emergencies that the freeze permits.
5. Leave every safe, authorized, freeze-compliant change scheduled as it is.

## What agents often miss

Agents often treat "overlapping schedules" as the whole problem and either over-cancel
unrelated parallel work or miss the collisions that only appear after joining the
schedule to the CMDB. Same-CI clashes are easy; direct, redundant, and two-hop dependency
collisions are the ones that get left running.

Policy checks fail in both directions. Runs trust a change's own approval field and miss
that there is no approved CAB record — or they cancel a change that looks unsigned but is
approved through the approver table. Freeze handling is similarly brittle: non-emergency
work inside the freeze is left up, or a legitimate emergency allowed during the freeze is
stopped. In short: the window is only safe when schedule, graph, approvals, and freeze
are checked together, and harmless overlaps are left alone.
