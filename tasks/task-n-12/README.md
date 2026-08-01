# task-n-12 — PCI segmentation fix (tighten without breaking)

## What this task is

A payments company failed a PCI audit of its card-authorization environment. The auditor found two problems. Systems outside the cardholder zone can reach systems inside it. Systems inside the cardholder zone can reach internet locations that they should not reach. A high-priority incident requires the agent to fix these problems.

An earlier rushed change tried to secure the same environment. It made the situation worse. It blocked legitimate traffic but did not fix the actual problems.

One flagged path is not a problem. It gives a scanner access that an auditor approved as a compensating control. This approval is recorded in the change register.

There is another card environment next to the affected environment. It was not changed and has correct segmentation. Use this healthy environment as the example of the correct configuration.

## What we expect the agent to do

1. Read the incident and the earlier change. Then find the healthy sibling environment. Use it as the reference for every tier.
2. Compare the application, database, and tokenization tiers. Map the healthy environment's rules to the broken environment's own subnets.
3. Remove or restrict every path that allows corporate desktops or development machines to reach the card tiers. Fix both the host firewall rules and the subnet rules.
4. Restore the legitimate flows that the rushed change removed:
   - The web front end to the application tier.
   - The admin jump host to the application tier.
   - The application tier to the database.
   - The application tier to the tokenization service.
5. Restrict the card environment's wide-open internet access to the approved payment-processor endpoints. Remove all internet access from the database tier because it should never have had that access. Remove the remaining rule that points to a retired processor address.
6. Check the flagged scanner access against the approved-exception record before changing it. The access is approved, so keep it. It must also exist at the subnet layer, exactly as it does in the healthy environment.
7. Confirm that the shared list of approved processor addresses matches the live equipment inventory. Correct the list if it does not match.
8. Resolve the incident.

## What agents often miss

Agents usually complete almost all of this work correctly. They find the healthy peer and rebuild all three tiers based on it. They restore the four flows removed by the earlier change. They verify the scanner access against the approved exception and keep it. They remove the retired processor rule. They also close the incident.

The same failure happens each time, during the last step. Agents point the card environment's outbound rule to an address group named "Approved-Card-Processor". They assume the name proves that the group's contents are correct. They do not inspect the group. The group contains one address that does not belong to any live system. It is also missing one of the two processor gateways that the equipment inventory identifies as live. As a result, the fix appears correct but allows traffic from the cardholder zone to an unapproved destination. It also blocks access to a gateway used by real card traffic.

All required information is available. The inventory lists both gateways and marks them as live. The group's contents are available with one request. Agents fetch both sources but do not compare them. They trust the group's name instead of verifying its contents. This is the only missed step that causes an otherwise passing run to fail.
