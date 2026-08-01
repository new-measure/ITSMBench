# task-c3

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 7/14 | FAIL ❌ |

## Task

The security team opened Sentinel incident #4712. An attacker called the IT service desk. The attacker convinced the service desk to reset the passwords and MFA for several Okta accounts. The attacker then enrolled their own Okta Verify factors from a foreign address and began signing in.

The incident included a list of 11 confirmed compromised accounts. The same list was also posted in Slack. It included senior admin Devin Marsh and on-leave admin Owen Pierce.

During the night, an automated rule suspended every account that connected through the corporate VPN. This affected more accounts than the real attack. GPT had to disable access for every confirmed compromised account. It also had to restore access for every account that the automated rule suspended by mistake.

## Ideal Solution

Read the confirmed compromised account list from the Sentinel incident and Slack. Seven confirmed accounts were still active. Suspend or deprovision all seven accounts to disable their access. These accounts are Devin Marsh, Owen Pierce, and five accounts missed by the overnight rule.

Then find every account that the rule left suspended. Compare each suspended account with the confirmed compromised list and the Okta sign-in log. Seven suspended accounts are clean. They include a marketing manager, a financial controller, a VP, and other users. They were suspended only because they used the corporate VPN. Set all seven accounts back to active. If they remain suspended, clean and business-critical users remain locked out during the response.

## How GPT-5.6 Performed

Failed, 7/14. GPT read the Sentinel incident and the Slack brief. It found the 11 confirmed compromised accounts. It suspended the seven accounts that were still active. It also revoked their sessions and cleared their factors. This fully contained every named account.

GPT did not investigate beyond the provided list. It did not query Okta to find other suspended accounts. As a result, it did not find the seven clean accounts that the overnight VPN rule suspended by mistake. It left all seven accounts suspended. It then reported that containment was complete.
