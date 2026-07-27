# task-b9

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 7/14 | FAIL ❌ |

## Task

The security team opened a Microsoft Sentinel incident (#5093): an attacker breached the RelayOS hardware vendor's firmware distribution and pushed a trojaned build (8.4.1-br229), infected gear is beaconing to an attacker control host, and rogue assets were planted on the network. The confirmed-compromised list — 11 assets, including patient-zero core switch dc1-core-sw-01 and live perimeter firewall edge-fw-lon-01 — was attached to the incident and reposted in Slack. Overnight, an automated rule had also decommissioned every asset in patient zero's management subnet, a wider net than the real attack. In Device42, GPT had to take every genuinely compromised asset out of service and restore any the rule had wrongly pulled.

## Ideal Solution

Read the confirmed-compromised list from the Sentinel incident and Slack. Set `status` to `decommissioned` on the seven confirmed assets still in service — the two named core boxes plus five the subnet rule missed because they sit on other subnets. Then check every asset the rule decommissioned: seven (a finance database, a payroll server, a badge controller, a VoIP PBX, and others) never beaconed to the control host and are clean collateral, so set their `status` back to `in_service`. None of the seven is on the confirmed-compromised list, so absence from that list — not the subnet sweep — is what marks them safe to restore.

## How GPT-5.6 Performed

Failed, 7/14. GPT read the Sentinel incident entities and the Slack brief, pulled the eleven confirmed hosts, looked each up in Device42, and set the seven still in service to `decommissioned` — clean containment of every named asset, which it then re-read to confirm. It never looked past that handed-to-it list. It never listed the full inventory or checked which assets sat in `decommissioned`, so it never found the seven clean, business-critical assets the overnight subnet rule had wrongly pulled, and left every one of them out of service.
