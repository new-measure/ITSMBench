# task-b10

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 7/14 | FAIL ❌ |

## Task

The security team opened a Sentinel incident (#4718): a threat actor stole the integration tokens (OAuth / API keys) of several of Acme's SaaS vendors and is using them to pull Acme data out through the vendors' Vanta-monitored connections. The confirmed-compromised list — 11 vendors, led by the live patient-zero Meridian Analytics and the payment processor Coastline Payments — is named on the incident, reposted in Slack, and carries a per-vendor Vanta finding. An overnight rule had already archived a batch of vendors by egress volume, a wider and imperfect net. GPT had to cut off every compromised vendor and restore any clean one the rule had wrongly offboarded.

## Ideal Solution

Read the confirmed-compromised list from the Sentinel incident and Slack. Archive the seven confirmed vendors still active — Meridian Analytics, Coastline Payments, and five the volume rule missed because they exfiltrated slowly — which marks them offboarded in the vendor register so downstream deprovisioning automation revokes their integration access. Then audit every vendor left archived against that list and its Vanta findings. Seven of them (a payroll processor, a legal e-discovery vendor, a benefits administrator, a backup provider, and others) are clean, archived only because a legitimate bulk sync tripped the volume rule, and must be set back to MANAGED. Leaving them archived keeps business-critical vendors cut off during the response.

## How GPT-5.6 Performed

Failed, 7/14. GPT read the Sentinel incident and the Slack brief, pulled the eleven confirmed vendors, checked each one's Vanta finding, and set all eleven to ARCHIVED — cleanly cutting off every compromised vendor, including the two live ones. It then confirmed 11 of 11 were archived and reported containment complete. It only ever listed the inventory filtered to those eleven names, so it never looked at the other archived vendors. It never found the seven clean, business-critical vendors the overnight volume rule had wrongly offboarded, and left every one of them archived.
