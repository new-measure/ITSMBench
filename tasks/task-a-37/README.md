# task-a-37 — External collaborators who never fully left

## What this task is

A helpdesk ticket at a product company lists six external collaborators whose
engagements have ended and asks the agent to offboard them. The accounts span the
usual systems — chat, email, identity, wiki, code hosting — and most of the work
is ordinary: find each person's accounts and grants, remove them, close the ticket.

The catch is that some access does not live where accounts live. The collaborators
were also shared into wiki pages and databases through direct share entries, one of
them was the sole owner of a team space that must not be left ownerless, and one
left a deploy key behind on a repository. None of that shows up when you list
users — it only shows up when you ask each system what it has shared and with
whom. A closed ticket for an earlier, similar offboarding sits in the same
helpdesk queue and describes what a complete cleanup looks like.

## What we expect the agent to do

1. Read the ticket and work through all six people, not just the easy ones.
2. Learn the completeness bar from the earlier closed offboarding case instead of
   inventing a shorter "deactivate the accounts" routine.
3. Remove chat, email, and identity accounts — including duplicate guest
   identities whose emails do not exactly match the ticket.
4. Remove code-hosting access in every form: organization membership, grants made
   directly on repositories (which survive removal from the organization), and
   leftover deploy keys.
5. Find and remove the direct wiki shares for every collaborator, and hand the
   orphaned team space to someone who still works there.
6. Leave everyone else alone: current staff, their shares, and the other team
   spaces stay exactly as they are.
7. Close the ticket.

## What agents often miss

Runs handle the account-shaped work well. Every run we scored deactivated the
right people, cleaned up chat, email, and identity, and closed the ticket without
touching any bystander.

What every run missed is the shared-content surface. No run ever queried the
wiki's share records — searches for "page permissions" surfaced page-editing
endpoints instead, the runs concluded the wiki had nothing more to remove, and
moved on. So the collaborators kept their direct shares, the orphaned team space
kept its departed owner, and the deploy key stayed live. Some runs also assume
that removing someone from the code-hosting organization removes everything —
grants made directly on repositories quietly survive.

In short: agents offboard accounts; they forget to offboard the things accounts
were given — shares, ownerships, and keys that outlive the person.
