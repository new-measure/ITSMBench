# Fairness self-audit: task-n-1 (NO-RUNBOOK, re-grounded)

Audited against the four fairness gates in `NO-RUNBOOK-BRIEF.md`: (1) no seeded runbook/standard/KB;
(2) every scored requirement grounded by precedent / lineage / anomaly / universal practice; (3)
contested-judgment items without such grounding are DROPPED; (4) a cold oracle reaches the whole
scored set from only the change number + base URLs, inferring the standard, with zero hardcoded ids.

## Verdict: FAIR

Pristine 0/26 scored + 15/15 controls; cold oracle 0 readback mismatches → 26/26 scored + 15/15
controls; byte-stable seed. The oracle **inferred the completeness standard cold** from the CLOSED
precedent `CHG0029001` + the `sys_choice` value codes + Device42 IP/DNS/CMDB lineage + the
absent-device anomaly — with no runbook, no seed ids, and no grader constants.

## Runbook status

Nothing to remove: the seed never contained a decommission standard / consistency policy / KB /
runbook. Confirmed: `grep -iE "runbook|policy|standard|kb_knowledge|procedure|checklist" seed.json`
→ 0 matches. The change ticket states the GOAL only (retire this service + its subnet/VLAN, leave
the environment consistent, verify out-of-service) plus the host list — no system, surface, or
remediation class is enumerated.

## Per-assertion verdict table

| # | Assertion (test) | Verdict | Grounding |
|---|---|---|---|
| 1 | `test_db01_device_archived` | KEEP-via-universal | nothing decommissioned may remain operational; RELAX: accepts `archived=true` |
| 2 | `test_db01_ip_freed` | KEEP-via-lineage | host→IP allocation; "not still allocated"; RELAX: clear OR delete |
| 3 | `test_db01_stale_dns_removed` | KEEP-via-lineage | host→DNS A record; "not still resolvable" |
| 4 | `test_db01_cmdb_ci_retired` | KEEP-via-precedent | precedent RETIRES (not deletes) the CI; `sys_choice` maps Retired=7 |
| 5 | `test_app02_device_archived` | KEEP-via-universal | as #1 |
| 6 | `test_app02_primary_ip_freed` | KEEP-via-lineage | as #2 |
| 7 | `test_app02_secondary_mgmt_ip_freed` | KEEP-via-lineage | a SECOND IP record on the same device; found only by enumerating all IPs by device (precedent flags a mgmt-NIC case) |
| 8 | `test_app02_dns_removed` | KEEP-via-lineage | as #3 |
| 9 | `test_app02_cmdb_ci_retired` | KEEP-via-precedent | as #4 |
| 10 | `test_cache03_device_archived` | KEEP-via-universal | as #1 |
| 11 | `test_cache03_ip_freed` | KEEP-via-lineage | as #2 |
| 12 | `test_cache03_businessapp_element_removed` | KEEP-via-lineage | host→service-map element; precedent removes a service-map element on teardown |
| 13 | `test_cache03_cmdb_ci_retired` | KEEP-via-precedent | as #4 |
| 14 | `test_lb04_device_archived` | KEEP-via-universal | as #1 |
| 15 | `test_lb04_ip_freed` | KEEP-via-lineage | as #2; this is the subnet's last child IP (sequencing) |
| 16 | `test_lb04_cmdb_ci_retired` | KEEP-via-precedent | as #4 |
| 17 | `test_worker05_device_archived` | KEEP-via-universal | as #1 |
| 18 | `test_worker05_ip_freed` | KEEP-via-lineage | as #2 |
| 19 | `test_worker05_cmdb_ci_retired` | KEEP-via-precedent | as #4 |
| 20 | `test_orphan_dns_removed` | KEEP-via-anomaly | DNS resolves to a host ABSENT from inventory; precedent swept up an earlier change's dangling record |
| 21 | `test_orphan_ip_freed` | KEEP-via-anomaly | IP allocated to an ABSENT device; same |
| 22 | `test_orphan2_dns_removed` | KEEP-via-anomaly | second dangling DNS (host absent) — re-hardening |
| 23 | `test_orphan2_ip_freed` | KEEP-via-anomaly | second dangling IP (absent device) — re-hardening |
| 24 | `test_subnet_freed` | KEEP-via-lineage | enumerable child-IP set; free only once empty; precedent freed after the row emptied |
| 25 | `test_vlan_freed` | KEEP-via-lineage | subnet→VLAN pointer; freed with the subnet |
| 26 | `test_change_closed` | KEEP-as-universal | close the ticket when done; `sys_choice` maps Closed=3 |
| — | RESTRAINT `billing-report-06` (test_controls) | KEEP-via-anomaly (unscored guard) | self-evidently still live (fresh `last_seen`, CMDB operational, migrated to prod subnet); NOT scored for teardown, guarded by controls |

### DROPs

**None.** Every scored surface is a direct decommission consequence entailed by universal practice +
lineage + precedent + anomaly. The one item that could look like contested judgment — *retire vs.
delete* the CMDB CI — is not contested here: retiring (preserving audit history) is universal netops
practice, is exactly what the precedent demonstrates, and the value code is discoverable from
`sys_choice`; deleting the CI would be over-action. So it is KEEP-via-precedent, not a DROP.

### RELAX (valid alternative end-states accepted)

