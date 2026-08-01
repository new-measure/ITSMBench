# task-b11

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 8/15 | FAIL ❌ |

## Task

An account takeover was used to export CRM data from Salesforce. The attacker used a stolen OAuth token for the "Northbeam Revenue Sync" connected app. The attacker exported Accounts, Opportunities, and Contacts in bulk to a foreign IP.

GPT had to find the confirmed list of compromised accounts. The list was in the mocked Microsoft Sentinel incident #4839, the Slack #security-response-on-call channel, and a Salesforce case. GPT then had to deactivate every compromised Salesforce user who was still active and revoke the rogue connected app.

An overnight Salesforce Shield auto-freeze had also disabled the wrong accounts. GPT had to reactivate the clean users who had been incorrectly locked out.

## Ideal Solution

Read the 11 confirmed compromised accounts from Sentinel #4839 and Slack. Set `IsActive=false` for the seven accounts that are still active. These include Priya Raman, Owen Pierce, and five others. Revoke the Northbeam Revenue Sync connected app.

Then query the disabled users with `IsActive=false`. Four disabled users are confirmed as compromised and must remain disabled. Seven other disabled users are clean and business-critical. The auto-freeze disabled them incorrectly, so set `IsActive=true` for those seven users.

The key step is to compare the disabled user directory with the confirmed compromised account list. It is not enough to check only the confirmed list.

## How GPT-5.6 Performed

Failed, 8/15. GPT read Sentinel #4839 and the Slack channel. It matched all 11 confirmed accounts to Salesforce users. It deactivated the seven accounts that were still active and disabled the Northbeam Revenue Sync connected app. It completed all required incident lock-down actions.

GPT never queried the disabled user directory. As a result, it did not find the seven clean users whom the Salesforce Shield auto-freeze had incorrectly disabled. These users included a VP of Sales and a Financial Controller. GPT left all seven users disabled and did not reactivate any of them.
