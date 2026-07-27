# task-iam-19 — Break-glass account used overnight

## What this task is

A security incident at a payments company: the registered break-glass emergency
administrator account was signed in and used overnight, and there is no approved
authorization on file. The ticket asks the on-call engineer to reconstruct what the
account did, put the environment back the way it was, secure the account while keeping
it available for real emergencies, and close the incident.

The session was not just a list of direct actions. The intruder used the break-glass
account to create a rogue service account, which created a second one, and all three
identities made changes: unauthorized admin roles, privileged group additions,
application access, planted login factors, a suspended employee, and two legitimate
admins kicked out of their group. Legitimate overnight work by real staff is mixed into
the same log window and must be left alone. Nothing lists the damage anywhere — the
only way to know what happened is to read the identity system's event log and follow
the chain of actors.

## What we expect the agent to do

1. Read the incident and reconstruct the session from the identity log: filter events
   by actor, notice the accounts the session created, and follow their actions too.
2. Reverse every unauthorized change: remove the granted admin roles, group
   memberships, and application assignments; delete the planted login factors; shut
   down the two rogue service accounts.
3. Reverse the sabotage as well: restore the suspended employee and put the removed
   admins back in their group. Undoing a session means restoring what it took away,
   not only deleting what it added.
4. Leave the interleaved legitimate changes untouched.
5. Secure the break-glass account itself: revoke its sessions and change its password —
   the one credential the intruder is known to hold — while keeping the account active
   as an emergency control.
6. Close the incident properly.

## What agents often miss

The investigation is done well. Runs reliably reconstruct the full chain — including
the rogue account that created another rogue account — separate the attack from
legitimate overnight work, and reverse the whole footprint. Nearly every check passes
in nearly every run.

What splits passing from failing runs is finishing the last two steps precisely. The
most common miss: the break-glass account is declared "secured" after its sessions are
revoked, but its password — the exact secret the intruder just used — is never changed.
Runs have had the account-update operation sitting in their own search results and
still skipped it. The other near miss is administrative: the incident gets closure
notes and a close code, but the record's state field is never set, so the ticket still
counts as open.

In short: the forensic work is strong; the misses are the final housekeeping — rotate
the credential that leaked, and actually close what you say you closed.
