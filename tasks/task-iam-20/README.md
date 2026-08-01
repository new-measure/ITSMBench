# task-iam-20 — Delegated-access review after a Finance reorg

## What this task is

After a Finance reorganisation, an access review finds delegated and impersonation access on the CFO office shared mailbox. A ServiceNow ticket asks the agent to remove access that is no longer legitimate and keep approved access.

The stale access exists in several places. The mailbox has delegates and send-as grants for people who left the company, people who moved out of Finance, and an outside party. It also has external forwarding and forward-filters that send mail to personal addresses. There is also stale third-party app access. Departed staff still have OAuth tokens. One manager who moved to Marketing still has an app with full-mailbox scope.

The ticket contains misleading information. It says the flagged external forwarding is "the new backup integration." This is false. The real backup is an approved read-only app that must remain. The external forwarding sends company data outside the company and must be removed. If the agent accepts the ticket's claim without checking the evidence, the data leak remains.

## What we expect the agent to do

1. Read the ticket and the reorg record. Identify who left the company and who moved out of Finance.
2. Remove stale mailbox access. Remove delegates and send-as grants for departed staff, people who moved out of Finance, and the outside party. Remove the external forwarding and the forward-filters.
3. Check the ticket's backup claim against the evidence. Keep the approved read-only backup app. Remove the external forwarding because it is data exfiltration.
4. Review each affected person's third-party apps, not only the mailbox. Revoke the departed users' OAuth tokens. Remove the moved-out manager's full-scope app.
5. Do not change approved access. Keep the approved delegates and send-as grants, the backup app, unrelated people's ordinary apps, and all user accounts. Removing delegated access does not require disabling any account.
6. Close the ticket.

## What agents often miss

Agents consistently avoid removing approved access. Every run keeps the approved delegates, keeps the backup app, and leaves all accounts unchanged. Nobody removes too much.

The main problem is that agents miss per-person app access. They clean up mailbox delegates, send-as grants, and forwarding. Then they stop reviewing access. They do not check each affected person's third-party app grants. As a result, the departed users' tokens and the moved-out manager's full-scope app remain. This happens even when an agent reads the reorg record and notes that the manager moved to Marketing. The agent identifies the move but does not audit that person's apps.

Another problem is that agents believe the ticket's claim. The ticket describes the external forwarding as the approved backup. Weaker runs accept this claim and keep the data leak. Stronger runs verify the claim. They find that the backup is a separate read-only app and remove the external forwarding.

In short, agents usually clean up mailbox delegation correctly. They often fail to continue the review for each affected person's app access. They may also trust the ticket's backup claim without checking it.
