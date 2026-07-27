# task-iam-18 — Guest access review (find the hidden reasons)

## What this task is

A periodic guest-access review. Over time, external guest accounts pile up across the
corporate directory, the source-control organization, and the chat workspace. A
ServiceNow request asks the agent to review the whole guest estate, remove access that
is no longer legitimate, and keep the guests that are still active.

Some guests are clearly stale, and the reason shows right in the directory: one is past
its own expiry date, one was sponsored by an employee who has left. Others look
perfectly fine from the directory alone — an unexpired account, an active sponsor — yet
are stale for a reason recorded somewhere else: two belong to a partner company that has
been shut down, and one is a person who has since become a full employee, so the guest
identity is now a duplicate. Each stale guest's access is spread across all three
systems.

## What we expect the agent to do

1. Review every guest, not just the obvious ones.
2. Decide whether each guest is still legitimate using all the evidence, not only the
   directory. That means finding and reading the partner-company register and the
   guest-to-employee conversion record, which live in their own tables.
3. For each stale guest, remove its access everywhere it is held: disable its directory
   sign-in, remove it from its security groups, remove its source-control grant, and
   deactivate its chat account.
4. Leave the legitimate guests and the real employees alone, including the employee
   behind the duplicate guest.
5. Close the review request once the estate is correct.

## What agents often miss

Runs handle the guests whose staleness is visible in the directory: the expired account
and the one whose sponsor departed get cleaned up across all three systems.

What runs miss is the staleness that is not visible from the directory. Two guests are
stale only because their partner company was decommissioned, and one is stale only
because the same person is now an employee. Nothing on those accounts looks wrong on its
own — the deciding facts sit in separate records the agent has to go looking for. Runs
do not check what other data exists, so they never open the partner register or the
conversion record, and they leave those guests in place while reporting the review
complete. The result is a review that fixed the easy half and declared the whole estate
clean.

A smaller trap runs the opposite way: removing or disabling a guest that is still
legitimately active, which is over-reach, not cleanup.

In short: cleaning up the obviously-stale guests is reliable; digging out the reasons a
healthy-looking guest is actually stale — and stopping short of the guests that should
stay — is what separates a finished review from a partial one.
