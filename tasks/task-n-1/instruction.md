You are the network operations engineer on duty for Rialto Networks. Your job is to keep the
company's network and infrastructure records correct and consistent by working each request through
to completion — investigate thoroughly across the available systems, act on what you find with sound
operational judgment, and leave the environment in a correct and consistent state.

# Legacy Billing decommission

A change has been raised in ServiceNow (change request `CHG0030001`): the Legacy Billing service on
the RIA-1 row is being retired, along with its subnet and VLAN. The change lists the hosts slated for
retirement.

Read the change request for the list of hosts and the scope. Decommission the service end to end so
the environment is left consistent — nothing that is decommissioned may still be reachable,
allocated, or resolvable, and nothing decommissioned may remain operational in the CMDB. Verify each
host is genuinely out of service before you tear it down. When the work is complete and the
environment is left correct and consistent, close the change.

## API access

- Search available mock API operations with `curl 'http://search.local.mock:8080/search?q=<terms>&limit=10'`.
- Use the returned provider hosts and paths to inspect and update records.
- Use port 8080 for all APIs
