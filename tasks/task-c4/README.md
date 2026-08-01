# task-c4

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 9/16 | FAIL ❌ |

## Task

The security team reported a SEV-1 in the `#it-helpdesk` Slack channel. An OAuth consent-phishing campaign targeted the acme.com Okta org. Fake "review shared document" prompts came from a domain that looked similar to the real one. These prompts tricked several employees, including a Super Admin, into giving rogue sign-in apps broad Okta scopes. The scopes included `okta.users.manage` and `okta.apps.manage`. The attacker also created an org API token from the admin's session. The security team named two rogue apps. GPT had to use the Okta system log to find the remaining rogue apps. It then had to remove every rogue app and revoke the attacker's API token.

## Ideal Solution

First, filter the Okta system log for consent-grant events from the attacker's source IP. This identifies all eleven rogue apps. Then deactivate or delete the eight apps that are still active. Revoke the API token created by the attacker.

Next, review the disabled apps. An automated containment action had disabled seven legitimate business sign-in apps because its rules were too broad. These apps included Zendesk, Datadog, Figma, and others. They had no attacker consent events. Reactivate all seven legitimate apps. Keep the genuinely rogue disabled apps turned off. Responders often miss the step of restoring the incorrectly disabled apps.

## How GPT-5.6 Performed

FAIL. GPT filtered the Okta system log by the attacker's source IP and identified all eleven rogue apps. It deactivated the eight apps that were still active and revoked the attacker's API token. This completed the required cleanup of the attack.

However, GPT only removed the attacker's resources. It did not list the disabled apps to check whether the automated containment had incorrectly disabled legitimate apps. As a result, it did not reactivate any of the seven legitimate business sign-in apps that remained offline.
