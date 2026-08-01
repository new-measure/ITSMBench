# task-b8

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 16/16 | PASS ✅ |

## Task

Security reported an active card-skimming attack on the public storefront checkout. The attack was recorded as Microsoft Sentinel incident 47. Checkout runs behind HAProxy. It uses three pools: pool-storefront-web, pool-storefront-api, and pool-storefront-cdn. These pools contain about 43 backend servers.

GPT was given access to the load balancer. It had to stop customer traffic from reaching every backend involved in the attack. It had to identify the compromised backends itself. These included three unauthorized backends added by the attacker. They also included several existing nodes that were secretly serving the skimmer. These nodes could only be identified from the incident's network-connection records.

## Ideal Solution

Read incident 47 to find the two collector addresses and the names of the three rogue backends. Filter the incident's egress records for connections that sent cardholder data to those collectors. Match the source addresses from those connections to the HAProxy server list.

For every rogue or compromised backend that is still taking traffic with `admin_state=ready`, set it to `maint` or `drain`, or remove it. Then restore the seven healthy nodes that an unstable auto health-guard had incorrectly removed from rotation. Set their state back to `admin_state=ready`. These nodes are not part of the attack, and checkout needs their capacity.

## How GPT-5.6 Performed

Passed, 16/16. GPT read incident 47 and retrieved its network-connection records. It created a list of addresses that were sending cardholder data to the two collectors. It matched those addresses to the HAProxy servers. It set `admin_state=maint` on the three unauthorized backends and the six compromised internal nodes that were still serving traffic.

GPT then read the incident comment and the `drain_reason` on the drained rows. It found that an unstable health-guard had incorrectly removed healthy nodes from rotation. It returned all seven clean, drained backends to `ready`.

The restore step is now clearly indicated in the environment. The affected backends are also in the same rotation that GPT had already edited. As a result, GPT performs the restore reliably. The task scores about 1.0, which is outside the [0,0.7] range for gpt-5.6-sol. Fairness was chosen instead of keeping the task within the difficulty range.
