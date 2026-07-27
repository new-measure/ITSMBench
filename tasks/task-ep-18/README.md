# task-ep-18 — Patched fleet that isn't

## What this task is

A security review says a critical application vulnerability was patched across the
fleet weeks ago, yet the endpoint-security tool is still flagging one production
server on the old version. A ServiceNow incident asks the agent to confirm the fleet
is actually remediated and get to the bottom of why the finding is still showing.

The flagged server is a false alarm: it was patched and verified; only the security
tool's vulnerability record is stale. The real problem is everything around it. The
patch wave was driven by a device group in the security tool, and that group was
built from a stale list: several vulnerable production machines were never in it, one
of them is hidden from the console, one exists only in the asset inventory, one only
in the device-management directory, and one sits parked in a maintenance hold whose
window came and went. One legacy host is genuinely exempt and must be left alone.
None of this is stated anywhere — it comes out only by checking the security tool,
the asset inventory, and the device directory against each other.

## What we expect the agent to do

1. Clear the flagged server: show its patch was real and the finding is stale, and
   do nothing destructive to it.
2. Ask the bigger question the ticket implies: is the rest of the fleet actually
   patched? Sweep every inventory, not just the security tool — machines missing
   from one system show up in another.
3. Fix the patch cohort: add every still-vulnerable production machine to the
   deployment group, unhide the hidden one, and take the parked database out of its
   expired maintenance hold so it can finally be patched.
4. Respect the real exceptions: the exempt legacy host stays held, machines already
   patched stay where they are, and nothing outside production is touched.
5. Close the incident with an honest account of what happened.

## What agents often miss

Diagnosis is consistently strong. Every run sees through the false alarm, finds the
stale security-tool record, and names most or all of the machines the patch wave
missed — including the ones visible only in the asset inventory or device directory.

Turning that diagnosis into a repaired fleet is where runs fall short, in several
ways. Some write an excellent summary naming every vulnerable machine and then close
the ticket without changing the group at all. Some rebuild the deployment group as
"only the machines still waiting" and strip out the already-patched hosts and the
flagged server — changing things that were correct. Some derive the wrong cohort and
sweep in bystanders that were never in scope. And nearly every run reads the parked
database's "moved to maintenance hold" note as a reason to leave it alone, without
asking whether that hold is still valid — the work order behind it is still open,
the window long past, the machine still vulnerable.

In short: finding the missed machines is done well; making the fix land — the right
machines added, the wrong ones left alone, and the stale hold challenged rather than
trusted — is what separates a finished run from a well-written summary.
