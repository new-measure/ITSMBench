# task-n-8 — Non-compliant laptops before a Conditional Access cutoff

## What this task is

A high-priority ServiceNow ticket says a batch of managed laptops is showing as
non-compliant. A "require a compliant device" rule is about to switch to hard
enforcement, and anyone still non-compliant on that date loses access to mail,
chat and files. The ticket points at the Finance team and at a recent device
policy change as the likely cause.

Both leads are wrong. The policy change only made the rules slightly more
forgiving, and the problem is not limited to Finance. The real set is eight
laptops spread across three departments, each held out of compliance by more
than one thing at once. Mixed in with them are look-alikes that must be
left alone: a laptop with an approved exemption, a laptop whose alert has
already been confirmed as a false alarm, and two laptops that are genuinely
healthy.

The work spans four systems: the device manager, the security product, the
directory and the ticket system.



## What we expect the agent to do

1. Read the ticket, then check the change record it blames and confirm it was
   harmless.
2. List every managed device rather than trusting the department named in the
   ticket, and work out which ones are really non-compliant.
3. Find the directory group that the baseline compliance policy is assigned to.
   The healthy owners are in it; the exempt owner sits in a separate,
   clearly-labelled exemption group; the eight drifted owners are in neither.
4. Put those eight owners back into the required group.
5. Clear the six real security alerts on the affected laptops, and leave the one
   alert that is already marked as a false alarm alone.
6. Force a check-in on all eight stale laptops so they re-evaluate before the
   cutoff.
7. Close the ticket, using the status value the ticket system actually stores
   rather than the word shown on screen.

Leaving the exempt laptop, the false-alarm laptop and the two healthy laptops
untouched is the expected judgment.

## What agents often miss

The security side goes well. Runs reliably spot the alerts, tell the genuine
ones from the false alarm, notice the stale check-in dates, and force a sync.
They also see through both false leads in the ticket.

The step that gets dropped is the directory one. Runs fetch the required group's
membership, list it in their notes, and still never connect it to the broken
laptops. In one case a run put the group's members and the device owners side by
side, then reported only the harmless direction of the gap — two people in the
group who own no laptop — while missing the eight laptop owners who are absent
from the group. The reading behind this is that group membership describes who
is already covered, so an owner who is missing looks out of scope rather than
drifted. Nothing gets fixed in the directory, and the laptops stay broken.

Two smaller misses recur. One is writing the ticket's closing status as a word
instead of the coded value the system keeps, which quietly leaves the ticket
open. The other is waiting for a laptop's compliance flag to flip; it does not
flip on its own, and the job is to remove the causes and force the re-check.
