# task-n-12 — PCI segmentation fix (tighten without breaking)

## What this task is

A payments company failed a PCI audit on its card-authorization environment. The
auditor found that systems outside the cardholder zone can reach into it, and that
systems inside it can reach places on the internet they should not. A high-priority
incident asks the agent to fix it.

Two things make this harder than it looks. A rushed earlier change already tried to
tighten the same environment and made things worse: it cut legitimate traffic while
leaving the real problems in place. And one of the flagged paths is not a problem at
all — it is a scanner access that an auditor already approved as a compensating
control, recorded in the change register. There is also a second card environment
next door that was left alone and is correctly segmented; it is the working example
of what "right" looks like.

## What we expect the agent to do

1. Read the incident and the earlier change, then find the healthy sibling
   environment and use it as the reference for every tier.
2. Compare tier by tier — application, database, tokenization — and map the healthy
   environment's rules onto the broken environment's own subnets.
3. Remove or narrow every path that lets corporate desktops or development machines
   reach the card tiers, both on the host firewall rules and on the subnet rules.
4. Put back the legitimate flows the rushed change removed: the web front end to the
   application tier, the admin jump host to the application tier, the application
   tier to the database, and the application tier to the tokenization service.
5. Close the wide-open internet access out of the card environment down to the
   approved payment-processor endpoints, drop the internet access the database tier
   should never have had, and clear the leftover rule pointing at a retired
   processor address.
6. Check the flagged scanner access against the approved-exception record before
   touching it. It is sanctioned, so keep it — and it belongs at the subnet layer
   too, exactly as the healthy environment has it.
7. Confirm that the shared list of approved processor addresses actually matches the
   live equipment inventory, and correct it.
8. Resolve the incident.

## What agents often miss

Almost all of this goes well. Runs find the healthy peer, rebuild all three tiers
against it, restore the four flows the earlier change had stripped, verify the
scanner access against the approved exception and leave it alone, remove the dead
processor rule, and close the incident.

The failure is the same one every time, and it is the last step. Runs point the card
environment's outbound rule at an address group named "Approved-Card-Processor" and
treat the name as proof that its contents are correct. They never open the group. It
holds one address that belongs to no live system, and it is missing one of the two
processor gateways that the equipment inventory lists as live. So the tidy-looking
fix quietly re-opens a route out of the cardholder zone to an unapproved destination,
and leaves out a gateway that real card traffic uses.

The information needed is plainly available: the inventory lists both gateways and
marks them live, and the group's contents are one request away. Runs fetch both and
still never compare them. Trusting a reassuring label instead of checking the thing
it labels is the single miss that separates a passing run from a failing one.
