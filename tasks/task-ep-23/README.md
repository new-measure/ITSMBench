# task-ep-23 — Live mailbox compromise: evict the attacker everywhere

## What this task is

A property company's security queue gets a ticket: an employee reported a suspicious
wire-transfer email, and a first-tier tech already cleaned up the reporter's mailbox.
The ticket asks the on-call security engineer to pick it up, work it to completion, and
shut down whatever it turns out to be.

It turns out to be a live business-email-compromise campaign across nine mailboxes.
The attacker left persistence of many kinds: forwarding rules to an outside address, a
hidden mail filter, a look-alike send-as identity, a rogue phone factor in the identity
system, OAuth grants to a fake mail-sync app, an admin API token minted during the
break-in, and a super-admin role quietly given to a low-profile clerk account. One
mailbox with forwarding is a false alarm: its vendor forward was set up by IT long
before the intrusion and must stay. The nastiest piece is a hidden relay mailbox: the
attacker delegated one victim's mail to an address that appears in no directory, and
that shadow mailbox forwards everything to the attacker.

## What we expect the agent to do

1. Read the ticket and the security alerts, and map the full set of compromised
   accounts — including two mailboxes that only show up through their OAuth grants.
2. Remove every piece of attacker persistence: forwards, filters, delegates, send-as
   identities, rogue phone factors, sessions, OAuth grants for the fake app, the
   attacker-minted admin token, and the clerk account's rogue admin role.
3. Follow chains to the end. Deleting the victim's delegation is not enough: the
   mailbox it pointed at is still forwarding stolen mail outside, even though it
   appears in no directory. Check it directly and shut its forwarding down.
4. Tell real from planted: the vendor forward that predates the intrusion stays; the
   legitimate CRM app, automation tokens, the IT admin's role and filters all stay.
5. Close the ticket with an honest account of what happened.

## What agents often miss

Runs handle the visible sweep well: forwards, filters, send-as, factors, sessions, and
the false-alarm vendor forward are almost always judged correctly, and nothing
legitimate gets broken.

What every run has missed so far is the hidden relay. Runs find the suspicious
delegation on the victim's mailbox and delete it — correctly calling it malicious —
then go looking for the strange address it pointed at. The directory says no such
user; the identity system says no such user; the activity logs are silent. After
several "does not exist" answers, runs conclude the address is inert and close the
incident. Nobody asks the mail system itself — the same settings check they just ran
on nine other mailboxes — which would have shown the shadow mailbox live and
forwarding to the exact attacker address they had been chasing all along.

A second, less common gap: enumerating the fake app's OAuth grants across every
account instead of only the mailboxes named in the ticket, and checking org-level
surfaces (admin tokens, role assignments) that survive per-user cleanup.

In short: per-mailbox cleanup is strong; following the delegate chain into a mailbox
that officially "does not exist" — and auditing org-level persistence — is what
separates a finished eviction from an almost-finished one.
