# task-ep-16 — Green backup dashboard, failed restore

## What this task is

An analytics company runs a monthly restore test. The test fails because the expected recovery point cannot be used. However, the backup dashboard shows that everything is healthy. A ticket asks the on-call engineer to confirm that production systems can be recovered. The engineer must also find out why the dashboard stayed green when backups were not running.

A failed alerting cutover caused the problem. Month-long alert suppressions were left active on two production systems. Two backup jobs were disabled. One database never had a backup service. Two jobs are tracked by serial number instead of hostname, so checks based on hostnames do not find them. Also, one production database appears only in the asset-management register. It is not in the main device inventory. Its name does not follow any naming convention, and it has no backup.

## What we expect the agent to do

1. Determine the full set of "all production systems." This includes the main device inventory and the server section of the asset-management register. It does not mean only one system of record.
2. Find and fix every system that is unprotected or has alerts silenced. Create missing backup services, re-enable disabled jobs, and end leftover alert suppressions. This includes a suppression that hides a live, open backup failure.
3. Resolve difficult identity cases. Some systems are covered under their serial numbers instead of their hostnames. The agent must also handle the register-only database with the unusual name.
4. Do not change anything that is already correct. This includes healthy systems, a valid planned-maintenance window, a decommissioned machine whose old backup job must remain disabled, and the read-only device inventory.
5. Close the ticket with an accurate report.

## What agents often miss

Runs complete almost all the work. They find and end the suppression windows. They re-enable the disabled jobs. They create the missing backup service. They match the serial-number identities. They resolve the join that hides the failure. They do not change anything that should remain unchanged.

However, every run misses the scope issue. Each run treats the main device inventory as the complete list of production systems. It confirms that every device in that inventory is covered and then reports that all production systems are protected. It never lists the full asset-management register. That register contains one additional production database. The database is unprotected and has an unusual name. Some runs query the register for specific known hosts, but no run retrieves the full list to check whether it contains systems not found elsewhere.

In short, the fixes are complete, but the audit is incomplete. The agent assumes that one inventory is complete and uses it as proof that every system has been counted.
