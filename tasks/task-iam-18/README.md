# task-iam-18 — Guest access review (find the hidden reasons)

## What this task is

This task is a periodic review of guest access. External guest accounts build up over time in the corporate directory, the source-control organization, and the chat workspace. A ServiceNow request asks the agent to review all guest accounts, remove access that is no longer valid, and keep access for guests who are still active.

Some guests are clearly stale. The reason is visible in the directory. One guest is past its expiry date. Another guest was sponsored by an employee who has left.

Other guests look valid in the directory. Their accounts have not expired, and their sponsors are active. However, they are stale for reasons stored elsewhere. Two guests belong to a partner company that has been shut down. One guest has become a full employee, so the guest identity is now a duplicate. Every stale guest has access in all three systems.

## What we expect the agent to do

1. Review every guest, including guests who do not appear stale.
2. Use all available evidence to decide whether each guest is still valid. Do not rely only on the directory. Find and read the partner-company register and the guest-to-employee conversion record. These records are stored in separate tables.
3. For every stale guest, remove all access in every system. Disable directory sign-in, remove the guest from its security groups, remove its source-control grant, and deactivate its chat account.
4. Do not change the legitimate guests or the real employees. This includes the employee associated with the duplicate guest identity.
5. Close the review request after the guest access is correct.

## What agents often miss

Agents usually clean up guests whose stale status is visible in the directory. They remove the expired account and the account sponsored by an employee who left. They also remove those guests from all three systems.

Agents often miss guests whose stale status is not visible in the directory. Two guests are stale only because their partner company was decommissioned. One guest is stale only because the same person is now an employee. These accounts do not look invalid on their own. The facts that determine their status are stored in separate records. Agents often do not check what other data is available. They do not open the partner register or the conversion record. They leave these guests in place and report that the review is complete. As a result, they fix only the easy cases and incorrectly report that all guest accounts are correct.

There is also a smaller risk of doing too much. An agent might remove or disable a guest who is still legitimately active. This is a harmful mistake, not a valid cleanup action.

In short, agents reliably clean up guests who are clearly stale. A complete review also requires finding the separate records that show why an account that looks valid is actually stale. The agent must also avoid changing guests who should remain active.
