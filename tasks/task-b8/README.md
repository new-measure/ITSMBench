# task-b8

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 16/16 | PASS ✅ |

## Task

Security reported an active card-skimming attack on the public storefront
checkout, opened as Microsoft Sentinel incident 47. Checkout runs behind HAProxy
across three pools (pool-storefront-web, -api, -cdn) with about 43 backend
servers. GPT was handed the load balancer and told to cut off the malicious
serving path so no more customer traffic reaches any backend that is part of the
attack. It had to find the compromised backends itself: three unauthorized ones
the attacker added, plus several existing nodes secretly serving the skimmer,
identifiable only from the incident's network-connection records.

## Ideal Solution

Read incident 47 to get the two collector addresses and the three named rogue
backends. Filter the incident's egress records to the connections sending
cardholder data to those collectors, then match the source addresses to the
HAProxy server list. Set every rogue or compromised backend still taking traffic
(admin_state=ready) to maint or drain, or remove it. Then return the seven healthy
nodes that a flapping auto health-guard had wrongly pulled out of rotation back to
admin_state=ready, since they are not part of the attack and checkout needs their
capacity.

## How GPT-5.6 Performed

Passed, 16/16. GPT read incident 47, pulled its network-connection records, and
built the list of addresses sending cardholder data to the two collectors. It
matched those to the HAProxy servers and set admin_state=maint on the three
unauthorized backends and six compromised internal nodes still serving. It then
read the incident comment and the drain_reason on the drained rows, saw a flapping
health-guard had wrongly pulled healthy nodes, and returned all seven clean drained
backends to ready. With the restore step now signposted in-world, and those
backends in the same rotation it already edited, GPT reliably does it; the task
scores about 1.0, outside [0,0.7] for gpt-5.6-sol. Fairness was chosen over the
difficulty band.
