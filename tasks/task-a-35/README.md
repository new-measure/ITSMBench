# task-a-35 — Q3 restructure: batch offboarding across six systems

## What this task is

A support ticket covers a company restructure. Several people have left the company. One person has changed roles. The agent must complete the full batch across six systems: Salesforce, HubSpot, PagerDuty, ServiceNow, Freshdesk, and Slack.

These systems do not have cross-links. No system knows what data the other systems contain. No system provides a complete view of everything linked to one person.

Each person has different accounts, access, and resources. One person owns customer records and a deal. These items must be reassigned to an active person. They must not be left without an owner.

One person has on-call duties. Their escalation duties and schedule coverage must be assigned to replacements.

One person created automation that still runs under her account. This includes a service account, scheduled jobs, and an API credential. These items are not listed with her name in any single place.

One person has a second integration login that is not easy to identify.

One contractor exists in only two systems and has no central identity.

The person who changed roles must lose only the access required by the old role. All other access must remain.

## What we expect the agent to do

1. Read the ticket and process every person listed in it. Do not process only the easy cases.
2. Find all accounts, access, and resources for each person by checking every system directly. There is no reverse index that shows all related items.
3. Fully deprovision the people who left. Disable their accounts. Remove their on-call coverage. Delete or deactivate their users and agents in every system where they exist.
4. Do not leave anything broken. Reassign owned records and deals to active people. Replace on-call coverage so there are no gaps. Handle automation that still runs under a person who left. Disable it, delete it, or transfer it to an active owner.
5. Handle the role change carefully. Remove access required by the old role. Keep the person active in all other systems.
6. Do not change anything that belongs to people who remain. Their accounts, schedules, and valid automation must stay exactly as they are.

## What agents often miss

Incomplete runs usually miss the items that a person created instead of the access they were assigned. Checking only each person's accounts can appear complete. However, automation may still run under the authority of a person who left. The service account, scheduled jobs, or permanent credential may remain active.

The automation may also be only partly fixed. One job may be disabled while related jobs continue to run. A record showing who created a job may be changed without removing the job's actual authority.

Unusual cases are another common problem. Using the same process for every person may skip the contractor who has no central identity. It may also miss the second integration login because it does not look like a personal account.

Runs with thorough discovery usually complete the work successfully. The actions are simple after all related items are known. The agent must continue looking for other items tied to each person after finding the obvious ones. It must do this for the full batch without changing anything that belongs to people who stayed.
