# task-grc-7 — Vulnerability register reconciliation after a scanner outage

## What this task is

A cloud company is preparing for a SOC 2 review. Its vulnerability scanner was unavailable for some time. During the outage, the tracking register in ServiceNow became inconsistent with the actual scanner results. A ticket asks the vulnerability-management lead to compare the register with the scanner's current results across the entire program and then close the incident.

There are several types of inconsistencies. Some tickets were closed as fixed, but the scanner still detects the vulnerability on the host. Some current findings have no ticket. Some overdue critical findings remained unassigned after their deadline. Some approved risk acceptances were not applied to the register. Some findings have duplicate records. Many records are already correct and must not be changed. These include closures confirmed by the scanner, minor scanner noise that the program intentionally does not track, and a false positive supported by real evidence.

## What we expect the agent to do

1. Read the incident. Use the scanner as the source of truth. A ticket's status is only a claim. Check every claim against the scanner results for that host before accepting it.
2. Reopen closed tickets when the scanner still reports the vulnerability. Create tickets for current findings that have no ticket.
3. Assign overdue critical findings and move them forward.
4. Apply approved risk acceptances that are still valid. Merge duplicate records so that each finding has only one active ticket.
5. Do not change records that are already correct. This includes confirmed closures, the supported false positive, low-severity scanner noise that the program does not ticket, and findings that have not yet reached their deadline.
6. Close the incident accurately.

## What agents often miss

Most runs complete the reconciliation work. They reopen incorrect closures, create tickets for missing findings, assign overdue critical findings, apply risk acceptances, and merge duplicate records.

The main risk is changing too much instead of too little. Some register records may appear incorrect but are actually correct. These include closures for scanner findings that are truly gone, minor informational findings that the program has decided not to track, and findings that are close to their deadline but are not yet overdue. Incorrect runs often create tickets for this scanner noise or escalate findings before their deadline. They assume that changing everything is safer than evaluating each record using its evidence. Careful runs check the scanner's actual results, correct only the records that conflict with those results, and leave all other records unchanged.