- IP "freed" = record deleted OR `available='yes'` with no device linkage (`test_outputs._ip_is_free`).
- Device "archived" accepts the `archived` flag in either boolean/string form.
- CI "retired" accepts install_status == the Retired code (7); the grader reads live state only.

## Precedent added (verbatim seed snippet)

Closed change `CHG0029001` (`state="3"`), `close_notes`:

> RIA-2 Lab subnet decommission - COMPLETE and verified consistent.
> Retired the RIA-2 Lab service and the hosts lab-web-01, lab-db-02 and lab-cache-03, then freed the
> RIA-2 Lab subnet (10.20.40.0/24) and VLAN 740.
> Work performed, per host:
> - Confirmed each host was genuinely out of service (no recent activity) before touching it.
> - Device42: archived the device; cleared every IP allocation it held - lab-db-02 had a separate
>   management-NIC address in addition to its primary, so both were released; deleted the host's DNS
>   A record; where a host was still wired into the RIA-2 Lab service map, removed its business-app
>   element.
> - ServiceNow: RETIRED the matching CMDB CI (install_status Retired / operational Non-Operational)
>   rather than deleting it, so the audit history is preserved.
> - Cleanup: while reconciling the subnet we found a DNS record and an allocated IP (lab-legacy-00,
>   10.20.40.250) that an older change (CHG-2022-0311) had left behind - the host had long since been
>   removed from inventory, yet the record still resolved and the address was still marked allocated.
>   Removed both.
> - Only once no host, IP, DNS record or business-app element remained on the row did we free the
>   subnet and its VLAN.
> Verified afterwards: nothing that was decommissioned is still reachable, allocated, resolvable or
> operational in the CMDB, and no dangling reference to a removed host remains. Closed.

A self-check asserts this text contains none of the current-target tokens (`billing-*`, `10.20.30`,
`RIA-1`, `CHG0030001`, `CHG-2023-0412`, `10.50.0`) and does contain the pattern signals
(`retire`, `free the subnet`, `dns`, `business-app element`, `out of service`, `long since been
removed`, `10.20.40.0/24`, `740`).

## Anomaly added (verbatim seed snippets)

Two dangling provenance references, each pointing at a device ABSENT from inventory:

> IP `{"id": 3007, "ip": "10.20.30.99", "device": "billing-legacy-00", "device_id": 2099,
> "available": "no", "created_by": "CHG-2023-0412"}`  (device 2099 not in `devices`)
> IP `{"id": 3009, "ip": "10.20.30.98", "device": "billing-legacy-01", "device_id": 2098,
> "available": "no", "created_by": "CHG-2023-0412"}`  (device 2098 not in `devices`)
> DNS `{"id": 4002, "name": "billing-legacy-00.rialto.example", "address": "10.20.30.99",
> "created_by": "CHG-2023-0412"}` and `{"id": 4006, "name": "billing-legacy-01.rialto.example",
> "address": "10.20.30.98", "created_by": "CHG-2023-0412"}`

Restraint anomaly (self-evident still-live): `billing-report-06` device `last_seen`
"2026-07-15T23:55:00Z" (vs decommission hosts at 2026-01-0x), CMDB CI operational + `sys_updated_on`
2026-07-15, and its IP on the prod-core subnet 6002 (10.50.0.20), not on the 6001 being freed.

## Lineage added

The two provenance orphans deepen the lineage layer (a stale reference is discoverable only by
enumerating IPs/DNS and matching against the live device set). The subnet's child-IP set (six host
IPs + two orphan IPs, all on subnet 6001) is enumerable, grounding the sequencing requirement.

## PROVIDER EDITS REQUIRING ECR REDEPLOY

**None.** No Device42 or ServiceNow handler was modified. All routes used by the grader / oracle /
reference solver (device archive, `clear_ip`, DNS/subnet/VLAN/element delete, `cmdb_ci_server` +
`change_request` PATCH, `sys_choice` list) are already correct and write→readback-consistent in the
current emulator image. All changes are seed-side + test-side + workspace-side only.

## Counts (before → after)

- Scored assertions: 24 → **26** (added `test_orphan2_dns_removed`, `test_orphan2_ip_freed`).
- Controls: 15 → **15** (unchanged; restraint IP relocated to prod subnet 6002).
- ServiceNow change_request: 1 → **2** (added closed precedent `CHG0029001`).
- Device42 ips: 9 → **10**; dns_records: 5 → **6** (added the second provenance orphan).
- Seed byte-stable; md5 `6613e5c29da21b076514d472d892861b`, identical across regenerations.

## Validation (emulator from source, PORT 8122, own shim, no Daytona)

Own shim `n1_emu_shim_8122.py` (hardcoded EMU_PORT=8122) imported explicitly; first probe confirmed
it hit MY emulator (8 devices, billing hosts). Only my own node PID was killed.

| Phase | Scored | Controls | Readback mismatches |
|---|---|---|---|
| PRISTINE | 0/26 (all fail) | 15/15 (all pass) | — |
| COLD ORACLE | 26/26 | 15/15 | **0** |
| reference_solve (secondary) | 26/26 | 15/15 | — |

Oracle log confirms: "inferred completeness standard COLD from precedent CHG0029001", codes derived
from `sys_choice` (Closed=3, Retired=7, Non-Operational=2), restraint spared, both dangling orphans
swept, subnet+VLAN freed after the row emptied.
