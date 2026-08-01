# task-n-3 — Stores cannot take card payments (the blamed cause is not the cause)

## What this task is

A P1 incident reports that stores cannot complete card payments at the register. The incident blames one of two possible causes. The first is a security-agent update sent to the store machines on Friday. The second is an outage at the payment processor.

Neither is the cause. A security-hardening change was made to the company's web gateway during the same weekend. This change broke the entire connection path from the registers to the payment processor. Many small objects across the path are incorrect. Payments work only when every object is correct. The payment endpoint addresses also changed during an earlier migration. Some network configurations still use the old addresses.

The agent must use evidence to disprove the reported causes. The agent must identify the complete path used by card payments, repair every broken part, and close the incident.

## What we expect the agent to do

1. Read the incident. Then check both reported causes against real evidence. The store machines are healthy, and the processor endpoints are live. Use this data to rule out both causes.
2. Identify every dependency of a card payment. The payment app does not use only one connection. It connects to five external endpoints: authorization, tokenization, settlement, a certificate checking service, and a fraud step-up partner. All five connections must work.
3. Use healthy services in the same environment as the reference. Their gateway rules show the correct configuration. The rules allow traffic from the store register group, use HTTPS, and point to each service's own destination list. The payment rules no longer match this configuration. Some rules are disabled. Some allow the wrong source. Some no longer specify the service.
4. Look up every payment endpoint in the asset inventory to find its current address. Then update the gateway destination lists and the DNS records so they match the current addresses.
5. Remove the payment addresses from the over-broad block list. Do not delete the block list because it still blocks a destination that must remain restricted.
6. Remove the old configuration left by the migration. This includes a rule and a DNS record that still point to retired addresses.
7. Close the incident.

## What agents often miss

Agents usually make the correct judgment about the reported causes. Every run uses evidence to reject both the security-agent update and the vendor-outage theory. Every run also identifies the gateway change. Most runs correctly repair the five gateway rules. They copy the structure of the healthy nearby rules instead of allowing traffic too broadly.

Agents consistently miss the addresses. No run checks the asset inventory for the payment endpoints. As a result, no run discovers that the endpoint addresses changed. Instead, agents compare DNS records with the gateway destination lists. They see that both contain the same addresses and report that the addresses are correct. However, both configurations contain the same outdated addresses. Comparing them does not verify that the addresses are current.

Agents also see a second clue but do not use it. The block list contains five addresses that do not appear anywhere else in the policy. These are the current payment endpoint addresses. Agents read the list, do not explain why the addresses are present, and do not change it.

The weakest runs stop even sooner. They repair only the rule for authorization, report that they have explained the outage, and close the ticket. The rest of the payment path remains broken.
