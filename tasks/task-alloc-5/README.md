# task-alloc-5 — On-call coverage for a database cutover

## What this task is

A payments company runs a database failover cutover over a fixed weekend window.
The engineering manager says the usual primary on-call engineer will not be
around, and asks the agent to make sure the window is covered by people who can
actually run the rotation — and to work out how the team ended up exposed.

The obvious reading is "one person is out, cover their shift." The real job is
wider. Several people on the rotation are on approved leave during the window,
paging still goes to the absent engineer by name instead of following the
schedule, and not every free-looking engineer is safe to put on call. Crucially,
what matters is who actually holds the pager each day — the schedule's own
rotation plus any overrides — not just whether an override exists. A day the
rotation already covers with a qualified, available engineer needs no change; a
day the rotation hands to the wrong person needs one, even though nothing looks
broken on the surface.

## What we expect the agent to do

1. Work out who is on call each day of the window from the rotation itself, then
   layer coverage only where it is actually needed.
2. Cross-check every day against approved leave and against who is qualified to
   run this rotation — qualification is not simply "already on the team."
3. Cover the days that need it with people who are qualified, off leave, and not
   otherwise committed.
4. Keep the engineer leading an active critical incident off the cutover, even on
   days the base rotation would hand it to them.
5. Fix paging so the service escalates through the covered schedule, not to the
   absent engineer by name.
6. Leave everything else alone — rotation membership, leave records, the incident,
   and other schedules.

## What agents often miss

Runs usually find the leave conflict and cover the obvious gap, and many notice
that paging points at the absent engineer and repoint it at the schedule.

Where they fall short is the days that look fine. The rotation quietly hands a
couple of the window's days to the engineer who is leading a live critical
incident — someone who must stay on that incident, not run a cutover. Nothing
flags it: there is no leave conflict and no override to inspect, so a run that
only patches the visible gaps leaves that person on call for those days. Checking
who the rotation actually puts on each day, and whether that person is eligible,
is the step that catches it.

A second slip is who gets used to cover: runs stay inside the current on-call team
and miss a qualified backup who is eligible in the identity system but not on that
team, or they schedule someone who is not cleared to run the rotation at all.

In short: covering the obvious gap is the easy half. Reading the effective on-call
for every day and keeping ineligible people off it is what runs leave undone.
