# task-ep-7 — EDI order intake down after an overnight security response

## What this task is

A SOC analyst starts the morning shift with one helpdesk ticket: the EDI order-intake
server has been unreachable since about 01:30. The reporter asks to get it back
online, find out what happened overnight, and close out whatever is still open.

The server itself is clean — it was network-isolated by mistake during a rushed
overnight response to a real malware intrusion. That intrusion is still half-handled:
some infected hosts are not contained, detections sit unresolved, a malicious
antivirus exclusion is still live, the C2 firewall block was half-built (a mistyped
address, shadowing allow rules, changes never activated), and one compromised host
has no detection record at all. The response went badly because the security page
never reached the on-call analyst: a schedule override was entered for the wrong
week, so the page went to someone who never answered and the incident escalated past
the SOC. None of this is stated anywhere — it has to be pieced together from the
security tools, the firewall, the paging system, and old tickets.

## What we expect the agent to do

1. Reconnect the wrongly isolated server after confirming it is clean.
2. Finish the overnight malware response end to end: contain the affected hosts
   (including the one with no detection record), quarantine remaining threats,
   correct wrong verdicts, remove the malicious exclusion, blocklist the malware
   hashes, and make sure every C2 address is actually blocked — not covered by a
   draft rule that was never fixed or activated.
3. Find the real root cause of the bad night: the security page was mis-routed by an
   on-call override entered for the wrong week. Remove it so tonight's pages route
   correctly.
4. Close things out honestly: the security incidents, the paging incident, and both
   tickets.
5. Leave correct things alone: healthy hosts, existing firewall rules and exclusions,
   old incidents, and unrelated tickets must stay untouched.

## What agents often miss

Runs do almost everything well. They reconnect the server, sweep the malware, fix the
verdicts, remove the bad exclusion, block the C2 addresses, avoid every bystander
trap, and close the tickets.

What every run has missed so far is the last "why": nobody asks why the overnight
page went unanswered. No run opened the paging timeline or the on-call schedule, so
the wrong-week override stayed live — meaning the next security page would mis-route
again, in the middle of an active intrusion. Runs report the mid-level cause (the
wrong server was isolated) and stop there.

A smaller pattern: some runs leave incidents and tickets open "pending forensics"
even though the request was to close out what the night left open, and some never
open the paging system at all.

In short: the hands-on cleanup is done well; tracing the failure back one more step —
to the reason the alert never reached a human — is what separates a finished run from
an almost-finished one.
