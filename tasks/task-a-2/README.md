# task-a-2 — Slow laptop that is really a contained malware case

## What this task is

A helpdesk ticket from an employee: his laptop became very slow after the latest
update — Zoom freezes, Chrome crashes. The ticket asks the agent to find the cause,
fix the problem, and close the ticket.

The update is innocent. The real cause is that the security tooling detected known
malware on the machine and placed it in network containment. A contained host can
only reach the security cloud, which is exactly why everything on it feels broken.
The company even has a knowledge-base runbook for this exact situation, spelling out
the right order of work: confirm the malware against threat intel, block the bad
file hash by escalating the existing watch-mode indicator (not by creating a
duplicate), scan the machine, only then lift containment, re-sync the device, close
and assign the detection, reclassify and close the ticket as a security case, open a
problem record naming the real cause, and record an asset audit.

## What we expect the agent to do

1. See past the reported symptom: check the endpoint in the security tools, find the
   active critical detection and the containment, and confirm the file hash is truly
   malicious before acting.
2. Find and follow company practice — the runbook in the knowledge base — rather
   than inventing a procedure. Order matters: block the hash first, clean the
   machine, then lift containment, then re-establish management.
3. Restore the user to normal work. Lifting containment is what actually fixes "my
   laptop is slow."
4. Finish the record-keeping the way the company does it: detection closed and
   assigned to the security team, ticket reclassified to security and closed with
   notes naming the real cause, a problem record capturing the malware and the exact
   hash, and the asset audit logged.
5. Leave the healthy things alone: the blamed update stays, the device is not wiped,
   rolled back, or retired, and the existing indicator is escalated in place.

## What agents often miss

No run has ever opened the knowledge base, so no run has found the runbook that
lists every required step — each one improvises its own procedure and leaves gaps
the company's own playbook would have prevented.

The improvised runs fail in two opposite ways. One style fixes the machine but skips
the security follow-through: containment lifted, scan run, ticket closed — while the
malicious hash is never actually blocked, the detection is never assigned, the
ticket keeps its old non-security category, and no problem record or asset audit
exists. The final summary names the malware; the records left behind do not. The
other style goes full lockdown and forgets the user: passwords reset, heavy security
notes written, but the machine is kept contained (or contained again), so the laptop
never comes back online and the ticket the user opened is never properly closed.

A smaller repeated stumble: an update call that matches nothing returns an empty
result rather than an error, and runs that do not read the record back afterwards
believe a change landed when it did not.

In short: finding the malware is common; finding the company's procedure for it is
not. The runs that fail treat either the fix or the paperwork as optional.
