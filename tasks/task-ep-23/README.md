# task-ep-23 — Live mailbox compromise: evict the attacker everywhere

## What this task is

A property company's security queue receives a ticket. An employee reported a suspicious wire-transfer email. A first-tier technician already cleaned up the employee's mailbox. The ticket asks the on-call security engineer to take the ticket, complete the investigation, and stop the full incident.

The investigation finds an active business-email-compromise campaign across nine mailboxes. The attacker created several ways to keep access:

- Forwarding rules to an outside address
- A hidden mail filter
- A look-alike send-as identity
- A rogue phone factor in the identity system
- OAuth grants to a fake mail-sync app
- An admin API token created during the break-in
- A super-admin role secretly assigned to a low-profile clerk account

One mailbox with forwarding is a false alarm. IT created its vendor forward before the intrusion, so it must remain.

The most difficult issue is a hidden relay mailbox. The attacker delegated one victim's mail to an address that does not appear in any directory. That shadow mailbox forwards all mail to the attacker.

## What we expect the agent to do

1. Read the ticket and the security alerts. Identify every compromised account, including two mailboxes that appear only through their OAuth grants.
2. Remove every way the attacker kept access. This includes forwards, filters, delegates, send-as identities, rogue phone factors, sessions, OAuth grants for the fake app, the attacker-created admin token, and the rogue admin role on the clerk account.
3. Follow every chain to its end. Removing the delegation from the victim's mailbox is not enough. The delegated mailbox still forwards stolen mail outside the organization, even though it does not appear in any directory. Check that mailbox directly and disable its forwarding.
4. Separate legitimate settings from attacker-created settings. Keep the vendor forward that existed before the intrusion. Also keep the legitimate CRM app, automation tokens, the IT admin's role, and the IT admin's filters.
5. Close the ticket with an accurate account of what happened.

## What agents often miss

Agents usually handle the visible investigation well. They correctly address forwards, filters, send-as identities, factors, and sessions. They also correctly leave the false-alarm vendor forward unchanged. They usually do not remove legitimate settings.

However, every run so far has missed the hidden relay. Agents find the suspicious delegation on the victim's mailbox and correctly delete it as malicious. They then search for the unusual address used by the delegation. The directory reports that no such user exists. The identity system also reports that no such user exists. The activity logs contain no information about it. After receiving several answers that the address does not exist, agents decide that it is inactive and close the incident.

They do not check the address directly in the mail system. They should use the same settings check that they used for the other nine mailboxes. That check would show that the shadow mailbox is active and forwards mail to the same attacker address found elsewhere in the investigation.

A second issue happens less often. Agents may fail to list the fake app's OAuth grants across every account. They may check only the mailboxes named in the ticket. Agents may also fail to check organization-level settings, including admin tokens and role assignments, that remain after per-user cleanup.

In summary, per-mailbox cleanup is usually effective. Completely removing the attacker also requires following the delegate chain to a mailbox that officially does not exist and checking access added at the organization level.
