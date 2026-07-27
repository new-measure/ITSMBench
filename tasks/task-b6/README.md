# task-b6

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 7/14 | FAIL ❌ |

## Task

The security team opened a Sentinel incident (#4817): an attacker took over a group of Tier-3 help-desk agent accounts in Jira Service Management and used their membership of the "Tier-3 Support — Privileged Access" organisation (org 702) to open customer requests in bulk and steal customer personal data. The confirmed-compromised list — 12 agents, including patient-zero Marcus Reyes and desk lead Dev Kapoor — was attached to the incident and reposted in Slack. Overnight, an automated rule had also pulled a batch of agents out of org 702 based on who logged a bulk export, a different set from the real attack. GPT had to cut every compromised agent's access and restore anyone the rule wrongly removed.

## Ideal Solution

Read the confirmed-compromised list from the Sentinel incident and Slack. Remove from org 702 the seven confirmed agents still in it — Marcus Reyes, Dev Kapoor, and five the overnight rule missed — cutting their privileged access. Then open the containment log (request ACH-95102), which lists the twelve accounts the rule auto-removed, and check each against the confirmed list. Seven of them (a customer-success agent, a financial-close lead, a major-incident manager, and others) are clean, removed only for running legitimate bulk exports, and must be added back to org 702. Leaving them out keeps clean, business-critical agents locked out of the service desk during the response.

## How GPT-5.6 Performed

Failed, 7/14. GPT read the Sentinel incident and the Slack brief, pulled the twelve confirmed accounts, and checked them against the org 702 roster. It removed the seven still in the organisation — Marcus Reyes, Dev Kapoor, and five more — stopping the request and data-theft abuse, and confirmed the other five were already gone. It then posted a summary to Slack and the incident. It worked only from the handed-to-it confirmed list. It never listed the service-desk requests, so it never opened the containment log or compared who the overnight rule had removed against that list. It left all seven wrongly-removed clean agents out of org 702.
