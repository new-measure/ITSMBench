# task-ops-3 — Sign off a weekend change window safely

## What this task is

Cobalt Financial is about to approve its weekend maintenance window for implementation.

You are the change manager and CAB chair. Before any work begins, you must make sure every change scheduled for the window is safe to run. No change may cause a service outage. Every change must be authorized. No change may violate an active change freeze.

Overlapping times do not always mean that changes conflict. Two changes can run during the same hours without risk if they affect unrelated systems. They are unsafe when their configuration items are connected. This includes the same CI, a direct dependency, a shared redundant dependency, or a multi-hop path in the CMDB.

Authorization and freeze rules require separate checks. A change may appear valid based on its own fields but have no real CAB approval record. Its approval may still be in the "requested" state. A non-emergency change may also be scheduled during the freeze.

## What we expect the agent to do

1. List every change scheduled for the maintenance window. Confirm each change's schedule, CI, approval state, and freeze membership using the system of record.
2. Find every pair of changes that overlaps in time and has related CIs in the dependency graph. Check conflicts connected through several dependency steps and conflicts that share a dependency. Do not check only conflicts on the same CI.
3. Neutralize or reschedule every real collision so that the overlap cannot cause an outage. Do not change harmless time overlaps.
4. Stop changes that do not have CAB authorization. Stop non-emergency changes scheduled during the freeze. Do not stop legitimate approved emergencies that the freeze allows.
5. Leave every safe, authorized, and freeze-compliant change scheduled as it is.

## What agents often miss

Agents often treat all overlapping schedules as conflicts. They may cancel unrelated work that can safely run in parallel. They may also miss conflicts that become visible only after matching the schedule with the CMDB. Conflicts on the same CI are easy to find. Direct dependency, redundant dependency, and two-hop dependency conflicts are often missed and left running.

Policy checks can fail in both directions. Agents may trust the approval field on a change and miss that there is no approved CAB record. They may also cancel a change that appears unsigned even though it has approval in the approver table.

Freeze checks can fail in similar ways. Agents may leave non-emergency work scheduled during the freeze. They may also stop a legitimate emergency that is allowed during the freeze.

The window is safe only when the schedule, dependency graph, approvals, and freeze are checked together. Harmless overlaps must remain unchanged.
