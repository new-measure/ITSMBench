# task-c1

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 9/17 | FAIL ❌ |

## Task
Security reported an active business email compromise. An attacker used a rogue Okta OAuth app called "Mailbox Sync & Backup" and stolen sessions to control several Acme mailboxes. The attacker sent fake emails saying "our bank details changed." The attacker also leaked email through forwarding filters and a mailbox delegate. Earlier that morning, Okta's impossible-travel workflow had automatically suspended a group of accounts. GPT had to use the evidence in Okta and Gmail to contain the attack. It was told only to remove the attacker's access. It was not told which accounts were involved.

## Ideal Solution
Two actions are required. First, contain the attacker. Use the Okta sign-in log, the OAuth app's user list, and the mailboxes to identify the five hijacked accounts that are still active. Suspend those accounts. Revoke the rogue API token. Deactivate the rogue app. Remove the delegate and forwarding filter from Tendai Tembo's mailbox.

Second, list every suspended user. Re-enable the eight clean accounts that the impossible-travel rule suspended by mistake. These accounts belong to the CEO, several VPs, and senior engineers. They have no attacker sign-in, no rogue grant, and no forwarding. They only have a normal login from Acme's own overseas VPN.

## How GPT-5.6 Performed
GPT contained the attack correctly. It connected sign-ins from the Romanian M247 proxy to the rogue OAuth app and the fraudulent sent email. It then suspended the five hijacked accounts that were still active, revoked the rogue API token, deactivated the OAuth app, and deleted the exfiltration filters and the delegate from Tendai Tembo's mailbox. It also correctly kept the five compromised accounts suspended.

However, GPT only examined the ten accounts that it connected to the attack. It never listed all suspended users. As a result, it did not identify or re-enable the eight clean CEO, VP, and engineer accounts that the automatic suspension had locked out by mistake.
