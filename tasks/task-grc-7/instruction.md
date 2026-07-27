You are the vulnerability-management lead at Acme Cloud, accountable for the accuracy of the company's
vulnerability register ahead of a SOC 2 CC7.1 review. Your remit is the WHOLE vulnerability program: what
the scanner actually reports on each host, what the ServiceNow register says about it, the SLA handling,
and the risk-acceptance decisions behind it.

# Vulnerability register reconciliation (SOC 2 CC7.1)

A ticket has been raised in ServiceNow (incident `INC0030001`) by the security team. Read the incident
for the request.

Reconcile the vulnerability register to reality across the whole program, then complete the closeout the
ticket asks for. Confirm what is actually true before you change anything, and make only the changes that
are actually required - do not touch findings, tickets, or records that are already correct or
legitimately accepted. Remediation of the underlying vulnerabilities (patching) is handled by the
platform teams and is out of scope; your job is accurate disposition and hygiene in the systems of
record.

## API access

- Search available mock API operations with `curl 'http://search.local.mock:8080/search?q=<terms>&limit=10'`.
- Use the returned provider hosts and paths to inspect and update records.
- Use port 8080 for all APIs
