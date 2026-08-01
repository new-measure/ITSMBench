# task-ep-15 — A credential leak that was never fully cleaned up

## What this task is

A payments company's secret scanner flags an API key again. The key was exposed in a June credential leak. A follow-up ticket asks the on-call engineer to rotate any credentials that are still exposed from that incident. The engineer must also find out what cleanup work was missed.

The June incident appears to be closed, but the cleanup was not completed. Several sub-tickets were marked done even though the work did not happen. One credential was rotated in the credential store, but its CI copy still has the value from before the leak. Another credential was updated in CI, but its copy in the credential store was never updated. A service account's API token was marked "revoked," but it is still active and in use. One sub-ticket is still open. One leaked credential never had a ticket. It is a database password that was posted as plain text on a wiki inventory page. The only evidence of this leak is an open scanning alert on another repository.

## What we expect the agent to do

1. Do not assume that a ticket status proves the work was completed. Check the actual system state for every cleanup item from the June incident. The credential store and CI secrets contain separate copies. Both copies must be current.
2. Complete the work that was falsely marked done or was forgotten. Rotate each stale credential on the side that was missed. Revoke the service token that is still active. Deactivate the old app that was scheduled for retirement.
3. Investigate the leak that had no ticket. The open alert on the second repository points to a credential that does not exist in the credential store. Find its actual location on the wiki credential inventory page. Remove the plain-text value.
4. Resolve the scanning alerts only after the underlying exposure has been removed.
5. Do not change anything that is already correct. Leave properly rotated credentials, active apps and tokens, and unrelated pages unchanged.
6. Close the tickets with an accurate explanation of what was missed and why.

## What agents often miss

Runs usually complete the visible checklist. They usually handle the flagged payments key, the service token that is still active, the legacy app, and the alert on the original repository. They also usually avoid changing anything that should remain unchanged.

Problems occur when a run treats one system as proof that another system is correct. A run may see that a CI secret was updated in June and report that the rotation was "verified." It may not check the credential store, where the password still has its value from before the leak. Some runs also close the still-open "rotate this credential" ticket as stale for the same reason. This closes a ticket that describes real unfinished work. The opposite problem also happens. A run sees that the credential store shows a June rotation, so it does not check the CI copy, which still has the old value.

The untracked credential is missed more than any other item. Runs see its open alert. Some even resolve the alert as "revoked." However, no run so far has searched for the credential's actual location. As a result, the plain-text password remains published on the wiki.

In short, runs fix the items that a status page reports as broken. To finish the task, the agent must verify that every reported fix actually happened for every copy of each credential.
