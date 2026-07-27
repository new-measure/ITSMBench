# task-alloc-6 — Spare-laptop pool allocation (find the six that are really free)

## What this task is

A provisioning request asks for six laptops of one model, to be issued to a staging
bench for a new project. The asset system shows none of that model free: every unit is
either reserved, deployed, or sitting in pending repair. The pool looks empty.

It is not. Six units can be safely returned to stock, and they come from two different
causes. Some are holds left over from a project that was cancelled months ago — the
requests were cancelled, but nobody ever released the hardware. Others came back from
break-fix, passed repair and were cleared for redeployment, but were never flipped out
of their repair status.

Mixed in with those are units that look the same but must not be touched: one that is
on hold for a cancelled project yet has an open defect case against it, one that is
still waiting on parts, and several holds that belong to other teams whose requests
are still live. The asset system's own status label does not tell these apart. The
request records and the repair tickets do.

## What we expect the agent to do

1. Find the provisioning request itself and read what it actually asks for: how many,
   which model, and which destination.
2. List every unit of that model and work out, for each one, why it is unavailable.
3. Check the request records to see which holds belong to cancelled work and which
   belong to work that is still going ahead.
4. Check the repair and defect tickets to see which units have a real open fault and
   which have already been repaired and cleared.
5. Free and issue exactly the six that both checks agree are safe, including any unit
   that is still checked out somewhere under a cancelled request.
6. Leave the faulty unit, the unit awaiting parts, and other teams' live holds exactly
   where they are.
7. Close out the provisioning request itself, so the work is recorded as fulfilled and
   not just physically done.

## What agents often miss

The core miss is relying on one source of truth. Both checks are needed, and either one
alone produces a confident, wrong answer.

Runs that never find the request records cannot tell a cancelled hold from a live one.
They fall back on age or priority, decide another team's hold is "stale", and take
laptops that were promised elsewhere — sometimes cancelling that team's request to do
it. Runs that never read the repair tickets do the opposite: they trust the status
label, issue a laptop that has an open defect case against it, and never notice the two
repaired units that only look broken.

The single most-missed unit is the one that is checked out to a field office under a
cancelled request. Runs read "checked out" as "in use" and stop there, without asking
why it went out or whether that reason still holds — while other units in exactly the
same state must be left alone, because their reason is still valid.

The last common gap is stopping at the hardware. Runs move the laptops, report the job
as done in their summary, and leave the request record itself still open and waiting.
