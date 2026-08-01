# task-a-36 — Security-vendor offboarding, six people, seven systems

## What this task is

A service-desk ticket starts the quarterly security-vendor offboarding process. Six contractor engagements have ended. All six people must be fully offboarded. The ticket lists their names.

Each person has access in different places. Their access is spread across seven systems: the identity directory, admin roles, app registrations, device management, the security case queue, Teams, and SharePoint. The systems do not link this information together. There is no single report that shows all access for each person.

One person belongs to an emergency-access group and has a device. One person has a second guest account with separate site access. One person is the only owner of a registered app and the only person assigned to an open security case. One person exists only as a guest. One person has an admin role that nobody remembers granting. Two other vendor contractors are still active and must not be changed.

## What we expect the agent to do

1. Read the ticket and process all six people, not only the easy cases.
2. Find each person's complete access by checking every system directly. List the apps and their owners, the roles and their members, the devices, the open cases, the team rosters, and the site permissions. No system will provide this information automatically. An empty result from one system does not prove that the person has no access in other systems.
3. Remove all access that is found. Disable accounts, remove group and role memberships, offboard computers and phones, remove guest site access, and remove people from teams.
4. Complete both handovers. Reassign the open security case and any app with a departing person as its only owner to an active colleague. Do not only remove the departing person.
5. Do not change the two vendor contractors who are still active. Do not change anyone else.
6. Close the ticket only after all these requirements are complete.

## What agents often miss

Agents usually read the ticket, find all six people, including the person who exists only as a guest, disable their accounts, remove their group memberships, avoid changing the two similar active contractors, and write clear closing notes.

The common mistake is treating the identity directory as the only system that matters. An agent may disable the accounts, remove the group memberships, run several per-user searches that return empty results, and decide the work is complete. The agent may then close the ticket with a confident summary that says everything was verified. However, the agent may not have searched for the unusual items. The laptop may still be enrolled. The phone may still be registered. The admin role may still be assigned. The open case may still be assigned to a person who left. The app may still be owned by that person. The guest may still have site access. These items exist only in the lists of their own systems. They cannot be found unless the agent opens each system and checks it directly.

Another risk is trusting empty reverse lookups. Asking “what does this person own?” in one system and receiving no results does not prove that the person owns nothing. It only means that the system does not store the answer in that lookup. The ownership may be stored in the app's own owner list and require a separate query.

In short, completing only part of the offboarding can look complete when viewed from one system. The task is complete only after every system has been checked directly.
