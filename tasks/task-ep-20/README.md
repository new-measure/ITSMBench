# task-ep-20 — External readers on a restricted document site

## What this task is

A company security review finds that an external group can read a restricted document site. The group should not have any access. The finding is recorded on a wiki page. The agent is the documentation governance operator. The agent must remove all access that should not exist and find out why it was granted.

The named site is only the first known issue. The external group received access through a bulk import during an acquisition. That import also gave the group read access to three other restricted sites. One site still gives access to an offboarded individual. Another site has an anonymous view link. A confidential site gives access to a directory group whose members are all offboarded. The contractors in the external group were offboarded in the identity system months ago. However, their accounts in the company's separate knowledge-base workspace are still active. No single source lists all these issues. The agent must check every site and every directory to find them.

## What we expect the agent to do

1. Remove the external group's access from the named site.
2. Continue checking the other restricted sites. Remove every grant connected to the same import. This includes the group grants, the offboarded individual's grant, the anonymous link, and the grant to the directory group whose members are all offboarded.
3. Find the root cause. An integration account made a bulk access grant during the acquisition. The access was never removed when the contractors were offboarded.
4. Check the same group of contractors in the second directory. Their knowledge-base workspace accounts are still active even though their main identities were deprovisioned. Deactivate these accounts, but do not delete them.
5. Do not change legitimate access. The approved partner site, the public help center, internal staff, and retained vendor accounts must remain exactly as they are.
6. Update the finding page with what was found and what was done.

## What agents often miss

Agents usually complete the permission check correctly. Every run removes the external group from the named site. It then checks the related restricted sites, finds the anonymous link and the grant to the group of offboarded users, identifies the acquisition import as the root cause, and documents the work. It does this without changing legitimate access.

Every run misses the second directory. The contractors appear fully offboarded in the main identity system. Agents check that system but do not check the separate knowledge-base workspace directory. As a result, they do not deactivate the contractors' active accounts there. Most runs never open that directory. One run listed the directory and found the active external accounts, but still did not deactivate them. It decided that the records should remain for audit purposes. Deactivating an account keeps the record. Leaving the account active keeps the access.

In short, agents remove the visible permissions but miss the offboarded people who can still log in to the knowledge base.
