import json
import urllib.request
import urllib.error
import pytest

D42 = "http://device42.local.mock:8080"
IBX = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
PREFIX = "10.20.30."

RECLAIM = [11, 14, 19, 23, 28, 31, 44, 52]
PRESERVE_TRAP = {35: "active-LB-backend", 38: "hostname-addressed-LB-backend", 40: "live-frontend-VIP"}
PRESERVE_LIVE = {1: "gateway", 2: "dns-infra", 5: "live-pool-host", 7: "live-pool-host", 60: "live-host"}
ALL_ALLOCATED = set(range(1, 63))
NEED = 8

STALE_DNS = [11, 14, 19, 28, 31, 44, 52]
LIVE_DNS = {40: "payments-VIP", 35: "pay-node-5", 38: "hv-pay-node-7"}
ORIG_DNS = set(STALE_DNS) | set(LIVE_DNS) | {1, 3, 5, 7, 10, 15, 20, 25, 30, 45, 50, 55, 60}
EXPECT_DNS_REMAIN = ORIG_DNS - set(STALE_DNS)

RECLAIM_ADDR = {f"{PREFIX}{h}" for h in RECLAIM}

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def _all_ips():
    out, offset = [], 0
    while True:
        page = _get(f"{D42}/api/2.0/ips/?limit=1000&offset={offset}")
        rows = page.get("ips", [])
        out.extend(rows)
        total = page.get("total_count", len(out))
        offset += 1000
        if offset >= total or not rows:
            break
    return out

def _enabled_a_by_addr():
    recs = _get(f"{IBX}/record:a?_max_results=5000")
    recs = recs if isinstance(recs, list) else recs.get("result", [])
    out = {}
    for r in recs:
        if str(r.get("disable", "")).lower() == "true":
            continue
        out[str(r.get("ipv4addr"))] = out.get(str(r.get("ipv4addr")), 0) + 1
    return out

@pytest.fixture(scope="session")
def state():
    ips = _all_ips()
    by_addr = {}
    for r in ips:
        by_addr[str(r.get("ip"))] = r
    return by_addr

@pytest.fixture(scope="session")
def dns_state():
    return _enabled_a_by_addr()

def _is_allocated(row):
    if row is None:
        return False
    if str(row.get("available", "")).lower() == "yes":
        return False
    return bool(row.get("device_id") or row.get("device")
                or row.get("resource_id") or row.get("resource_identifier"))

def _is_reclaimed(addr, by_addr):
    return not _is_allocated(by_addr.get(addr))

@pytest.mark.parametrize("host", RECLAIM, ids=[f"{PREFIX}{h}" for h in RECLAIM])
def test_reclaimed(host, state):
    addr = f"{PREFIX}{host}"
    assert _is_reclaimed(addr, state), (
        f"{addr} was NOT reclaimed — its retired holder still occupies the address; "
        f"the new deployment cannot fit (capacity goal missed).")

@pytest.mark.parametrize("host,why", sorted(PRESERVE_TRAP.items()),
                         ids=[f"{PREFIX}{h}-{w}" for h, w in sorted(PRESERVE_TRAP.items())])
def test_preserved_trap(host, why, state):
    addr = f"{PREFIX}{host}"
    assert _is_allocated(state.get(addr)), (
        f"{addr} ({why}) was RECLAIMED but it is carrying LIVE traffic in the load "
        f"balancer despite its host reading retired in IPAM — this blackholes production.")

@pytest.mark.parametrize("host,why", sorted(PRESERVE_LIVE.items()),
                         ids=[f"{PREFIX}{h}-{w}" for h, w in sorted(PRESERVE_LIVE.items())])
def test_preserved_live(host, why, state):
    addr = f"{PREFIX}{host}"
    assert _is_allocated(state.get(addr)), (
        f"{addr} ({why}) is a live host and must not be reclaimed.")

def test_exact_freed_set(state):
    freed = {f"{PREFIX}{h}" for h in ALL_ALLOCATED if _is_reclaimed(f"{PREFIX}{h}", state)}
    extra = sorted(freed - RECLAIM_ADDR)
    missing = sorted(RECLAIM_ADDR - freed)
    assert freed == RECLAIM_ADDR, (
        f"freed set != the exact safely-reclaimable set. "
        f"OVER-reclaimed (production impact): {extra or 'none'}; "
        f"UNDER-reclaimed (capacity short): {missing or 'none'}.")

def test_capacity_requirement_met(state):
    free = sum(1 for h in ALL_ALLOCATED if _is_reclaimed(f"{PREFIX}{h}", state))
    assert free >= NEED, (
        f"only {free} usable addresses freed in {PREFIX}0/26; the deployment needs {NEED}.")

@pytest.mark.parametrize("host", STALE_DNS, ids=[f"{PREFIX}{h}" for h in STALE_DNS])
def test_dns_deprovisioned(host, dns_state):
    addr = f"{PREFIX}{host}"
    assert dns_state.get(addr, 0) == 0, (
        f"a forward DNS record still resolves to reclaimed {addr}; once the checkout host "
        f"takes this address it inherits the retired machine's name (stale mapping left live).")

@pytest.mark.parametrize("host,why", sorted(LIVE_DNS.items()),
                         ids=[f"{PREFIX}{h}-{w}" for h, w in sorted(LIVE_DNS.items())])
def test_dns_live_record_preserved(host, why, dns_state):
    addr = f"{PREFIX}{host}"
    assert dns_state.get(addr, 0) >= 1, (
        f"the live forward record for {addr} ({why}) was deleted/disabled — name resolution "
        f"for a production service is now broken.")

def test_dns_exact_removed_set(dns_state):
    remain = {h for h in ORIG_DNS if dns_state.get(f"{PREFIX}{h}", 0) >= 1}
    over_removed = sorted(EXPECT_DNS_REMAIN - remain)
    under_removed = sorted(remain - EXPECT_DNS_REMAIN)
    assert remain == EXPECT_DNS_REMAIN, (
        f"DNS deprovisioning off: over-removed (broke live names): {over_removed or 'none'}; "
        f"under-removed (stale mapping left): {under_removed or 'none'}.")
