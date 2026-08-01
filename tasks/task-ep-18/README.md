# task-ep-18 — Patched fleet that isn't

## What this task is

A security review says that a critical application vulnerability was patched across the fleet several weeks ago. However, the endpoint-security tool still reports that one production server has the old version. A ServiceNow incident asks the agent to confirm that the fleet is fully remediated and find out why the finding still appears.

The flagged server is a false alarm. It was patched and verified. Only the security tool's vulnerability record is stale. The larger problem is the patch process. The patch wave used a device group in the security tool. That group came from a stale list. Several vulnerable production machines were never added to it. One machine is hidden from the console. One appears only in the asset inventory. One appears only in the device-management directory. Another is in a maintenance hold even though its maintenance window has passed. One legacy host has a valid exemption and must not be changed.

The ticket does not state any of this. The agent must discover it by comparing the security tool, the asset inventory, and the device directory.

## What we expect the agent to do

1. Clear the flagged server. Show that its patch was successfully applied and that the finding is stale. Do not make any destructive changes to it.
2. Check whether the rest of the fleet is actually patched, as the ticket implies. Review every inventory, not only the security tool. Machines that are missing from one system may appear in another.
3. Correct the patch cohort. Add every production machine that is still vulnerable to the deployment group. Unhide the hidden machine. Remove the parked database from its expired maintenance hold so it can be patched.
4. Keep the valid exceptions unchanged. The exempt legacy host must remain on hold. Machines that are already patched must remain where they are. Do not change anything outside production.
5. Close the incident with an accurate explanation of what happened.

## What agents often miss

Agents usually diagnose the problem correctly. Every run identifies the flagged server as a false alarm, finds the stale security-tool record, and identifies most or all of the machines that the patch wave missed. This includes machines that appear only in the asset inventory or the device directory.

Agents often fail when they need to make the changes that repair the fleet. Some write a strong summary that names every vulnerable machine, but then close the ticket without changing the group. Some rebuild the deployment group so it contains only the machines that are still waiting for patches. This incorrectly removes the already-patched hosts and the flagged server, even though their group membership was correct. Some calculate the wrong cohort and include unrelated machines that were never in scope. Almost every run treats the parked database's "moved to maintenance hold" note as a reason to leave it unchanged. They do not check whether the hold is still valid. The related work order is still open, but the maintenance window has passed and the machine is still vulnerable.

Finding the missed machines is usually done well. Completing the task requires making the correct changes. Add the correct machines, leave unrelated and correctly configured machines unchanged, and question the stale maintenance hold instead of assuming it is still valid.
