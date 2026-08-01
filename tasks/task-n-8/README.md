# task-n-8 — Non-compliant laptops before a Conditional Access cutoff

## What this task is

A high-priority ServiceNow ticket reports that several managed laptops are non-compliant. A "require a compliant device" rule will soon switch to hard enforcement. On that date, anyone whose laptop is still non-compliant will lose access to mail, chat and files. The ticket says the Finance team and a recent device policy change are the likely causes.

Both claims are wrong. The policy change made the rules slightly easier to meet. The problem also affects more than the Finance team. There are eight affected laptops across three departments. Each laptop is non-compliant for more than one reason.

There are also similar laptops that must not be changed. One laptop has an approved exemption. One laptop has an alert that was already confirmed as a false alarm. Two laptops are healthy.

The work requires four systems: the device manager, the security product, the directory and the ticket system.

## What we expect the agent to do

1. Read the ticket. Then check the change record that the ticket blames and confirm that the change caused no harm.
2. List every managed device. Do not rely on the department named in the ticket. Identify which devices are actually non-compliant.
3. Find the directory group assigned to the baseline compliance policy. The owners of the healthy laptops are members of this group. The exempt owner is in a separate group that is clearly labelled as an exemption group. The owners of the eight affected laptops are not members of either group.
4. Add those eight owners back to the required group.
5. Clear the six real security alerts on the affected laptops. Do not change the alert that is already marked as a false alarm.
6. Force a check-in on all eight stale laptops so they re-evaluate before the cutoff.
7. Close the ticket. Use the status value that the ticket system stores, not the word displayed on screen.

The exempt laptop, the false-alarm laptop and the two healthy laptops must remain unchanged.

## What agents often miss

Agents usually handle the security work correctly. They find the alerts, separate the real alerts from the false alarm, notice the stale check-in dates and force a sync. They also correctly reject both false leads in the ticket.

Agents often miss the directory step. They retrieve the required group's membership and record it in their notes, but do not connect it to the affected laptops. In one case, an agent compared the group members with the device owners. The agent only reported that two group members did not own laptops. This was harmless. The agent failed to notice that eight laptop owners were missing from the group. This happens because group membership shows who is already covered. An owner who is missing can appear to be out of scope instead of incorrectly removed. If the directory is not fixed, the laptops remain non-compliant.

Two smaller mistakes also happen often. One is setting the ticket's closing status to a word instead of the coded value stored by the system. This leaves the ticket open without an obvious error. The other is waiting for a laptop's compliance flag to change. It does not change by itself. The required work is to remove the causes of non-compliance and force a new check-in.
