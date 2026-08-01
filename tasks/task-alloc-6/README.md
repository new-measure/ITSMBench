# task-alloc-6 — Spare-laptop pool allocation (find the six that are really free)

## What this task is

A provisioning request asks for six laptops of one model. The laptops must be issued to a staging bench for a new project. The asset system shows that none of this model are free. Every unit is marked as reserved, deployed, or pending repair.

However, six units can safely be returned to stock. They are unavailable for two different reasons. Some are still on hold for a project that was cancelled months ago. The requests were cancelled, but the hardware was never released. Other units were returned after break-fix work. They passed repair and were cleared for redeployment, but their repair status was never updated.

Some similar units must not be changed. One unit is on hold for a cancelled project but has an open defect case. One unit is still waiting for parts. Several units are on hold for other teams whose requests are still active. The asset system status alone cannot show these differences. The request records and repair tickets provide the required information.

## What we expect the agent to do

1. Find the provisioning request. Read the requested quantity, model, and destination.
2. List every unit of that model. Determine why each unit is unavailable.
3. Check the request records. Identify which holds belong to cancelled work and which holds belong to active work.
4. Check the repair and defect tickets. Identify which units have an open fault and which units were repaired and cleared.
5. Free and issue exactly the six units that both checks show are safe. Include any unit that is still checked out somewhere under a cancelled request.
6. Do not change the faulty unit, the unit waiting for parts, or the live holds that belong to other teams.
7. Close the provisioning request. This records the request as fulfilled instead of only completing the physical work.

## What agents often miss

The main error is using only one source of information. Both checks are required. Using either check alone leads to an incorrect result.

Agents that do not find the request records cannot tell a cancelled hold from a live hold. They may use age or priority instead. They may decide that another team's hold is stale and take laptops promised to that team. They may even cancel that team's request to do this.

Agents that do not read the repair tickets make the opposite error. They trust the asset status. They issue a laptop that has an open defect case. They also miss the two repaired units that are still marked as broken.

The unit most often missed is checked out to a field office under a cancelled request. Agents see "checked out" and assume that it is in use. They do not check why it was issued or whether that reason is still valid. Other units with the same status must not be changed because the reasons for those checkouts are still valid.

Another common error is stopping after moving the hardware. Agents report that the work is complete but leave the provisioning request open and waiting.
