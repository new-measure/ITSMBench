# task-iam-12 — Segregation-of-duties conflicts in effective access

## What this task is

An IAM / access-governance engineer at Meridian Trade & Finance is addressing a Q3 access review finding. Some users have toxic segregation-of-duties entitlement combinations in the finance and procurement Salesforce org. The finding requires the engineer to resolve real conflicts with the least disruption. The engineer must then close the finding against the SoD control matrix.

A user's actual permissions are the union of three layers:

- The profile's baseline permission set
- Directly assigned permission sets
- Permission sets inherited through an assigned permission-set group

For every real conflict, the two parts of the toxic pair come from different layers. An audit of only one layer does not detect these conflicts.

The finding does not name any users. Only a minority of the large user population have real conflicts. Some conflicts exist near approved compensating-control exceptions. Some toxic grants are included in the same supplementary permission set as a valid add-on duty that clean role-peers also have. Simply unassigning that permission set removes the conflict, but it also removes work the user must keep.

## What we expect the agent to do

1. Read the GRC finding. Load the SoD control matrix and all compensating-control exceptions. Do not assume that every rule has a violator.
2. Audit effective permissions for the full user population. Compute the union of profile permissions, direct assignments, and permission sets inherited through groups.
3. Check every apparent conflict against the matrix. Confirm that it is real. Do not change users who have approved exceptions.
4. Resolve every real conflict with the least disruption. Remove the supplementary toxic permission. Do not remove the profile-conferred primary duty that defines the user's role.
5. If a toxic capability is bundled with a valid add-on, clear the toxic grant without removing the add-on. For example, forecast management may be a valid duty that peers also have. Unassign permissions at a finer level or grant the clean duty again.
6. Use per-user fixes instead of changing a shared permission-set group that is also used by an exception holder.
7. Do not change non-conflicting dual holders, benign extras, or clean peers. Do not deactivate users as a shortcut.
8. Record the result and close the finding.

## What agents often miss

Agents can usually compute the effective-permission union and find the conflicts. They often make mistakes when deciding how to fix them.

A common excessive fix involves bundled permissions. The toxic capability may be in the same supplementary permission set as a valid, non-conflicting duty. Unassigning the entire set removes the SoD conflict. It also removes work that the user's clean peers still have. The finding requires the least-disruptive remediation. The agent must preserve the add-on or grant it again without the toxic permission.

Another common mistake is changing a shared permission-set group used by both a real violator and a user with an approved exception. Changing the group fixes the violator but breaks the exception. The correct action is a per-user fix. The agent must also check the full population. Stopping after finding the first few conflicts leaves other violators with active conflicts. The finding applies to the entire environment, not a sample.
