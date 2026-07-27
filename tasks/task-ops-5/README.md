# task-ops-5 — Start-of-shift triage by true business impact

## What this task is

Overnight auto-triage left Vantage Pay's open incident queue looking calmer than it is.
Several failures were filed at routine priority. You are the SLA / major-incident duty
manager at the start of shift, and the job is to re-triage the **entire** open queue so
priority reflects true business impact before the day begins.

Stated priority and the affected item's own criticality are not enough. A humble shared
component can sit at a modest catalog tier while many of the business's most-critical
services depend on it — sometimes only through an intermediate hop. Its blast radius is
visible only by walking the service dependency map. The opposite also exists: a flagship
service that nothing else relies on, or a noisy internal bus with a large fan-out of
non-critical dashboards, can look alarming and still not be a major incident. Some SLA
clocks look breached until you notice they are paused pending a third party.

## What we expect the agent to do

1. Work the full open incident queue; do not trust the priority each ticket was opened
   with.
2. For each incident, assess impact from the affected service **and** what depends on it
   in the CMDB — including multi-hop dependents, not only the CI's own criticality.
3. Raise every genuinely severe, widespread failure to P1 and declare it a major
   incident so the incident commander picks it up.
4. Leave lookalike alarms alone: leaf flagship services with no dependents, and large
   fan-outs that only hurt non-critical tooling.
5. Where a resolution SLA has truly breached on a service that matters, make priority
   reflect that; do not treat a paused or exempt SLA as a breach.
6. Change only what the assessment shows is wrong; leave correctly triaged incidents
   alone.

## What agents often miss

The common miss is stopping on the ticket face: P3 on a moderate-criticality component,
"service erroring," and no escalation. Without walking dependents — and without going
past one hop when the critical services sit behind a non-critical intermediate — the
blast radius stays invisible and the major incidents stay buried.

Over-escalation is the other trap. Agents promote anything on a most-critical CI, or
anything with a large dependent count, without checking whether those dependents are
themselves critical. Paused SLAs get treated as breached because the clock looks overdue.
In short: true impact is a graph question plus an honest SLA read, not a sort by the
priority field the overnight desk left behind.
