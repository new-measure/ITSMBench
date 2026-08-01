# task-ops-5 — Start-of-shift triage by true business impact

## What this task is

Overnight auto-triage made Vantage Pay's open incident queue look less serious than it is.
Several failures were assigned routine priority. You are the SLA / major-incident duty
manager at the start of the shift. You must re-triage the **entire** open queue before
the day begins. Each priority must reflect the true business impact.

Do not assess an incident using only its stated priority or the criticality of the affected
item. A shared component can have a modest catalog tier while supporting many of the
business's most-critical services. These services may depend on it through an intermediate
service. You must follow the service dependency map to find the full impact. The reverse
can also happen. A flagship service may have no dependents. An internal bus may have many
dependents that are only non-critical dashboards. These incidents may look serious but
still not be major incidents. Some SLA clocks may look breached even though they are
paused while waiting for a third party.

## What we expect the agent to do

1. Review the full open incident queue. Do not trust the priority assigned when each
   ticket was opened.
2. For each incident, assess the affected service and every service that depends on it
   in the CMDB. Include multi-hop dependents. Do not consider only the CI's own
   criticality.
3. Raise every failure that is truly severe and widespread to P1. Declare it a major
   incident so the incident commander picks it up.
4. Do not change alarms that only look similar. This includes leaf flagship services with no
   dependents and services with many dependents that only affect non-critical tooling.
5. If a resolution SLA has truly breached on an important service, update the priority
   to reflect that breach. Do not treat a paused or exempt SLA as breached.
6. Change only incidents that the assessment shows are incorrectly triaged. Leave
   correctly triaged incidents unchanged.

## What agents often miss

A common mistake is to assess only the ticket details. An incident may be P3 on a
moderate-criticality component, report that the service is erroring, and show no
escalation. You must still follow its dependents. You must also go beyond one hop when
critical services depend on it through a non-critical intermediate service. Otherwise,
you will not see the full impact, and major incidents will remain at a low priority.

Another mistake is over-escalation. Do not promote every incident on a most-critical CI.
Do not promote every incident with many dependents. Check whether those dependents are
critical. Do not treat paused SLAs as breached just because the clock looks overdue.
True impact requires checking the dependency graph and reading the SLA status correctly.
Do not base it only on the priority assigned by the overnight desk.
