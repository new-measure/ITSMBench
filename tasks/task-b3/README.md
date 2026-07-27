# task-b3

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 3/6 | FAIL ❌ |

## Task

Nadia Rahman in finance reported in the #it-helpdesk Slack channel that CrowdStrike Falcon flagged malware on her workstation (NADIA-RAHMAN-WKS) after she opened a fake vendor invoice, and asked IT to look at it and close it out. GPT had to work out what actually happened from the mocked systems and bring the environment back to a safe state — handling the real threat while making the right call on other Falcon detections and network-contained machines it would run into along the way.

## Ideal Solution

Contain NADIA-RAHMAN-WKS and block the command-and-control domain telemetry-sync-edge.net fleet-wide as a Falcon custom indicator (type `domain`, action `prevent`, applied globally). Then three judgment calls. Close the "LSASS credential access" detection on security analyst Priya Menon's laptop as a false positive — an approved assessment recorded in Confluence CR-2026-0312. Lift network containment on two clean finance servers (FIN-APP-SVR-01, FIN-RPT-SVR-01) that a misfiring auto-policy isolated overnight, taking finance offline. Suspend nadia.rahman in Okta, since her stolen password was already used from a foreign address after the infection.

## How GPT-5.6 Performed

It passed 3 of 6 checks. It contained the reported workstation, blocked the C2 domain fleet-wide with a global `prevent` indicator, and suspended nadia.rahman after finding the foreign Okta sign-in. It missed the two counterintuitive calls: it left FIN-APP-SVR-01 and FIN-RPT-SVR-01 network-contained instead of releasing the wrongly isolated servers, and it treated the LSASS detection on Priya Menon's laptop as part of the attack rather than closing it as the approved-assessment false positive.
