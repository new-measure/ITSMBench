# task-c4

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 9/16 | FAIL ❌ |

## Task

The security team posted a SEV-1 in the `#it-helpdesk` Slack channel: an OAuth
consent-phishing campaign hit the acme.com Okta org. Fake "review shared document"
prompts from a lookalike domain tricked several staff — including a Super Admin —
into granting rogue sign-in apps broad Okta scopes (`okta.users.manage`,
`okta.apps.manage`), and an org API token was created from the admin's session. Two
rogue apps were named. GPT had to trace the rest from the Okta system log and remove
every rogue app plus the attacker's API token.

## Ideal Solution

Filter the Okta system log for the consent-grant events from the attacker's source
IP to list all eleven rogue apps, then deactivate or delete the eight still active
and revoke the attacker-created API token. Then read the disabled apps the other
way: an over-broad automated containment had wrongly turned off seven real business
sign-in apps (Zendesk, Datadog, Figma, and others) that carry no attacker consent
event. Re-activate those seven, while leaving the genuinely rogue disabled apps off.
Restoring the wrongly-disabled apps is the step most responders skip.

## How GPT-5.6 Performed

FAIL. GPT filtered the Okta system log by the attacker's source IP, listed all
eleven rogue apps, deactivated the eight still active, and revoked the attacker's API
token — the full clean-up the campaign called for. But it treated the job as tearing
out the attack and nothing else. It never listed the disabled apps to check what the
automated containment had wrongly caught, so it re-activated none of the seven
legitimate business sign-in apps that were left offline.
