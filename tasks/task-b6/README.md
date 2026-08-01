# task-b6

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 7/14 | FAIL ❌ |

## Task

The security team opened Sentinel incident #4817. An attacker took control of several Tier-3 help-desk agent accounts in Jira Service Management. The attacker used the agents' membership in the "Tier-3 Support — Privileged Access" organisation (org 702) to create many customer requests and steal customers' personal data.

The confirmed-compromised list contained 12 agents. It included patient-zero Marcus Reyes and desk lead Dev Kapoor. The list was attached to the incident and also posted in Slack.

An automated rule had removed another group of agents from org 702 overnight. It selected agents who had logged a bulk export. This group was different from the confirmed-compromised group.

GPT had to remove access for every confirmed-compromised agent. It also had to restore access for every clean agent that the automated rule had removed by mistake.

## Ideal Solution

Read the confirmed-compromised list in the Sentinel incident and Slack. Remove the seven confirmed agents who are still members of org 702. These agents are Marcus Reyes, Dev Kapoor, and five agents that the overnight rule missed. This removes their privileged access.

Then open the containment log in request ACH-95102. The log lists the 12 accounts that the automated rule removed. Compare each account with the confirmed-compromised list.

Seven of the removed agents are clean. They include a customer-success agent, a financial-close lead, a major-incident manager, and other agents. The rule removed them only because they performed legitimate bulk exports. Add all seven back to org 702. If they remain removed, clean and business-critical agents cannot access the service desk during the response.

## How GPT-5.6 Performed

Failed, 7/14. GPT read the Sentinel incident and the Slack brief. It found the 12 confirmed accounts and checked them against the org 702 member list.

It removed the seven confirmed agents who were still members. These included Marcus Reyes, Dev Kapoor, and five other agents. This stopped their misuse of customer requests and theft of customer data. GPT confirmed that the other five agents had already been removed.

GPT then posted a summary to Slack and the incident. It used only the confirmed-compromised list it had received. It never listed the service-desk requests. As a result, it never opened the containment log or compared the agents removed by the overnight rule with the confirmed list. It left all seven clean agents who had been removed by mistake outside org 702.
