# task-b3

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 3/6 | FAIL ❌ |

## Task

Nadia Rahman from finance reported an issue in the #it-helpdesk Slack channel. CrowdStrike Falcon detected malware on her workstation, NADIA-RAHMAN-WKS, after she opened a fake vendor invoice. She asked IT to investigate and resolve the issue. GPT had to use the mocked systems to determine what happened and make the environment safe again. It had to handle the real threat. It also had to make the correct decisions about other Falcon detections and network-contained machines found during the investigation.

## Ideal Solution

Contain NADIA-RAHMAN-WKS. Block the command-and-control domain telemetry-sync-edge.net across the entire fleet. Create a Falcon custom indicator with type `domain` and action `prevent`, and apply it globally.

Then make three decisions. Close the "LSASS credential access" detection on security analyst Priya Menon's laptop as a false positive. Confluence CR-2026-0312 records that this was an approved assessment. Remove network containment from two clean finance servers: FIN-APP-SVR-01 and FIN-RPT-SVR-01. A malfunctioning auto-policy isolated them overnight and took finance offline. Suspend nadia.rahman in Okta because her stolen password was already used from a foreign address after the infection.

## How GPT-5.6 Performed

It passed 3 of 6 checks. It contained the reported workstation. It blocked the C2 domain across the entire fleet with a global `prevent` indicator. It also suspended nadia.rahman after finding the foreign Okta sign-in.

It missed the two decisions that required a different response from the obvious one. It left FIN-APP-SVR-01 and FIN-RPT-SVR-01 network-contained instead of releasing the servers that had been isolated by mistake. It also treated the LSASS detection on Priya Menon's laptop as part of the attack instead of closing it as a false positive from the approved assessment.
