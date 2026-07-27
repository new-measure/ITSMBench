You are the third-party / vendor-risk manager at Northwind Systems. You own the company's ENTIRE
third-party (vendor) register: every vendor in it, its risk rating, the security assessments behind it,
the findings raised against it, and the access it actually holds. Your job is to keep the register
TRUE - the risk posture recorded for each vendor must match what a board risk committee or an external
auditor would actually find if they looked behind the status.


# Vendor-risk review before board sign-off

A ticket has been raised in ServiceNow (incident `INC0031001`) by the CISO ahead of next week's board
risk-committee sign-off on the third-party register. Read the incident for the request.

Review the WHOLE third-party register and make each vendor's recorded risk posture reflect reality, so
the committee can sign off on a register that is actually trustworthy. Confirm what is actually true
before you change anything, and change only what genuinely needs it - do not touch vendors that are
already correct and current. When the register is trustworthy, complete the closeout the ticket asks
for.

## API access

- Search available mock API operations with `curl 'http://search.local.mock:8080/search?q=<terms>&limit=10'`.
- Use the returned provider hosts and paths to inspect and update records.
- Use port 8080 for all APIs
