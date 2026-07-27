# task-b2

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 7/14 | FAIL ❌ |

## Task

Security opened a Microsoft Sentinel incident (#5207): a contractor using a burner account (Mallory Kade) widened access on the four most sensitive SharePoint sites — Executive, Finance, Security, and Board & Legal — and was pulling documents out. The confirmed list of grants the actor added is named on the incident and reposted in Slack `#security-response-on-call`. GPT had to read that scope, open each sensitive site's permissions in SharePoint, and cut off every grant the actor had added before more data left.

## Ideal Solution

For each of the four named sites, read its permissions and remove the grants the actor added — the All Staff and External Contractors groups and the Mallory Kade account — leaving the real admin group in place. Then, unprompted, list every SharePoint site, not just the four named, and read each one's permissions. An overnight emergency lockdown had suspended legitimate team access on six other sites — Engineering, Operations, Sales & Marketing, People & HR, IT Support, and All Company. Set each suspended team grant back to active, including All Staff on the All Company site, even though that same group was one of the rogue grants elsewhere.

## How GPT-5.6 Performed

Failed, 7/14. GPT read Sentinel #5207 and the Slack brief, opened the four named sites, and removed all seven grants the actor had added — cutting off the insider's access to Executive, Finance, Security, and Board & Legal, and leaving each site's real admin group. It rechecked those four sites, reported containment complete, and posted a summary to Slack. It stopped there. It only ever read the four sites named in the incident, so it never listed the rest of the SharePoint inventory. It never found the six other sites whose team access the overnight lockdown had wrongly suspended, and left every one of those teams locked out of its own site.
