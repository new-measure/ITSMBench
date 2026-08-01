# task-n-13 — Internal apps unreachable, working fine from outside

## What this task is

A P1 incident reports that corporate users cannot access several internal apps. The same apps work correctly from outside the company. The incident blames the app deploy from the previous evening. That deploy is not the cause. It did not change DNS or the network. The real cause is an overnight DNS migration. The migration was closed as "successful, validation deferred." It broke the company's internal name resolution without drawing attention.

The company uses split-horizon DNS. It has an internal view for staff and an external view for the public. The migration damaged the internal view in several ways. Some app records are completely missing. Some resolve to the wrong address. Some point to hosts that no longer exist. Some aliases still use a retired domain in their chain. An entire sub-zone is delegated to nameservers that are no longer working. The apps still work from outside because the external view was not changed. This makes the outside test misleading. It does not show that DNS is working correctly.

## What we expect the agent to do

1. Confirm that the blamed deploy is not the cause, then move on.
2. Identify the split-horizon design. The internal and external views are intentionally different. Therefore, "works from outside" is expected and does not mean DNS is working correctly.
3. Restore internal resolution for every type of broken record. Create the missing app records with their live internal address. Repoint records that use the wrong address or a dead address. Fix aliases that still use the retired domain in their chain. Repoint the sub-zone delegation to the live nameservers.
4. Remove records that point to nothing and are actually dangling.
5. Do not change the external view. Do not change services that correctly have no internal record. Do not change healthy peer records.
6. Resolve the incident.

## What agents often miss

Results differ greatly on this task. The strongest agents complete the entire process. They reject the incorrect deploy cause. They restore the missing app records. They repoint aliases so they no longer use the retired domain. They fix the delegation. They remove the dangling records. Weaker agents stop too early. They spend a long time investigating and then make few or no changes. This leaves internal resolution broken.

The task is difficult because the damage affects several record types that do not refer to each other. The direct app records are only the first part. There are also aliases that use a retired domain in their chain and a sub-zone delegated to dead nameservers. These problems do not appear when checking only the direct app records. Healthy peer records show what working entries should look like. An agent must continue checking after the obvious records resolve again to find these other problems.

Another common error happens during incident close-out. Agents mark the incident with a status label instead of the value that the system actually stores. This can make the incident appear complete even though it never reaches a closed state.

In short, finding the cause is the easy part. A complete result requires repairing every affected part of the DNS records and closing the incident correctly.
