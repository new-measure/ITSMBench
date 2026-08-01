# task-b1

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 4/9 | FAIL ❌ |

## Task

Ishaan from the systems team reported a problem in Slack. Okta's Privileged Administrators group kept changing without anyone making the changes. Password and session resets did not make the corrections permanent. GPT needed to identify the actual cause and fix it. The Okta system log, account records, and Workday showed the cause. A former automation contractor had left behind a service account named svc-scim-sync. Its Okta SSWS API token kept granting admin access again from an external IP address.

## Ideal Solution

Revoke the access-sync API token because it keeps restoring access. An Okta token is separate from the account's password and sessions. It remains valid after the account is suspended. Therefore, only revoking the token or deprovisioning its account will stop the repeated changes. Deprovision the service account instead of only suspending it. Complete the same offboarding process for all three contractors on that team: Dmitri Sokolov, Marco Reyes, and Priya Nair. Workday shows that they are terminated, but Okta still lists them as suspended. Remove the standing Super Administrator role that the automation assigned to the active employee Carmen Costa. Delete the unauthorized Access Sync Connector app. Report it to security.

## How GPT-5.6 Performed

Failed, 4/9. GPT correctly identified that an Okta API token owned by svc-scim-sync was applying the changes again. This explained why password and session resets did not make the corrections permanent. GPT revoked that token and a second token. It removed Dmitri Sokolov from Privileged Administrators. It removed Carmen Costa's unauthorized Super Administrator role. It also posted a security escalation about the incident. However, it only suspended the service account and Dmitri instead of deprovisioning them. As a result, the token owner and the former contractor still counted as active. It did not remove the unauthorized Access Sync Connector app. It never opened Workday, so it did not learn that Marco Reyes and Priya Nair were terminated members of the same team. It left both accounts suspended.
