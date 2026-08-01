# task-ep-5 — Custodian data missing from a legal collection

## What this task is

Meridian Instruments is a medical device company. It is being sued over its VP-220 infusion pump. Legal holds were placed on five employees in June. One month later, outside counsel ran the document collection again and found that some data was missing. A helpdesk ticket asks the agent to restore the custodians' data to the state it was in when the holds were applied. The agent must also find out what caused the problem.

A person did not cause the problem. An automated content-lifecycle job ran one night after the holds were applied. It cleaned up old content across all systems. It moved quality records into archive folders. It rewrote index rows. It moved personal drive folders out of their original locations. It revoked a share used by litigation support. It moved wiki pages under an archive page. It also archived a chat channel. The same job changed a lot of content that was not related to the lawsuit. The ticket gives an example of a report that appears to be missing. That report was never missing. Its owner renamed it before the holds were applied.

## What we expect the agent to do

1. Recognize that the report named in the ticket is not part of the problem. Its owner renamed it. It was not deleted. Leave it unchanged.
2. Find the real cause. The lifecycle job run appears in the audit log, wiki page histories, and channel messages. All of these records contain the same reference.
3. Reverse the changes that this run made to matter data belonging to the five custodians. Do this in every affected system. Move the files back to their original locations. Correct the index rows that the job rewrote. This includes rows that the job changed even though it did not move the files. Return the moved folders. Grant the revoked share again. Move the wiki pages back. Unarchive the channel.
4. Do not restore anything outside this scope. The same run archived files belonging to other people. It also archived other channels and pages. Those changes were valid cleanups and must remain in place. Files that owners moved themselves must stay in their current locations. Anything archived before the holds were applied must remain archived.
5. Close the ticket with an accurate explanation of what happened.

## What agents often miss

Agents usually investigate the problem correctly. Every run recognized that the report named in the ticket was not the real problem. Every run correctly identified the lifecycle job as the cause. No run wiped, deleted, or damaged anything important.

The main problem is that agents do not restore everything changed by the cleanup job. Most runs create their repair list from the audit log. However, the audit log only records file-system changes. The same job also moved wiki pages and archived a chat channel. Those systems store their own evidence. Several runs found the channel message that said the lifecycle policy had archived the channel. They used that message to confirm the cause, but they did not return to unarchive the channel. No run checked the wiki.

Scope is another problem. The job moved both custodian files and non-custodian files in the same batch. Some runs restored everything changed by the job. This incorrectly restored other people's files that had been archived for valid reasons. One run reversed a file move that the owner had made. Some runs corrected the index rows but did not move the actual files. This left the records showing a state that did not match the real file locations.

The diagnosis is usually correct. The difficult part is completing the restoration in every affected system while changing only data for the people under hold.
