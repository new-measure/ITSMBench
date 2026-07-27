# task-n-3 — Stores cannot take card payments (the blamed cause is not the cause)

## What this task is

A P1 incident says stores cannot complete card payments at the register. The
incident blames one of two things: a security-agent update that shipped to the
store machines on Friday, or an outage at the payment processor.

Neither is true. A security-hardening change on the company's web gateway ran the
same weekend and broke the whole path from the registers out to the payment
processor. The damage is spread across many small objects, and payments only work
if every one of them is right. The addresses of the payment endpoints also moved
in an earlier migration, and parts of the network still point at the old ones.

The agent has to disprove the reported cause, work out the full path a card
payment takes, repair every broken piece, and close the incident.

## What we expect the agent to do

1. Read the incident, then check the two blamed causes against real evidence.
   The store machines are healthy and the processor endpoints are live, so both
   suspicions can be ruled out with data rather than opinion.
2. Find out what a card payment actually depends on. The payment app is not a
   single connection — it reaches five outside endpoints: authorization,
   tokenization, settlement, a certificate checking service, and a fraud
   step-up partner. All five must work.
3. Use the healthy services in the same estate as the reference. Their gateway
   rules show the correct shape: allowed from the store register group, over
   HTTPS, to their own destination list. The payment rules have drifted from
   that — some are switched off, some allow the wrong source, some lost the
   service.
4. Look up each payment endpoint in the asset inventory to get its current
   address, then make the gateway's destination lists and the DNS records agree
   with it.
5. Take the payment addresses out of the over-broad block list, without deleting
   the list, since it still blocks a genuinely restricted destination.
6. Clean up what the migration left behind: a rule and a DNS record still
   pointing at retired addresses.
7. Close the incident.

## What agents often miss

The judgment part goes well. Every run rejects the blamed security-agent update
and the vendor-outage theory with evidence, and finds the gateway change. Most
runs also repair the five gateway rules properly, copying the shape of the
healthy neighbours instead of opening things up.

The consistent miss is the addresses. No run looks the payment endpoints up in
the asset inventory, so no run ever learns that the endpoints moved. Instead
runs compare DNS against the gateway's destination lists, find that the two
agree, and report the addresses as confirmed correct. They agree because both
are stale in the same way. Comparing two copies of the same mistake is the trap.

There is a second clue that is seen and not used: the block list contains five
addresses that appear nowhere else in the policy. Those are the live payment
endpoints. Runs read that list, do not explain it, and leave it alone.

The weakest runs stop even earlier: they fix the one rule that names
authorization, declare the outage explained, and close the ticket while the rest
of the payment path is still broken.
