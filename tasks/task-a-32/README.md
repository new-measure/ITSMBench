# task-a-32 — Identity Administrators access audit

## What this task is

A routine ticket asks the IT support agent to audit the members of the Identity Administrators group. The agent must remove any admin access that is not properly authorized. There is no policy, runbook, or list of names that defines which access is legitimate. The agent must determine this from the environment.

The issue involves a chain of access grants. An employee left the company, but an offboarding failure left the employee’s account active. That account gave admin access to one person. That person gave access to others. Those people gave access to more people. The chain is four levels deep. The identity log contains every grant. A small register lists the admins who were set up legitimately at the start. Tracing the grant chain for any member ends at either the legitimate root or the terminated account.

While the illegitimate accounts had admin access, they created other resources. They created two service accounts, an app, and a privileged group with many members. None of these resources was approved anywhere. A closed incident from several months ago shows how a similar cleanup was handled.

## What we expect the agent to do

1. Do not accept the group list as proof that each member is authorized. Trace each member’s grant through the log until the chain reaches the legitimate root or the terminated account.
2. Remove admin access from every person whose chain leads to the terminated account, including people at all four levels. Keep every member whose chain is legitimate.
3. Identify that the terminated employee’s account is still active in the identity system and disable it.
4. Check what else the illegitimate accounts did with their access. Find the two service accounts, the app, and the group they created. Disable or remove each of them. Do not change the ordinary user accounts that were added to the group.
5. Record the decisions and close the ticket.

## What agents often miss

Agents usually find and remove the illegitimate admins correctly. They read the grant log, build the grant chain, remove all four levels of illegitimate access, and keep the legitimate members.

Runs often fail to complete the work beyond the membership list. Agents leave the terminated employee’s account active. Because the audit focuses on the group, they may not notice the account that caused the problem. Almost no run checks what the illegitimate accounts created while they had admin access. As a result, the rogue service accounts remain active, the app remains enabled, and the group with many members keeps its access. This happens because the cleanup ends after removing the illegitimate members instead of reversing the actions those accounts performed.

Removing access is only the first part of the work. A complete run must also remove or disable the resources created by the accounts whose access was revoked.
