# task-b5

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 9/17 | FAIL ❌ |

## Task

An adversary-in-the-middle phishing attack with an info-stealer hit the Northgate
region overnight. The SOC posted the confirmed-compromised account list in the
`#it-helpdesk` Slack channel and opened Microsoft Sentinel incident #4471. GPT had
to reconcile those accounts against enrolled devices in Microsoft Intune and make
sure every compromised device was moved into the Security-Hold device category,
which conditional access blocks from all corporate resources. An overnight
risk-based auto-quarantine had already isolated the region's devices, but it keyed
off who was on the Northgate network, so it was wrong in both directions.

## Ideal Solution

Read the nine compromised accounts from Sentinel and Slack, list the Intune managed
devices, and match each device's owner against that list. Move every compromised
account's device still sitting in a normal category into Security-Hold. Then look at
Security-Hold the other way: find the clean devices the auto-quarantine wrongly swept
in — three shared ward EHR kiosks with no owner, several ordinary staff laptops and
phones, and a VP's laptop — and move each back to its correct home category to restore
its access (shared EHR kiosks to Clinical, an individually-assigned phone to Mobile,
laptops to Corporate — each device's class is readable from its name/OS/owner and the
category descriptions state which class each category is for). Leave correctly placed
devices alone.

## How GPT-5.6 Performed

FAIL. GPT read the SOC brief and Sentinel #4471, pulled all nine compromised
accounts, listed the 114 enrolled devices, and matched each account to its devices.
It correctly moved every still-open compromised device, including Dana Okoro's laptop
and phone, into Security-Hold and checked that none was missed. But it treated the
job as containing the compromised accounts' devices only. It never examined the
Security-Hold category from the other side, so it never found the clean ward kiosks
and staff and VP laptops the overnight auto-quarantine had wrongly locked, and it
restored none of them.
