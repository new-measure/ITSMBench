# task-iam-16 — Over-shared resources (keep the justified access)

## What this task is

A company data-governance review identifies several sensitive resources that have been shared with more people than intended. These resources include deal-room sites, finance documents, and board material. A service-desk ticket asks the agent to reduce access to the minimum required level. The agent must remove access that is too broad and keep access that is valid.

Most removals are clear. The agent must remove anonymous links, company-wide links, unrelated groups, vendors, contractors, and employees who have no business need. However, one case requires careful judgment. One external person with access is an approved M&A advisor working on an active deal. A valid, closed change request in the service desk records approved this access. The agent must not remove this person. Removing the advisor may look like correct cleanup, but it would cause harm.

## What we expect the agent to do

1. Read the ticket and review the current permissions for every flagged resource.
2. Use the ownership and audience records in the environment to identify the intended audience for each resource. Do not guess.
3. Remove every grant that is too broad. This includes open links, broad groups, and people who have no connection to the resource. Check effective access, not only direct shares. A viewer may have access through a nested group or an open link.
4. Before removing access for any external person, check whether there is a valid justification. One external advisor has an approved access request. Keep that access.
5. Do not change valid access. Keep resource owners, intended teams, and other resources that are shared correctly. Do not change the directory.
6. Close the ticket and provide an accurate summary.

## What agents often miss

Agents complete the basic permission changes in every run. They remove all over-broad links, groups, and unrelated people. They keep access for the intended audiences and close the ticket.

One decision determines whether the run passes or fails. In failed runs, agents see an external company email address on a sensitive deal site and remove it without checking. One summary even stated that removing "external advisors" was an achievement. These agents did not make any query to the change records to check whether the access was justified. In passing runs, agents checked whether the grant had an approval. They found the closed change request and kept the advisor's access.

Removing access is simple. The main requirement is to prove which access must remain. Runs fail when agents do not look for that proof.
