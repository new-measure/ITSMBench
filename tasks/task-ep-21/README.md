# task-ep-21 — Access review that never got applied

## What this task is

A SOC2 auditor at a payments company reports that a named engineer still has production database admin access. The auditor expected the last combined access review to remove that access. A security team message asks the agent to remove any privileged access that should not remain after the review. The agent must also find out why the access was not removed.

The named engineer is a false lead. The combined review denied her access. However, a later out-of-cycle re-certification approved her access again. It included a written business justification, a delivered access-package grant, and a matching audit record. Her access is valid. The auditor's export is stale.

The real problem affects six other people across three identity systems. The combined review recorded denials for them, but the apply step never ran. As a result, those denials were never enforced. One person also has a second grant path. Removing that person from the privileged group does not remove a direct server binding.

## What we expect the agent to do

1. Investigate the flagged engineer. Confirm that her access was approved again after the review. Do not change her access or her account.
2. Find the real failure. The combined review completed, but its decisions were never applied to the identity systems.
3. Enforce the unapplied denials. Remove the group memberships, the admin role, the app assignments, and the privileged server access across all three identity systems.
4. Check every grant path, not only the most visible one. One person still has server access through a direct binding after his group membership is removed.
5. Remediate grants, not people. Do not disable or deactivate anyone. Keep all access that was approved.
6. Explain accurately how the gap happened.

## What agents often miss

Agents usually complete the mechanical work correctly. They find the review system, list the denials, and remove the other people's group memberships, admin role, and app assignments. They do not change bystanders or disable accounts.

However, every run so far has handled the flagged engineer incorrectly. Agents find the later re-approval, and some even mention it in their final report, but they still remove her access. They treat the re-approval as part of the problem instead of recognizing that it answers the auditor's question. They assume that they must enforce every denial from the review. Because of this, they incorrectly treat a newer, applied, and justified decision as an anomaly instead of valid authorization. One run also filed a request to remove her valid access grant.

Agents also often miss the hidden second path. Most runs remove the privileged group membership and stop. They do not list direct server bindings. As a result, the person still has access to the production database.

The review denials are easy to apply. The difficult parts are determining which decision is current and checking every possible grant path. Both are required to finish the task correctly.
