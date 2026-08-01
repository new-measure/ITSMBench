# task-b10

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 7/14 | FAIL ❌ |

## Task

The security team opened Sentinel incident #4718. A threat actor stole integration tokens, including OAuth tokens and API keys, from several of Acme's SaaS vendors. The threat actor is using those tokens to extract Acme data through the vendors' Vanta-monitored connections.

The incident names 11 confirmed compromised vendors. The same list was posted again in Slack. Each vendor has a Vanta finding. The list includes the active patient-zero vendor Meridian Analytics and the payment processor Coastline Payments.

An overnight rule had already archived a group of vendors based on egress volume. This rule included more vendors than the confirmed list and was not fully accurate. GPT had to cut off every compromised vendor. It also had to restore every clean vendor that the rule had incorrectly offboarded.

## Ideal Solution

Read the confirmed compromised vendor list from the Sentinel incident and Slack. Archive the seven confirmed vendors that are still active. These include Meridian Analytics, Coastline Payments, and five vendors that the volume rule missed because they extracted data slowly.

Archiving these vendors marks them as offboarded in the vendor register. This causes downstream deprovisioning automation to revoke their integration access.

Then review every archived vendor against the confirmed list and its Vanta findings. Seven archived vendors are clean. They include a payroll processor, a legal e-discovery vendor, a benefits administrator, a backup provider, and other vendors. They were archived only because a legitimate bulk sync triggered the volume rule. Set these seven vendors back to MANAGED. If they remain archived, business-critical vendors will stay cut off during the response.

## How GPT-5.6 Performed

Failed, 7/14. GPT read the Sentinel incident and the Slack brief. It identified the 11 confirmed vendors and checked each vendor's Vanta finding. It set all 11 vendors to ARCHIVED. This cut off every compromised vendor, including the two active vendors.

GPT then confirmed that all 11 vendors were archived and reported that containment was complete. However, it only listed inventory records filtered to those 11 vendor names. It did not review the other archived vendors.

As a result, GPT did not find the seven clean, business-critical vendors that the overnight volume rule had incorrectly offboarded. It left all seven vendors archived.
