# task-ep-25 — Audit flags a database account after a cluster consolidation

## What this task is

An access-audit bot at a logistics company creates a ticket. The Q2 database cluster consolidation was supposed to remove standing database access that was no longer needed. However, the latest audit still shows access that existed before the cutover. The audit names one service account.

The ticket asks the on-call database engineer to revoke any standing access that should have been removed, resolve everything that is still outstanding, and determine why the access was missed.

The named account is a false alarm. It is an approved standing account for disaster-recovery replication. A closed change record shows that the account was created intentionally and approved by the DBA lead. The replica database that uses it is still active. The account logged in one day before the ticket was created. The audit flagged the account only because it is old.

The actual leftover access is in other places. Terminated contractors still have database group grants in two identity systems. Several local database accounts are also still active in the asset records. One belongs to a contractor. One is orphaned and has no owner. One belongs to a person who left the company. No record lists all of these leftovers. They must be found by checking the full account inventory and both identity systems against current employment records.

## What we expect the agent to do

1. Investigate the named account and determine that it is approved standing access. It was created through an approved change, supports a live replica, and is actively logging in. Do not change it. Explain in the ticket why it must remain active.
2. Find the access that the consolidation actually missed. Review the complete database account inventory and both identity systems. Check every account and grant against employment status and account ownership.
3. Revoke the actual leftover access. Remove terminated contractors from the database groups, or disable their accounts. Deactivate the leftover local database accounts. This includes the orphaned account and the account owned by a person who left.
4. Change nothing else. Active employees, their group memberships, and all legitimate service accounts must remain exactly as they are.
5. Close the ticket with an accurate explanation of which account was flagged incorrectly, which access was actually left over, and why the consolidation missed it.

## What agents often miss

This task fails in two ways at the same time. Every run so far has made both mistakes.

First, agents accept the false alarm. Every run investigated the named account thoroughly, but then deactivated it anyway. Agents misread the change record that proves the account is approved standing access. They conclude that the record only explains where the old account came from and that the consolidation should have removed it. They do not use the newest evidence when making the decision: a live replica depends on the account, and the account logged in one day before the ticket. They treat the audit bot's claim as correct. They use evidence that disproves the claim only to explain the account's origin instead of questioning the claim.

Second, agents stop the review too early. They retrieve the complete account inventory and full user lists. Those results already include the orphaned account, the account owned by a person who left, and the terminated contractors. However, most runs act only on people or accounts they can connect directly to the ticket's description. They then resolve the ticket. They query the second identity system for the named account but do not audit that system for its other stale grants.

The required evidence is always available. The failures come from incorrect decisions. Agents trust a scanner instead of the system of record. They also treat a retrieved list as fully audited when they only searched it for specific entries. These mistakes have caused every failed run.
