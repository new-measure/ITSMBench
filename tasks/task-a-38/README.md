# task-a-38 — Offboarding a batch of platform engineers

## What this task is

A help-desk ticket lists seven platform and DevOps workers whose engagements have ended. Offboard all seven people and close the ticket.

The company uses six separate systems that do not reference each other:

- single sign-on
- GitHub
- a separate Linux fleet directory
- an asset register
- a paging service
- the help desk

There is no runbook.

Each person has something that a normal account shutdown does not remove:

- One person created deploy keys and CI webhooks that still run under her name.
- One person is the only on-call target for payments paging.
- One person still has hardware checked out.
- One person has a second login in the fleet directory in addition to his SSO account.
- One person has direct app grants outside any group.
- Two contractors have no SSO account. They exist only in the fleet directory, so a process focused on SSO will not find them.

Do not change the access of current teammates who have similar-looking access.

## What we expect the agent to do

1. Read the ticket and handle all seven people, including the difficult cases.
2. Disable each person's logins in every directory where they exist. This includes the two contractors who exist only in the fleet directory.
3. Remove access that remains after a login is disabled. This includes group memberships, direct app grants, and GitHub org membership.
4. Find and handle everything each person created or held. Remove their deploy keys and webhooks by checking names and ownership so that teammates' items are not removed. Check in their hardware. Replace the paging rule that routes to a departed engineer with a live target. Do not leave the paging rule empty.
5. Do not change anyone else's access, keys, webhooks, or hardware.
6. Close the ticket only after all access and resources have been handled.

## What agents often miss

Agents usually complete the straightforward work. They find all seven people, disable logins in both directories, remove GitHub org memberships, assign paging to a live teammate, check hardware back in, and close the ticket. They also leave other people unchanged.

Agents often miss access that remains after a login is disabled. A run may report that a person's identity is fully closed after deactivating the account, while the person's group memberships, direct app grants, and created webhooks remain active. In one run, the agent carefully reviewed deploy keys and removed the departed engineer's keys. It then failed to list the webhooks available two calls away on the same repositories. Because the disabled login appears complete, agents may not audit the related systems.

In short, disabling the login is usually completed correctly. The task is only fully complete when everything the person left active is also removed or reassigned.
