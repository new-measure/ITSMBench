# task-a-37 — External collaborators who never fully left

## What this task is

A helpdesk ticket at a product company lists six external collaborators whose work has ended. The ticket asks the agent to offboard them. Their accounts are in the usual systems: chat, email, identity, wiki, and code hosting. Most of the work is standard. Find each person's accounts and grants, remove them, and close the ticket.

However, some access is stored separately from user accounts. The collaborators also have direct share entries for wiki pages and databases. One collaborator is the only owner of a team space, so ownership must be transferred before that person is removed. Another collaborator left a deploy key on a repository. User lists do not show these items. The agent must query each system for its shares and the people who have access. An earlier closed offboarding ticket is in the same helpdesk queue. It explains what a complete cleanup includes.

## What we expect the agent to do

1. Read the ticket and complete the work for all six people.
2. Use the earlier closed offboarding case to learn what a complete cleanup requires. Do not create a shorter process that only deactivates accounts.
3. Remove chat, email, and identity accounts. This includes duplicate guest identities with email addresses that do not exactly match the ticket.
4. Remove every form of code-hosting access. Remove organization membership, direct repository grants that remain after organization membership is removed, and leftover deploy keys.
5. Find and remove every collaborator's direct wiki shares. Transfer the orphaned team space to someone who still works at the company.
6. Do not change anything for other people. Current staff, their shares, and all other team spaces must stay exactly as they are.
7. Close the ticket.

## What agents often miss

Agents usually complete the account-related work. Every scored run deactivated the correct people, cleaned up chat, email, and identity, and closed the ticket without changing anything for other people.

However, every run missed access to shared content. No run queried the wiki's share records. Searches for "page permissions" returned page-editing endpoints instead. The runs then decided that the wiki had nothing else to remove and continued. As a result, the collaborators kept their direct shares, the departed owner remained the owner of the team space, and the deploy key remained active. Some runs also assume that removing a person from the code-hosting organization removes all access. Direct repository grants remain after organization membership is removed.

In short, agents remove accounts but forget to remove the shares, ownerships, and keys that were assigned to those accounts and remain after the person leaves.
