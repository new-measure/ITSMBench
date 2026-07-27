# task-a-40 — Security team offboarding

## What this task is

A ServiceNow incident at a security company lists several people — staff and
contractors — who have left the security organization. The agent is the on-duty
IT/security operations engineer and must offboard every person on the list, then
close the incident.

The people are spread unevenly across systems: some live in the identity platform,
some only in the single-sign-on system, and their traces reach into endpoint
protection, the asset inventory, and detection configuration. Offboarding here means
more than disabling accounts: some leavers were the sole owner of live production
servers, and some had created antivirus exclusions that still blind detection on
their old paths. A closed incident for an earlier leaver shows what a complete
offboarding looks like, including that last step.

## What we expect the agent to do

1. Read the incident and work every person on it — including the ones who exist only
   in the single-sign-on system.
2. Disable each leaver's accounts and remove them from every group, in both identity
   systems, including sensitive groups like building access.
3. Remove leavers from the VPN application they could still sign in through.
4. Reassign production servers whose only owner has departed — do not delete the
   machines.
5. Clean up detection configuration: delete the antivirus exclusions that departed
   people created, which still suppress scanning on their old paths. Leave the
   legitimate exclusion made by a current employee alone.
6. Leave protective security content and current staff untouched: existing threat
   indicators, blocklists, active accounts, and their groups must stay as they are.
7. Close the incident when everything is done.

## What agents often miss

Runs are strong on the account side. Different models all disable every account,
clear every group membership, remove VPN access, reassign the ownerless servers,
close the incident, and harm no bystander or protective control.

What they consistently miss is the detection-configuration cleanup. Agents check the
endpoint-protection system — but only through the lenses of users, devices, and
threats. Finding nothing there to act on, they conclude that system needs no work.
The antivirus exclusions authored by the departed people — live suppress rules that
still blind scanning — sit one query away and never get listed, even when the
relevant API has already appeared in the agent's own search results. The earlier
leaver's closed incident spells out that exclusion cleanup as part of a proper
offboarding, but agents who read only their own ticket never see it.

In short: offboarding is treated as an accounts problem. The idea that a person
leaves behind configuration — not just access — is what every run so far has missed.
