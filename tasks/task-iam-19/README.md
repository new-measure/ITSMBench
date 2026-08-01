# task-iam-19 — Break-glass account used overnight

## What this task is

This is a security incident at a payments company. Someone signed in to the registered break-glass emergency administrator account and used it overnight. There is no approved authorization for this use.

The ticket asks the on-call engineer to identify everything the account did, restore the environment to its previous state, secure the account while keeping it available for real emergencies, and close the incident.

The session included more than direct actions by the break-glass account. The intruder used the account to create a rogue service account. That service account created a second rogue service account. All three identities made changes. They assigned unauthorized admin roles, added identities to privileged groups, granted application access, added login factors, suspended an employee, and removed two legitimate admins from their group.

The same log window also contains legitimate overnight work by real staff. Those changes must not be modified.

There is no list of the damage. The only way to identify it is to read the identity system's event log, filter events by actor, and follow the chain of actors.

## What we expect the agent to do

1. Read the incident and reconstruct the session from the identity log. Filter events by actor. Identify the accounts created during the session and review their actions too.
2. Reverse every unauthorized change. Remove the granted admin roles, group memberships, and application assignments. Delete the added login factors. Shut down the two rogue service accounts.
3. Reverse the sabotage too. Restore the suspended employee and add the removed admins back to their group. Restoring the session's changes requires undoing both additions and removals.
4. Do not change the legitimate actions that occurred during the same period.
5. Secure the break-glass account. Revoke its sessions and change its password because the intruder is known to have that credential. Keep the account active so it remains available for emergencies.
6. Close the incident correctly.

## What agents often miss

Agents usually investigate the incident well. They reliably reconstruct the full chain, including the rogue account that created another rogue account. They separate the attack from legitimate overnight work and reverse the full unauthorized set of changes. Nearly every check passes in nearly every run.

The final two steps usually determine whether a run passes or fails. The most common mistake is declaring the break-glass account secure after revoking its sessions without changing its password. The password is the exact secret the intruder used. Some runs included the account-update operation in their search results but still did not use it.

The other common near miss is administrative. The incident receives closure notes and a close code, but its state field is not set. As a result, the ticket still counts as open.

In short, the main failures happen during the final housekeeping steps. Change the leaked credential and set the incident state so the incident is actually closed.
