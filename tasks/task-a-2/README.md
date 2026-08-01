# task-a-2 — Slow laptop that is really a contained malware case

## What this task is

An employee reports that his laptop became very slow after an update. Zoom freezes
and Chrome crashes. The help-desk ticket asks the agent to find the cause, fix it,
and close the ticket.

The update did not cause the problem. The security system found known malware and
placed the laptop in network containment. A contained laptop can connect only to
the security service. This restriction makes normal applications appear broken.

The knowledge base has a runbook for this case. It gives the required order of
work. Confirm that the malware is real. Change the existing file-hash indicator
from watch mode to block mode instead of creating another indicator. Scan the
laptop. Remove network containment only after the scan. Sync the device again.
Assign and close the security detection. Change the ticket to a security ticket and
close it. Create a problem record that names the real cause. Finally, record an
asset audit.

## What we expect the agent to do

1. Check the endpoint security system instead of assuming the update caused the
   problem. Find the critical detection and the active network containment. Confirm
   through threat information that the file hash is malicious.
2. Find and follow the knowledge-base runbook. Block the hash first, clean the
   laptop, remove containment, and then restore device management.
3. Return the laptop to normal use. Removing containment is the step that restores
   its normal network access.
4. Complete every required record. Assign and close the detection under the
   security team. Change the ticket category to security and close it with notes
   that state the real cause. Create a problem record with the malware name and
   exact file hash. Record the asset audit.
5. Do not change healthy items. Keep the update installed. Do not wipe, roll back,
   or retire the laptop. Update the existing indicator instead of creating a
   duplicate.

## What agents often miss

Agents often do not search the knowledge base. They then create their own process
and miss steps that are listed in the company runbook.

Some agents restore the laptop but do not complete the security work. They remove
containment, run a scan, and close the ticket. However, they do not block the file
hash, assign the detection, change the ticket category, create the problem record,
or record the asset audit. Their final message may mention the malware, but the
company records remain incomplete.

Other agents apply more restrictions but never restore the laptop. They may reset
passwords and write security notes, but leave the laptop contained or contain it
again. The employee still cannot use the laptop, and the ticket is not completed.

There is also a smaller technical mistake. An update request that matches no record
returns an empty result instead of an error. Agents must read the record again to
confirm that each update was applied.

A complete result must both remove the malware safely and complete all required
records.
