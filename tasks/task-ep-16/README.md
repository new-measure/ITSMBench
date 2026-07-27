# task-ep-16 — Green backup dashboard, failed restore

## What this task is

A monthly restore drill at an analytics company fails: the recovery point the team
expected is not usable, yet the backup dashboard shows green. A ticket asks the on-call
engineer to make sure production systems are actually recoverable and to get to the
bottom of how the dashboard stayed green while backups were not happening.

The cause is a botched alerting cutover. Month-long alert suppressions were left running
over two production systems, two backup jobs were switched off, one database was never
given a backup service at all, and two jobs are tracked under serial numbers instead of
hostnames, so name-based checks miss them. On top of that, one production database
exists only in the asset-management register — not in the main device inventory — under
a name that follows no naming convention, and nothing backs it up.

## What we expect the agent to do

1. Work out what "all production systems" really means: the main device inventory plus
   the server section of the asset-management register — not just one system of record.
2. Find every unprotected or silenced system and fix each one: create the missing backup
   services, re-enable the disabled jobs, and end the leftover alert suppressions —
   including one that hides a live, open backup failure.
3. Handle the tricky identities: systems covered under their serial number rather than
   their hostname, and the register-only database with the odd name.
4. Leave correct things alone: healthy systems, a genuine planned-maintenance window, a
   decommissioned machine whose old backup job must stay off, and the read-only device
   inventory.
5. Close out the ticket honestly.

## What agents often miss

Runs handle almost everything. They find the suppression windows and end them, re-enable
the disabled jobs, create the missing backup service, untangle the serial-number
identities, solve the hidden-failure join, and never touch anything they shouldn't.

What every run misses is the scope question. Each one treats the main device inventory
as the full list of production systems, verifies every device there is covered, and
declares the estate protected. The asset-management register — which holds one more
production database, unprotected and oddly named — never gets listed. Some runs even
query that register for specific hosts they already know about, but no run ever pulls
the full list to ask "is anything in here that I haven't seen?"

In short: the fixing is thorough; the auditing is not. One inventory that looks complete
is taken as proof that the whole estate has been counted.
