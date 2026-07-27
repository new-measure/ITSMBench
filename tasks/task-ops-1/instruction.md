You are the service-desk **duty manager (shift lead)** at Northwind Pay, and your shift is ending.
Everything runs through one ServiceNow system of record: incidents, problems, changes, the CMDB
(configuration items with their support groups and business criticality), the user/support groups, and
the SLA records.

# End-of-shift handoff — leave the WHOLE board coherent

It was a rough overnight shift and the incident queue is a mess. Before you hand the desk over to the next
shift, your job is to leave the **entire board** in a correct, coherent state — not only the headline
outage. Work the whole open queue and do all three of the following:

1. **Consolidate the major incident.** Monitoring has opened problem `PRB0040100` for the emerging major
   issue. Attach the incidents that are the SAME underlying outage to that problem and close them as
   duplicates. Work out which tickets truly belong to it — the desk's tagging is inconsistent and some
   tickets are mislabeled — and be careful not to sweep in tickets that merely look similar but are a
   different issue. Point the problem's investigation at what actually caused the outage, and move the
   problem forward from its initial state.

2. **Fix routing across the board.** Go through the open queue and make sure **every** ticket is with the
   team that actually owns its affected service — the support group of the ticket's affected configuration
   item — rather than wherever the desk's keyword auto-assignment happened to drop it. Do not assume the
   current assignment is correct; check each ticket's affected service and re-route the ones that are with
   the wrong team.

3. **Fix priorities across the board.** Make sure **every** open ticket's priority reflects real business
   impact and current service commitments. In particular, an incident on a business-critical service whose
   resolution SLA has already breached must not be left sitting at a routine priority.

Confirm what is actually in place before you change anything, and leave every record consistent. The queue
is large, so investigate efficiently with server-side queries rather than reading everything.

## API access

- Search available mock API operations with `curl 'http://search.local.mock:8080/search?q=<terms>&limit=10'`.
- Use the returned provider hosts and paths to inspect and update records.
- Use port 8080 for all APIs
