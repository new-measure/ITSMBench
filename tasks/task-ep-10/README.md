# task-ep-10 — Release that lied

## What this task is

A release engineer at Orbitware receives an escalated Jira ticket, **RLY-2301**. A customer upgraded to Relay 4.7.0. The customer reports that the claimed CSV formula-injection security fix is still broken. The ticket suggests a false possibility: the fix may have been removed during a rollback. The ticket asks the agent to fix the problem and check which other claims in the 4.7.0 release notes are incorrect.

The release automation created 4.7.0 from Jira metadata while the release manager was away. It marked every issue tagged `4.7.0` as Done. It then published release notes from that issue list. Only four of the eight claimed fixes were included in the release. Four were not included:

- One had an approved PR, but the PR was never merged. This was the disputed security fix.
- One was merged and then reverted.
- One was merged after the release was created.
- One was never built.

A ninth fix was included in the release window. However, it is filed under a separate, unreleased Jira version named `4.7`. Because of this, it is missing from both the release notes and the 4.7.0 issue list.

## What we expect the agent to do

1. Investigate RLY-2301. Reject the rollback explanation when the evidence does not support it.
2. Merge the approved security PR that has passing CI. Do not only update Jira or Confluence records.
3. Publish a patch release for fixes that are now real or become real later. Create a released Jira version, publish a GitHub release, and publish patch notes that document those fixes.
4. Correct the inaccurate 4.7.0 release notes and issue states. Remove claims about fixes that did not ship. Reopen and remove the version tag from items that never shipped. Add the fix from the separate Jira version that did ship.
5. Do not change the four fixes that truly shipped, the bad “reland” PR with requested changes and failing CI, older releases, or unrelated records.
6. Close the trigger only after the customer-facing fix can actually be shipped.

## What agents often miss

Agents usually investigate the release correctly. They identify which claimed fixes are real. They merge the disputed security PR. They reopen the reverted and never-built items. They do not merge the bad reland PR. They also correct many parts of the release notes.

However, they often do not complete the release process:

- Almost every run merges the security fix into `main` but does not publish a patch release. There is no released Jira version, GitHub release, or patch notes. The customer remains on vulnerable 4.7.0. This is an active exposure, not only a record-keeping problem.
- Because the agents know they have not shipped the fix, they often intentionally leave RLY-2301 In Progress.
- Agents also sometimes miss the separate-version fix, RLY-2172 under `4.7`. Some runs find it. Others do not retag it into 4.7.0 or add it to the release notes.

The main problem is that agents treat merging the PR as completion. The task is not complete until the fix is actually released to the customer. Most trials miss this requirement.

Full calibration details are in `workspace/CALIBRATION.md`.
