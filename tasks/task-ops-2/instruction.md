You are the **problem manager** on duty at Meridian Pay, a digital-payments company. Everything runs
through one ServiceNow system of record: incidents, problems, changes, the CMDB (configuration items
with their support groups, business criticality, and dependency relationships), the user/support
groups, and change records.

# Drive the checkout problem to root cause

Monitoring has opened problem `PRB0041001` — customers are unable to complete checkout. The affected
service named on the problem is healthy on its own; whatever broke it is somewhere in what it **depends
on**, and the outage has rippled out to everything that **depends on it**. Your job is to take THIS
problem all the way to a correct, complete root-cause analysis. Do the following:

1. **Find the true root cause.** Work out what actually broke checkout. The affected service's own
   configuration item is not where the fault is — trace the service's dependencies and find the change
   that lines up with when the outage began. Be careful: there is a recent change on the affected
   service itself that looks tempting but does not line up with the outage, and it is not the cause.
   Point the problem's investigation at the change that truly caused it, and don't attribute it to a
   change that doesn't fit.

2. **Link the full incident footprint.** This outage did not only raise incidents on the affected
   service — it hit every service that depends on it, too. Find **all** the incidents that are this same
   outage across the affected service and its downstream dependants, attach each of them to
   `PRB0041001`, and close them as duplicates. Work out which incidents truly belong to this problem's
   footprint — do not sweep in tickets that merely look similar but are a different, unrelated issue, or
   that belong to a different problem, or that are old issues from before this outage began.

3. **Move the problem forward.** Once you have the cause and the footprint, advance the problem out of
   its initial state and record it as a known error.

Confirm what is actually in place before you change anything, and leave every record consistent. The
queue is large, so investigate efficiently with server-side queries and the CMDB dependency graph rather
than reading everything.

## API access

- Search available mock API operations with `curl 'http://search.local.mock:8080/search?q=<terms>&limit=10'`.
- Use the returned provider hosts and paths to inspect and update records.
- Use port 8080 for all APIs
