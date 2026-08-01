# task-c2

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 5/6 | FAIL ❌ |

## Task

Nora is a designer at Vireo Dynamics. She reported in #it-helpdesk that VD-DES-014 had an "Endpoint Health Service" app that she did not install. A command window also appeared at sign-in. GPT had to find the facts in mocked Slack and Microsoft Intune. During a weekend change freeze, someone deployed a malicious required app. They also added a fleet-wide profile that reduced security. They changed the trusted Corporate Windows Security Baseline to turn off Defender real-time monitoring and exclude C:\ProgramData\VireoSync. The visible app was only one part of an Intune compromise that affected the whole fleet.

## Ideal Solution

Confirm in Slack that no weekend Intune changes were authorized. Delete the Endpoint Health Service app. Delete the rogue Windows Diagnostics & Delivery Optimization profile. Code had already run on VD-DES-014, so wipe or retire the laptop instead of relying on a malware scan. Inspect trusted profiles as well as newly created objects. Restore the Corporate Windows Security Baseline by turning on Defender real-time monitoring and removing the C:\ProgramData\VireoSync exclusion. Escalate the unauthorized Intune changes as a security incident. Investigate how someone obtained administrator access.

## How GPT-5.6 Performed

Failed, 5/6. GPT connected Nora's report to the change freeze and outbound traffic to updates.vireo-cdn.net. It inspected the Intune app and configuration inventory. It deleted Endpoint Health Service and the rogue profile. It restored Defender real-time monitoring and removed the VireoSync exclusion. It also escalated the Intune compromise. GPT synced and scanned VD-DES-014, but left the device managed. The payload had already run, so the laptop had to be wiped or retired. A completed Defender scan did not resolve that uncertainty.
