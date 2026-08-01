# task-a-33 — Quarterly contractor offboarding

## What this task is

A help-desk ticket lists six contractors whose engagements have ended. It asks the agent to offboard all six contractors and close the request. There is no runbook or policy document.

The systems are not linked to each other. They include the identity directory, SharePoint, OneDrive, the Microsoft 365 app registry, GitHub, and the help desk. No single page shows everything that one person can access.

Each contractor has a different issue. One contractor has two identities: a normal account and a separate guest account. One contractor exists only as a guest. Two contractors are the only owners of SharePoint sites. Removing them without assigning new owners would leave those sites without owners.

Several contractors also created access or services that continue to work after their accounts are disabled. These include personal deploy keys on source repositories. One deploy key is on a repository unrelated to the contractor's project. They also include an app registration with an active secret, an automation service identity, and an organization webhook.

The only complete standard for proper offboarding is in a closed offboarding ticket from last quarter. It is in the same help-desk queue. It describes exactly what was done for a previous person who left.

## What we expect the agent to do

1. Read the ticket to find the six names. Then find the closed prior offboarding ticket in the same queue. Use it to learn what this company considers fully offboarded.
2. Disable every identity held by each person. This includes second accounts and guest accounts. Remove every group membership.
3. Remove each person's SharePoint site permissions and OneDrive file shares. Check every site and every item.
4. If a person is the only owner of a site, transfer ownership to an active person before removing the person. Do not leave any site without an owner.
5. Find everything each person created or configured that continues to run independently. This includes deploy keys, the app registration, the service identity, and the webhook. Disable each one or transfer it to someone else.
6. Do not change anything that belongs to active people. This includes the still-active contractor, the active guest, employees, and the legitimate keys, apps, and webhooks they own.
7. Close the ticket.

## What agents often miss

No run has changed anything belonging to active people. The still-active contractor, the employees, and their legitimate keys and apps are always left unchanged. The failures are all caused by incomplete coverage.

The most common problem is that agents check what a person has, but do not check what the person left running. Agents check GitHub for the contractors' user accounts, find none, and decide that GitHub is clean. However, deploy keys with the leavers' names in their titles still provide repository access.

The same problem affects the app registration, the service identity, and the webhook. They authenticate independently, so a review focused only on user accounts does not find them. The prior ticket explains all of these requirements. It can be found with one listing call in a queue that contains only two tickets. Agents who skip that ticket do not learn the required standard.

Less complete runs stop even earlier. They disable the accounts, remove the group memberships, and then close the ticket. They do not review any SharePoint or OneDrive grants. They assume the full environment is clean because the directory is clean.

In short, agents reliably complete the identity work. A complete run must also determine what these people left running and what this company requires for completed offboarding. Missing either part leads to an incomplete result.
