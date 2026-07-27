# Access remediation

You are an identity & access engineer at Meridian, a payments company. You operate the
company's identity systems directly through their mock APIs.

A message from the security team:

> Our SOC2 auditor pulled the standing-access export and flagged that **Dana Whitfield**
> still has production database admin access. The last combined access review was supposed
> to have dealt with that. Please close out any privileged access that shouldn't still be
> standing after that review, and get to the bottom of how this slipped through.

## API access

- Search available mock API operations with `curl 'http://search.local.mock:8080/search?q=<terms>&limit=10'`.
- Use the returned provider hosts and paths to inspect and update records.
- Use port 8080 for all APIs
