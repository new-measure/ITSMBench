# task-ep-8 — Public internet exposure across a production AWS account

## What this task is

External exposure monitoring reports a public IP that may expose production data. A security-operations ticket asks the on-call cloud security engineer to confirm what is exposed across the AWS account. The engineer must restrict anything that should not be public and find the cause of the exposure.

The reported IP belongs to the company's approved public web load balancer. It is not a data leak. The actual problem is behind it. Nine other resources are publicly reachable but should not be. These resources include databases, a cache, a search cluster, an admin console, and two old load balancers. They became public for different reasons. These reasons include emergency changes that were not reverted, a database created by a pipeline without tracking, an acquisition import, a security alert that was closed as resolved even though the issue was not fixed, and an asset record that incorrectly identifies a database as a web frontend. Three public web endpoints are approved and must remain exactly as they are.

## What we expect the agent to do

1. Check the reported IP and identify it as an approved public endpoint, not a leak.
2. Check the entire account for public exposure instead of stopping at the reported address. Find every security group rule that is open to the internet and every public IP attached to a resource.
3. Use evidence to decide which public endpoints are legitimate. Check change tickets that state access was temporary. Check asset records that identify the environment and role. Do not decide based on resource names.
4. Completely remove each unintended exposure through both access paths. Remove the open ingress rules and detach the public IP. The resource remains reachable if only one path is fixed.
5. Find the less obvious problems. One resource has a clean main security group but also has a second, forgotten group. One cluster is exposed on two ports, although the alert mentions only one. One database has an asset record that identifies it as a web frontend.
6. Do not change the approved endpoints, the resource that is already fixed, or any clean internal resources.
7. Explain the root cause and close the ticket.

## What agents often miss

Agents usually perform this task well. They generally identify the reported IP as a false positive, check the whole account, and find the less obvious problems. These include the forgotten second security group, the second open port, and the incorrectly labeled database. No run has changed anything that should have remained unchanged.

The main difference between a complete solution and an almost complete solution is checking the source and history of each resource. An agent that does not read the change-ticket queue or the asset inventory cannot distinguish the two old, non-production load balancers from the approved public load balancers. They look the same at the network level, so the agent leaves them open. The same problem affects the admin console. Without reading the change ticket that says its public access was temporary, an agent may limit access to corporate addresses but leave its public IP attached. This leaves a public access path.

The network check is usually completed correctly. The common missing step is checking how each public endpoint was created and why it is public. The agent must revert endpoints that were never intended to remain public.
