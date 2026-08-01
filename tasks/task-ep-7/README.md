# task-ep-7 — EDI order intake down after an overnight security response

## What this task is

A SOC analyst starts the morning shift with one helpdesk ticket. The EDI order-intake server has been unreachable since about 01:30. The reporter asks the analyst to restore the server, determine what happened overnight, and close anything that is still open.

The server is clean. It was isolated from the network by mistake during a rushed overnight response to a real malware intrusion. The intrusion response is incomplete. Some infected hosts are not contained. Some detections are unresolved. A malicious antivirus exclusion is still active. The C2 firewall block was not completed. It contains a mistyped address, allow rules that take priority over the block, and changes that were never activated. One compromised host has no detection record.

The response failed because the security page did not reach the on-call analyst. A schedule override was entered for the wrong week. The page went to someone who did not answer, and the incident escalated beyond the SOC. None of this is directly stated. It must be determined by reviewing the security tools, firewall, paging system, and old tickets.

## What we expect the agent to do

1. Confirm that the wrongly isolated server is clean, then reconnect it.
2. Complete the overnight malware response. Contain all affected hosts, including the host with no detection record. Quarantine all remaining threats. Correct the wrong verdicts. Remove the malicious exclusion. Blocklist the malware hashes. Ensure that every C2 address is actually blocked. Do not rely on a draft rule that was never corrected or activated.
3. Find the actual root cause of the failed overnight response. The security page was sent incorrectly because an on-call override was entered for the wrong week. Remove the override so tonight's pages route correctly.
4. Close the security incidents, the paging incident, and both tickets. Record the outcome accurately.
5. Do not change anything that is already correct. Healthy hosts, existing firewall rules and exclusions, old incidents, and unrelated tickets must remain unchanged.

## What agents often miss

Agents usually complete almost all of the work. They reconnect the server, address the malware, correct the verdicts, remove the malicious exclusion, block the C2 addresses, avoid changing unrelated items, and close the tickets.

However, every run so far has missed the final cause. No agent asks why the overnight page went unanswered. No agent opens the paging timeline or checks the on-call schedule. As a result, the wrong-week override remains active. The next security page could be sent to the wrong person again during an active intrusion. Agents identify the intermediate cause, which was that the wrong server was isolated, but they do not investigate further.

Some agents also leave incidents and tickets open for "pending forensics," even though the request is to close anything left open from the overnight response. Some agents never open the paging system.

The operational cleanup is usually completed correctly. The task is only complete when the agent also identifies why the alert did not reach a person and removes the wrong-week override.
