# task-a-36 — Security-vendor offboarding, six people, seven systems

## What this task is

A service-desk ticket kicks off the quarterly security-vendor offboarding: six
contractor engagements have ended, and each person must be fully offboarded. The
ticket lists the six names — that part is easy.

The hard part is that each person's footprint is different, and it is scattered
across seven systems: the identity directory, admin roles, app registrations,
device management, the security case queue, Teams, and SharePoint. No system
links them together, and there is no report that says who holds what. One person
has an emergency-access group and a device. One has a second guest account with
its own site access. One is the sole owner of a registered app and the only
person assigned to an open security case. One exists only as a guest. One holds
an admin role nobody remembers granting. Two other vendor contractors are still
active and must not be touched.

## What we expect the agent to do

1. Read the ticket and work all six people, not just the easy ones.
2. Find each person's full footprint by checking every system directly — list
   the apps and their owners, the roles and their members, the devices, the open
   cases, the team rosters, the site permissions. Nothing will volunteer this
   information; empty answers from one system prove nothing about the others.
3. Close out everything found: disable accounts, remove group and role
   memberships, offboard computers and phones, remove guest site access, and
   remove people from teams.
4. Handle the two handovers: the open security case and the solely-owned apps
   must be reassigned to an active colleague, not just stripped.
5. Leave the two still-active vendor contractors, and everyone else, exactly as
   they are.
6. Close the ticket only when all of it is true.

## What agents often miss

The parts that go well: reading the ticket, finding all six people (including
the guest-only one), disabling their accounts, clearing their group
memberships, sparing the two look-alike active contractors, and writing tidy
closing notes.

The classic miss is treating the identity directory as the whole world. A run
disables the accounts, empties the group memberships, runs a few per-user
lookups that come back empty, and concludes the job is done — then closes the
ticket with a confident summary claiming everything was verified. But the odd
items were never looked for: the laptop still enrolled, the phone still
registered, the admin role still held, the open case still assigned to someone
who left, the app still owned by them, the guest still on the site. Those live
only in each system's own lists, and no run finds them without opening each
system and asking.

The subtle trap is trusting empty reverse lookups. Asking "what does this
person own?" in one system and getting nothing back feels like proof of a clean
slate. It only means that system doesn't keep the answer — the ownership is
recorded on the other side, in the app's own owner list, one query away.

In short: half an offboarding looks complete from inside one system. The task
is only done when every system has been asked directly.
