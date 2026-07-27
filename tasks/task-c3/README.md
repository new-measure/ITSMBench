# task-c3

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 7/14 | FAIL ❌ |

## Task

The security team opened a Sentinel incident (#4712): an attacker phoned the IT service desk, got the passwords and MFA reset on several Okta accounts, enrolled their own Okta Verify factors from a foreign address, and started signing in. The confirmed-compromised list — 11 accounts, including senior admin Devin Marsh and on-leave admin Owen Pierce — was attached to the incident and reposted in Slack. Overnight, an automated rule had also suspended every account seen coming from the corporate VPN, a wider net than the real attack. GPT had to cut access on every genuinely compromised account and restore anyone the rule had wrongly locked out.

## Ideal Solution

Read the confirmed-compromised list from the Sentinel incident and Slack. Suspend or deprovision the seven confirmed accounts still active — Devin Marsh, Owen Pierce, and five the overnight rule missed — cutting their access. Then check every account the rule left suspended against that list and the Okta sign-in log. Seven of them (a marketing manager, a financial controller, a VP, and others) are clean, caught only for using the corporate VPN, and must be set back to active. Leaving them suspended keeps clean, business-critical people locked out during the response.

## How GPT-5.6 Performed

Failed, 7/14. GPT read the Sentinel incident and the Slack brief, pulled the eleven confirmed accounts, and suspended the seven still active, also revoking their sessions and clearing factors — clean containment of every named account. It never looked past that handed-to-it list. It did not query Okta for which other accounts were suspended, so it never found the seven clean accounts the overnight VPN rule had wrongly locked out, and it left every one of them suspended. It signed off reporting containment complete.
