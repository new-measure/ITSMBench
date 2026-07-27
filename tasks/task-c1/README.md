# task-c1

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 9/17 | FAIL ❌ |

## Task
Security reports an active business email compromise. An attacker used a rogue
Okta OAuth app ("Mailbox Sync & Backup") and stolen sessions to run several
hijacked Acme mailboxes, sending fake "our bank details changed" emails and
leaking mail through forwarding filters and a mailbox delegate. Okta's
impossible-travel workflow had already auto-suspended a batch of accounts that
morning. GPT had to contain the attack from the evidence in Okta and Gmail: it
was told only to cut the attacker out, not which accounts were involved.

## Ideal Solution
Two things must happen. First, contain the attacker: from the Okta sign-in log,
the OAuth app's user list, and the mailboxes, find the five still-active hijacked
accounts, suspend them, revoke the rogue API token, deactivate
the rogue app, and remove the delegate and forwarding filter on Tendai Tembo's
mailbox. Second, list every suspended user and re-enable the eight clean
accounts (the CEO, several VPs, senior engineers) that the impossible-travel
rule wrongly caught. They have no attacker sign-in, no rogue grant, and no
forwarding — only a normal login from Acme's own overseas VPN.

## How GPT-5.6 Performed
GPT contained the attack cleanly. It matched sign-ins from the Romanian M247
proxy to the rogue OAuth app and the fraudulent sent mail, then suspended the
five still-active hijacked accounts, revoked the
rogue API token, deactivated the OAuth app, and deleted the exfil filters and
the delegate on Tendai Tembo's mailbox. It also correctly left the five genuinely
compromised accounts suspended. But it only ever examined the ten accounts it
tied to the attack. It never listed the full set of suspended users, so it did
not notice or re-enable the eight clean CEO, VP, and engineer accounts the
auto-suspension had locked out by mistake.
