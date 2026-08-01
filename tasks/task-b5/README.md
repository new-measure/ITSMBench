# task-b5

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 9/17 | FAIL ❌ |

## Task

An adversary-in-the-middle phishing attack and an info-stealer affected the Northgate region overnight. The SOC posted a list of confirmed compromised accounts in the `#it-helpdesk` Slack channel. It also opened Microsoft Sentinel incident #4471.

GPT had to compare those accounts with enrolled devices in Microsoft Intune. Every device owned by a compromised account had to be moved to the Security-Hold device category. Conditional access blocks devices in this category from all corporate resources.

An overnight risk-based auto-quarantine had already isolated devices in the region. It selected devices based on who was connected to the Northgate network. As a result, it both missed devices that should have been isolated and isolated devices that should not have been isolated.

## Ideal Solution

Read the nine compromised accounts from Sentinel and Slack. List the managed devices in Intune. Match each device owner with the compromised account list.

Move every device owned by a compromised account from its normal category to Security-Hold.

Then review all devices in Security-Hold. Find the clean devices that the auto-quarantine moved there by mistake. These include three shared ward EHR kiosks with no owner, several regular staff laptops and phones, and a VP's laptop.

Move each clean device back to its correct category to restore its access. Move shared EHR kiosks to Clinical. Move an individually assigned phone to Mobile. Move laptops to Corporate. The device name, OS, and owner show each device's class. The category descriptions state which device class belongs in each category.

Do not change devices that are already in the correct category.

## How GPT-5.6 Performed

FAIL. GPT read the SOC brief and Sentinel incident #4471. It retrieved all nine compromised accounts. It listed all 114 enrolled devices and matched each account to its devices.

It correctly moved every compromised device that still had access into Security-Hold. This included Dana Okoro's laptop and phone. It also verified that it had not missed any compromised devices.

However, GPT only handled devices owned by the compromised accounts. It did not review the Security-Hold category to find devices that did not belong there. Therefore, it did not find the clean ward kiosks, staff devices, or VP laptops that the overnight auto-quarantine had blocked by mistake. It did not restore access for any of them.
