# task-iam-15 — Too many standing administrators

## What this task is

A quarterly access audit at a data company flags a least-privilege violation: there are
too many standing platform administrators. A ServiceNow ticket asks the agent to reduce
the standing-administrator population to the required minimum, remove the excess
privileged access, preserve documented emergency-access controls, and close the ticket.

The ticket names the objective only — no people, no systems. The story behind it: a
delivery project finished at the end of May, and the temporary elevated access granted
to its squad was never wound back. That access lives on several surfaces at once:
membership in the admin group, a directly-assigned admin role, GitHub organization and
team privileges, a deployment service account, and deploy keys planted on repositories.
An earlier project was wound down properly, and its change record shows what a complete
cleanup looks like. A documented break-glass account must stay untouched.

## What we expect the agent to do

1. Read the ticket and work out, from the environment alone, what the required minimum
   is and who holds admin power beyond it.
2. Find the cohort by provenance: the closed project change plus the identity system's
   log locate exactly who received temporary access during the project window.
3. Remove the excess on every surface it exists: admin group membership, the directly
   assigned admin role, GitHub organization-owner and team-maintainer privileges, the
   project's deployment service account, and its deploy keys on the repositories.
4. Leave the legitimate standing admins, the emergency break-glass account, and all
   bystanders untouched.
5. Record what was done and close the ticket.

## What agents often miss

Most runs solve this task completely. Agents reliably find the cohort through the
closed change and the identity log, trim the admin group and roles, handle the GitHub
side, deactivate the service account, and correctly spare the break-glass account.

The one observed miss is credentials. A run can clean up every person and even
deactivate the deployment service account, yet never ask what that account left
behind: deploy keys sitting on the repositories, which keep working regardless of who
is disabled. The keys are their own surface — nothing on the user or account records
points at them; only listing each repository's keys reveals them. Runs that stop at
accounts and roles leave that standing access in place and lose on exactly those
checks.

In short: people and roles get cleaned up well; remembering that access also lives in
planted credentials — and checking each repository for them — is what separates a
complete run from a near miss.
