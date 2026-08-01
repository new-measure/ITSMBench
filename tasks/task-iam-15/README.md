# task-iam-15 — Too many standing administrators

## What this task is

A quarterly access audit at a data company finds a least-privilege violation. Too many people have permanent platform administrator access. A ServiceNow ticket asks the agent to reduce the number of standing administrators to the required minimum. The agent must remove the extra privileged access, keep the documented emergency-access controls, and close the ticket.

The ticket only states the objective. It does not name any people or systems. The reason for the problem is that a delivery project ended at the end of May. The temporary elevated access given to the project squad was not removed. This access exists in several places: membership in the admin group, a directly-assigned admin role, GitHub organization and team privileges, a deployment service account, and deploy keys added to repositories. An earlier project was closed correctly. Its change record shows all the cleanup steps that are required. A documented break-glass account must not be changed.

## What we expect the agent to do

1. Read the ticket. Use only the environment to determine the required minimum number of administrators and identify who has unnecessary admin access.
2. Identify the group of people by tracing how they received access. The closed project change and the identity system's log show exactly who received temporary access during the project period.
3. Remove all extra access from every place where it exists. This includes admin group membership, the directly assigned admin role, GitHub organization-owner and team-maintainer privileges, the project's deployment service account, and its deploy keys on the repositories.
4. Do not change the legitimate standing admins, the emergency break-glass account, or any unrelated people.
5. Record the completed work and close the ticket.

## What agents often miss

Most runs complete this task successfully. Agents usually identify the group through the closed change and the identity log. They remove access from the admin group and roles, clean up GitHub access, deactivate the service account, and correctly leave the break-glass account unchanged.

The one known mistake involves credentials. An agent can remove access from every person and deactivate the deployment service account but fail to check what credentials the account created. Deploy keys can remain on the repositories. These keys continue to work even when the related user or account is disabled. The keys are a separate form of access. User and account records do not show them. The agent must list the keys on each repository to find them. If an agent only removes accounts and roles, this access remains active and the related checks fail.

In short, agents usually clean up people and roles correctly. To complete the task, they must also remember that added credentials provide access and check every repository for deploy keys.
