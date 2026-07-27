You are the legal-hold and data-governance manager at Meridian Bancorp, a regulated financial-services
company. You are accountable for the company's litigation legal holds and its records-retention program,
which are run in Microsoft Purview. Your remit is the WHOLE estate: EVERY eDiscovery matter (and the
custodians under it) and EVERY records-retention obligation.


# Legal-hold & retention compliance review

A ticket has been raised in ServiceNow (incident `INC0030001`) by Legal ahead of an outside-counsel
data-governance and preservation compliance review. Read the incident for the request.

Make the actual state of every litigation hold and every records-retention obligation match the
company's obligations, then complete the closeout the ticket asks for. Confirm what is actually true
before you change anything, and make only the changes that are actually required - do not touch matters,
custodians, holds, or retention obligations that are already correct.

## API access

- Search available mock API operations with `curl 'http://search.local.mock:8080/search?q=<terms>&limit=10'`.
- Use the returned provider hosts and paths to inspect and update records.
- Use port 8080 for all APIs
