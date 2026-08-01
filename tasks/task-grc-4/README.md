# task-grc-4 — Certification campaign says done; the access says otherwise

## What this task is

A payments company has just completed its quarterly certification of privileged access.
Every reviewer submitted their decisions. The campaign platform shows the campaign as complete.
Before audit fieldwork starts, a ticket asks the access-certification manager to confirm that the environment matches the campaign decisions.

A recorded decision is not always an applied decision.
Across the campaign's review instances, many "remove" decisions were recorded but never carried out.
Denied admin roles, privileged group memberships, and application assignments are still active in the identity provider.
Reviewers also decided to restrict two entitlement packages, but those packages are still open to every employee.
One review was fully applied.
The platform's status is correct for some items but incorrect for others.
Each decision must therefore be checked against live access, not the campaign's own records.

## What we expect the agent to do

1. Read the ticket and identify the campaign's full scope. This includes every review instance and every decision in each instance.
2. Check each decision against the live system that controls the related access. Do not trust the recorded status.
3. Apply every recorded decision that was not carried out. Remove the denied admin roles, group memberships, and application assignments.
4. Apply the restriction decisions correctly. Limit who the two entitlement assignment policies allow so that the packages are truly restricted. Do not only hide or rename them.
5. Do not change approved access or access outside the campaign's scope.
6. Close the ticket with an accurate record of what was found and fixed.

## What agents often miss

Most runs complete the main work correctly.
They do not trust the campaign status.
They check every review instance.
They find decisions that were not applied.
They remove the denied roles, group memberships, and application assignments without changing approved access.

The restriction decision is often handled incorrectly.
Removing access is a common operation with a clear API.
Restricting an entitlement correctly is less obvious.
An agent may hide the entitlement package from the catalog and report that it is "restricted."
However, the assignment policy still allows every member of the company.
This means that the set of people who can receive the access has not changed.
The agent acted on the decision, but changed the wrong setting.
Its summary then incorrectly reports success.
To close the task completely, verify the exact field controlled by the decision: who is allowed, not how visible the package is.
