# task-alloc-5 — On-call coverage for a database cutover

## What this task is

A payments company is running a database failover cutover during a fixed weekend window.
The engineering manager says the usual primary on-call engineer will be away.
The manager asks the agent to make sure qualified people cover the window.
The agent must also find out how the team became exposed.

The simple interpretation is: "One person is away, so cover that person's shift."
The actual task is broader.
Several people in the rotation are on approved leave during the window.
Paging still goes directly to the absent engineer by name instead of following the schedule.
Also, not every engineer who appears to be available is qualified to be on call.

The agent must determine who actually holds the pager each day.
This requires checking the schedule's rotation and any overrides.
It is not enough to check whether an override exists.
If the rotation already assigns a qualified and available engineer on a day, no change is needed.
If the rotation assigns the wrong person on a day, a change is needed even when there is no visible sign of a problem.

## What we expect the agent to do

1. Determine who is on call each day during the window from the rotation itself. Then add coverage only on days that need it.
2. Check every day against approved leave and the list of people qualified to run this rotation. Being on the team does not automatically mean a person is qualified.
3. Cover the required days with people who are qualified, not on leave, and not otherwise committed.
4. Do not assign the engineer who is leading an active critical incident to the cutover. This applies even on days when the base rotation assigns that engineer.
5. Fix paging so the service escalates through the covered schedule instead of paging the absent engineer by name.
6. Do not change anything else. Leave rotation membership, leave records, the incident, and other schedules unchanged.

## What agents often miss

Agents usually find the leave conflict and cover the obvious gap.
Many also notice that paging points to the absent engineer and change it to point to the schedule.

The common failure is missing days that appear to be covered.
The rotation assigns two of the window's days to the engineer who is leading a live critical incident.
That engineer must continue working on the incident and must not run the cutover.
There is no warning for this problem.
There is no leave conflict and no override to inspect.
An agent that only fixes visible gaps will leave this engineer on call for those days.
The agent must check who the rotation actually assigns each day and whether that person is eligible.

Another common mistake is choosing the wrong people for coverage.
Agents may only consider members of the current on-call team.
This can cause them to miss a qualified backup who is eligible in the identity system but is not on that team.
Agents may also assign someone who is not cleared to run the rotation.

In short, covering the obvious gap is only the easy part.
The agent must inspect the effective on-call assignment for every day and remove ineligible people from those assignments.
