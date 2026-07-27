# task-b11

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 8/15 | FAIL ❌ |

## Task

An account-takeover was exfiltrating CRM data from Salesforce: a stolen OAuth token on the "Northbeam Revenue Sync" connected app was bulk-exporting Accounts, Opportunities, and Contacts to a foreign IP. GPT had to recover the confirmed-compromised account list from the mocked Microsoft Sentinel incident (#4839), the Slack #security-response-on-call channel, and a Salesforce case, then deactivate every still-active compromised Salesforce user and revoke the rogue connected app. An overnight Salesforce Shield auto-freeze had also disabled the wrong accounts, so GPT also had to restore the clean users it had wrongly locked out.

## Ideal Solution

Read the 11 confirmed-compromised accounts from Sentinel #4839 and Slack. Set `IsActive=false` on the seven that are still active (Priya Raman, Owen Pierce, and five others), and revoke the Northbeam Revenue Sync connected app. Then query the disabled users (`IsActive=false`): four are truly compromised and stay off, but seven clean, business-critical users were wrongly frozen by the auto-freeze and must be set back to `IsActive=true`. The decisive step is checking the disabled directory against the confirmed list, not only the confirmed list itself.

## How GPT-5.6 Performed

Failed, 8/15. GPT read Sentinel #4839 and the Slack channel, matched all 11 confirmed accounts to Salesforce users, deactivated the seven that were still active, and disabled the Northbeam Revenue Sync connected app — the whole lock-down side of the incident. It never queried the disabled-user directory, so it never found the seven clean users (among them a VP of Sales and a Financial Controller) that the Salesforce Shield auto-freeze had wrongly turned off. It left all seven disabled and reactivated none.
