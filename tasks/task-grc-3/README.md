# task-grc-3 — SOC 2 access cleanup after a messy quarter-close

## What this task is

An IAM/GRC engineer at Acme Cloud is three days away from SOC 2 Type II fieldwork. The CISO has created a ticket. The engineer must correct the company’s access state before the auditor arrives. The access that an auditor finds in the live systems must match the access that is actually authorized.

Several normal problems caused the current state. There is no single broken control. The Q3 access review was rushed. Some decisions were abandoned. Some decisions were never enforced. The HR→Okta sync broke weeks ago, so Okta data is out of date compared with HR. An overnight bulk-deprovisioning job crashed before it finished and left some users in partial states. A compliance monitor reports problems, but it checks only a sample. It is not a complete list of required fixes.

There is no complete and authoritative list of users or items that require fixes. Real issues appear next to similar cases that must not be changed. These cases exist across identity status, app access, admin roles, and entitlement policy. Each item must be checked against the record that controls it. These records include HR, exceptions, the deprovision job log, review items, and recorded decisions. Do not apply one rule to every item.

## What we expect the agent to do

1. Read the CISO ticket. Use the compliance monitor only as a signal. Do not treat it as the complete work list.
2. Compare workers who are truly terminated in HR with their live Okta accounts. Exclude workers covered by an approved exception. Deactivate terminated workers whose Okta accounts are still active.
3. Remove residue from the crashed job. Some terminated users are DEPROVISIONED but remain in privileged groups, so they still have effective access.
4. Enforce access-review decisions that were never applied in Okta. This includes recorded Deny decisions that were not applied. It also includes abandoned reviews where the review tool has a blank decision but ServiceNow records Revoke.
5. Remove admin roles that reviews denied or identified as over-broad. Do not change approved roles, promoted roles, or break-glass exceptions.
6. Restrict entitlement policies that reviews voted to restrict. These policies must no longer be open to every directory member.
7. Do not change similar cases that do not require fixes. These include rescinded terminations, completed deprovisions, Approve decisions, legitimate broad policies, same-name collisions, and out-of-scope users.
8. Close the ticket with an accurate record of what was found and fixed.

## What agents often miss

Agents that investigate carefully usually fix most terminated-worker issues and Deny decisions. The task still fails if they handle exceptions incorrectly or treat one type of access as the entire cleanup.

A common mistake involves a rescinded termination. HR shows the worker as terminated, and the Okta account is still ACTIVE. This looks the same as a real access gap. However, an approved exception with type "rescind" means the termination was canceled, so the account must remain active. Do not interpret the exception as approval to remove access and deactivate the user. That is incorrect. The ticket says not to change access covered by an approved exception.

Another common mistake is stopping after fixing obvious Okta account statuses. Remaining app access from the failed job appears in a different system. Abandoned reviews with Revoke recorded only in ServiceNow also appear in a different system. Entitlement policies that remain `allMemberUsers` must be checked separately. Applying one termination rule to everyone changes protected exceptions incorrectly and fails to fix these other forms of access. To complete the task, compare each subject with the system of record that governs it. Do not fix every item only because it appears incorrect.
