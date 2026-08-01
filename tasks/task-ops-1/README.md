# task-ops-1 — End-of-shift handoff on a chaotic incident board

## What this task is

An overnight wave of incidents left Northwind Pay's service desk disorganized. You are the duty manager handing the service desk to the next shift. You must make the **entire** open board consistent, not just handle the main outage. Monitoring has already opened problem `PRB0040100` for the developing major issue. Dozens of similar tickets are nearby. Many have incorrect labels, tags, or assignment teams.

Identifying tickets from the same outage requires checking several fields. Some real child incidents are on the failed service. Others are on services that depend on it, including services connected through multiple CMDB dependency steps. A few incidents are related only because they share a monitoring correlation id. Their CI is incorrect or blank. Some nearby tickets appear related but are not. They may use similar wording, affect the same service at a different time, or belong to a separate reporting outage with its own problem. Routing and priority are also incorrect across the board. Keyword-based automatic assignment sent tickets to the wrong support groups. At least one business-critical incident with a breached service commitment still has a routine priority.

## What we expect the agent to do

1. Identify which open incidents have the same underlying outage as `PRB0040100`. Use the CMDB dependency graph, timing, and correlation signals. Do not rely on keyword similarity.
2. Attach those incidents to the problem and close them as duplicates. Do not change similar-looking tickets or unrelated clusters.
3. Link the problem investigation to the change that caused the outage. Move the problem out of its initial state.
4. Reassign every open ticket whose assignment group does not match the support group of its affected configuration item.
5. Increase priorities when actual business impact and breached service commitments require it. Pay special attention to a critical service whose resolution SLA has already breached.

## What agents often miss

Agents usually find the obvious payment-auth child incidents and link a possible change. They often fail to identify every incident in the cluster. They stop at the named CI. They miss dependent services connected through multiple CMDB steps. They may also miss incidents that are related only through the shared correlation id. The opposite mistake is combining unrelated incidents. This includes the reporting cluster, older tickets on the same CI from before the outage window, and tickets that only contain the word "payment."

Agents also often focus only on the major incident. They leave incorrectly routed tickets and the SLA-breach priority unchanged. Choosing the correct change is another common problem. The tickets often blame an application deployment. However, the change that matches the outage start time is the signing-cert rotation on the auth service. Handling only the main outage is not enough. The whole board must be consistent before the next shift takes over.
