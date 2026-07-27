# task-b1

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 4/9 | FAIL ❌ |

## Task

Ishaan on the systems team reported in Slack that Okta's Privileged Administrators group keeps changing on its own and that password and session resets do not make the fixes stick. GPT had to work out the real driver and put it right. Reading the Okta system log, the account records, and Workday shows the cause: a departed automation contractor left a service account (svc-scim-sync) whose Okta SSWS API token keeps re-granting admin access from an outside IP address.

## Ideal Solution

Revoke the access-sync API token, which is what keeps restoring access. An Okta token is separate from the account's password and sessions and outlives a suspend, so only revoking it (or deprovisioning its account) stops the churn. Deprovision the service account, not just suspend it. Finish the offboarding the same way for all three contractors on that team — Dmitri Sokolov, Marco Reyes, and Priya Nair — who Workday shows as terminated but Okta still lists as suspended. Remove the standing Super Administrator role the automation left on live employee Carmen Costa, delete the rogue Access Sync Connector app, and flag it to security.

## How GPT-5.6 Performed

Failed, 4/9. GPT correctly found that an Okta API token owned by svc-scim-sync was reapplying the changes, which is why password and session resets never stuck, and revoked that token along with a second one. It removed Dmitri Sokolov from Privileged Administrators, stripped Carmen Costa's unauthorized Super Administrator role, and posted a security escalation about the incident. But it only suspended the service account and Dmitri instead of deprovisioning them, so the token owner and the departed contractor still counted as active. It left the rogue Access Sync Connector app in place. It never opened Workday, so it never learned that Marco Reyes and Priya Nair were terminated on the same team and left both suspended.
