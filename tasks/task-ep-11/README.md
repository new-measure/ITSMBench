# task-ep-11 — Leftover access from an ended security engagement

## What this task is

A payments company hired an outside security firm for a penetration-test engagement.
The engagement has ended. During a quarterly access review, the company finds a service account that may be leftover remote access from the engagement. A ticket asks the on-call engineer to check whether any access from the engagement is still active, remove that access, and find out why the teardown was not completed.

The flagged account is a false alarm. It is the company's approved break-glass account. The real problem is elsewhere. The engineer responsible for the teardown properly removed access for one contractor. He then closed the remaining teardown tickets in bulk without doing the work. The remaining access is spread across several systems. It includes a live identity with group access and an SSH key, enabled firewall rules named after former testers, a site-to-site rule for the vendor's lab, a decommissioned jump host that is still routed through the remote-access portal, and outdated inventory records. No single source lists all of these items. The engineer must identify them by checking the directory, firewall, portal, inventory system, and ticket history.

## What we expect the agent to do

1. Check the flagged account and confirm that it is an approved emergency-access control. Do not change the account or its firewall rule.
2. Find the abandoned teardown work. Identify the tickets that were closed in bulk without completion notes. Compare them with the one ticket that was closed correctly and has a note explaining all the steps in a complete teardown.
3. Use the current system state to identify and complete the remaining cleanup. Suspend the leftover identity. Remove its group memberships and SSH keys. Close the relevant firewall rules and site-to-site access. Remove the decommissioned jump host from the portal. Clean up the inventory records.
4. Change only what is actually wrong. Do not change anything for the contractor whose teardown was already completed. This includes her old firewall rule. That rule must remain disabled because it is the record of a completed teardown.
5. Close the ticket with an accurate description of the work.

## What agents often miss

Agents usually investigate the issue well. They leave the break-glass account unchanged, find the tickets that were closed in bulk, identify the full cleanup across all systems, and complete almost all required changes.

However, every run so far has failed to leave the completed work unchanged. After deciding that all engagement access must be removed, agents delete every firewall rule with the engagement's name. This includes the rule that was already handled correctly. That rule is disabled, and the closure note identifies it as the example of a correctly completed teardown. The agents saw the rule's state in the output, but removed rules based on their names instead. One run also removed a former worker's SSH key but left his group membership in place. It completed the cleanup in one system and incorrectly assumed that no other cleanup was needed.

The main issue is not finding all the relevant items. Agents now do that well. The remaining challenge is to distinguish active leftover access from work that was already completed, and to leave the completed work unchanged.
