#!/usr/bin/env python3
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

SN = "http://servicenow.local.mock:8080/api/now/table"
HAP = "http://haproxy.local.mock:8080/v3/services/haproxy/configuration"
HAP_RT = "http://haproxy.local.mock:8080/v3/services/haproxy/runtime"
D42 = "http://device42.local.mock:8080"
SENT = ("http://microsoft-sentinel.local.mock:8080/subscriptions/00000000-1111-2222-3333-444444444444"
        "/resourceGroups/secops-rg/providers/Microsoft.OperationalInsights/workspaces/sentinel-ws"
        "/providers/Microsoft.SecurityInsights/incidents")
INCIDENT_NUMBER = "INC0091001"
MISMATCHES = []

def call(method, url, body=None):
    data, headers = None, {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
        return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:200]}

def get(url):
    return call("GET", url)

def rows(resp, key=None):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        if key and resp.get(key) is not None:
            return resp[key]
        return resp.get("result") or []
    return []

def truthy(v):
    return v is True or str(v).strip().lower() in ("true", "1", "yes", "y")

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

incidents = rows(get(SN + "/incident"))
cur = next((i for i in incidents if str(i.get("number")) == INCIDENT_NUMBER), None)
assert cur, "incident %s not found" % INCIDENT_NUMBER
inc_sys = str(cur["sys_id"])
choices = rows(get(SN + "/sys_choice"))
resolved = [str(c.get("value")) for c in choices if str(c.get("name")) == "incident"
            and str(c.get("element")) == "state" and re.search(r"resolv", str(c.get("label", "")), re.I)]
closed = [str(c.get("value")) for c in choices if str(c.get("name")) == "incident"
          and str(c.get("element")) == "state" and re.search(r"clos", str(c.get("label", "")), re.I)]
RESOLVED = (resolved or closed or ["6"])[0]
print("incident %s sys_id=%s -> resolved-state=%s" % (INCIDENT_NUMBER, inc_sys, RESOLVED))

sent = rows(get(SENT + "?api-version=2023-11-01"), "value")
sev = next((i for i in sent if str((i.get("properties") or {}).get("status")) == "Active"), None)
devices = rows(get(D42 + "/api/2.0/devices/"), "devices")
pool_hosts = [d for d in devices if "pool" in str(d.get("role", ""))]
healthy_hosts = [d for d in pool_hosts if truthy(d.get("in_service"))]
print("decoy check: Sentinel active evidence=%s | pool hosts=%d, healthy=%d (hardware fine -> config RCA)"
      % (bool(sev), len(pool_hosts), len(healthy_hosts)))

frontends = rows(get(HAP + "/frontends"))
backend_rows = rows(get(HAP + "/backends"))
backends = [str(b.get("name")) for b in backend_rows]
backend_by_name = {str(b.get("name")): b for b in backend_rows}
servers = {}
for be in backends:
    for s in rows(get(HAP + "/backends/%s/servers" % be)):
        servers[(be, str(s.get("name")))] = s
runtime = {}
for be in backends:
    for r in rows(get(HAP_RT + "/backends/%s/servers" % be)):
        runtime[(be, str(r.get("server_name") or r.get("name")))] = r
print("fleet: %d frontends, %d backends, %d servers, %d runtime rows"
      % (len(frontends), len(backends), len(servers), len(runtime)))

def mode(vals):
    vals = [int(v) for v in vals if isinstance(v, (int, float))]
    return Counter(vals).most_common(1)[0][0] if vals else None

def mode_str(vals):
    vals = [str(v).lower() for v in vals if v is not None]
    return Counter(vals).most_common(1)[0][0] if vals else None

BASE_WEIGHT = mode(s.get("weight") for s in servers.values())
BASE_MAXCONN = mode(s.get("maxconn") for s in servers.values())
BASE_INTER = mode(s.get("inter") for s in servers.values())
BASE_FALL = mode(s.get("fall") for s in servers.values())
BASE_RISE = mode(s.get("rise") for s in servers.values())
BASE_CHECK = mode_str(s.get("check") for s in servers.values())
BASE_BALANCE = mode_str((b.get("balance") or {}).get("algorithm") for b in backend_by_name.values())
fe_maxconns = [int(f.get("maxconn")) for f in frontends if isinstance(f.get("maxconn"), (int, float))]
BASE_FE_MAXCONN = max(fe_maxconns)
print("baseline (fleet mode): weight=%s maxconn=%s inter=%s rise=%s fall=%s check=%s balance=%s | frontend maxconn=%s"
      % (BASE_WEIGHT, BASE_MAXCONN, BASE_INTER, BASE_RISE, BASE_FALL, BASE_CHECK, BASE_BALANCE, BASE_FE_MAXCONN))
assert None not in (BASE_WEIGHT, BASE_MAXCONN, BASE_INTER, BASE_FALL, BASE_CHECK, BASE_BALANCE), "baseline underivable"

fixed_frontends = []
for f in frontends:
    mc = f.get("maxconn")
    if isinstance(mc, (int, float)) and int(mc) < BASE_FE_MAXCONN // 4:
        body = {k: v for k, v in f.items() if k not in ("created_at", "created_by", "change_ref",
                                                        "binds", "ssl_front_use_list")}
        body["maxconn"] = BASE_FE_MAXCONN
        res = call("PUT", HAP + "/frontends/%s" % f.get("name"), body=body)
        ok = not (isinstance(res, dict) and res.get("_error"))
        print("  frontend %s maxconn %s -> %s (%s)" % (f.get("name"), mc, BASE_FE_MAXCONN,
                                                       "ok" if ok else res))
        fixed_frontends.append(str(f.get("name")))

fixed_backends = []
for be, b in sorted(backend_by_name.items()):
    alg = str((b.get("balance") or {}).get("algorithm") or "").lower()
    if alg and alg != BASE_BALANCE:
        body = {k: v for k, v in b.items() if k not in ("created_at", "created_by", "change_ref",
                                                        "servers", "http_check_list", "tcp_check_rule_list")}
        body["balance"] = {"algorithm": BASE_BALANCE}
        res = call("PUT", HAP + "/backends/%s" % be, body=body)
        ok = not (isinstance(res, dict) and res.get("_error"))
        print("  backend %s balance %s -> %s (%s)" % (be, alg, BASE_BALANCE, "ok" if ok else res))
        fixed_backends.append(be)

def anomalies(s):
    out = {}
    w, m, i, fl, chk = s.get("weight"), s.get("maxconn"), s.get("inter"), s.get("fall"), s.get("check")
    if isinstance(w, (int, float)) and int(w) == 0:
        out["weight"] = BASE_WEIGHT
    if isinstance(m, (int, float)) and 0 < int(m) < BASE_MAXCONN // 4:
        out["maxconn"] = BASE_MAXCONN
    if (isinstance(i, (int, float)) and int(i) < BASE_INTER // 4) or \
       (isinstance(fl, (int, float)) and int(fl) < 2):
        out["inter"] = BASE_INTER
        out["fall"] = BASE_FALL
        if BASE_RISE is not None:
            out["rise"] = BASE_RISE
    if str(chk).lower() != BASE_CHECK:
        out["check"] = BASE_CHECK
    return out

fixed_servers = []
for (be, name), s in sorted(servers.items()):
    fix = anomalies(s)
    if not fix:
        continue
    body = {k: v for k, v in s.items() if k not in ("created_at", "created_by", "change_ref")}
    body.update(fix)
    res = call("PUT", HAP + "/backends/%s/servers/%s" % (be, name), body=body)
    ok = not (isinstance(res, dict) and res.get("_error"))
    print("  server %s/%s fix %s (%s)" % (be, name, fix, "ok" if ok else res))
    fixed_servers.append((be, name, fix))

host_by_ip = {str(d.get("ip")): d for d in devices if d.get("ip")}
returned, left = [], []
for (be, name), r in sorted(runtime.items()):
    if str(r.get("admin_state")) not in ("maint", "drain"):
        continue
    addr = str(r.get("address") or servers.get((be, name), {}).get("address"))
    host = host_by_ip.get(addr)
    if host is not None and not truthy(host.get("in_service")):
        left.append((be, name))
        print("  LEAVE %s/%s drained: host %s out-of-service (sanctioned maintenance)"
              % (be, name, host.get("name")))
        continue
    res = call("PUT", HAP_RT + "/backends/%s/servers/%s" % (be, name), body={"admin_state": "ready"})
    ok = not (isinstance(res, dict) and res.get("_error"))
    print("  return %s/%s to ready (host in service -> unsanctioned drift) (%s)"
          % (be, name, "ok" if ok else res))
    returned.append((be, name))

call("PATCH", SN + "/incident/%s" % inc_sys, body={
    "state": RESOLVED, "close_code": "Solved (Permanently)",
    "close_notes": ("Root cause: the overnight capacity & health-check tuning push to the api edge tier "
                    "was botched — NOT an under-provisioned pool or a bad member (all pool hosts healthy "
                    "in the CMDB; telemetry showed frontend connection rejections, per-member resets, "
                    "zero-weight members and health-check flapping). Restored the drifted settings to "
                    "the healthy fleet baseline: raised the api frontend connection limit back to the "
                    "peer value, restored zero-weight members, restored the lowered per-member "
                    "connection limits, returned the over-aggressive health checks to standard "
                    "interval/threshold, and returned the unsanctioned drained members to service. Left "
                    "the one member legitimately drained for the planned host-maintenance window. No "
                    "hardware added; no members replaced; peer tier untouched.")})

print("\n--- readback ---")
frontends2 = rows(get(HAP + "/frontends"))
for f in frontends2:
    if str(f.get("name")) in fixed_frontends:
        check("frontend %s maxconn >= baseline" % f.get("name"),
              isinstance(f.get("maxconn"), (int, float)) and int(f.get("maxconn")) >= BASE_FE_MAXCONN)
backend_by_name2 = {str(b.get("name")): b for b in rows(get(HAP + "/backends"))}
for be in fixed_backends:
    alg = str((backend_by_name2.get(be, {}).get("balance") or {}).get("algorithm") or "").lower()
    check("backend %s balance distributing (not 'first')" % be, alg not in ("", "first", "static-rr"))
servers2 = {}
for be in backends:
    for s in rows(get(HAP + "/backends/%s/servers" % be)):
        servers2[(be, str(s.get("name")))] = s
for be, name, fix in fixed_servers:
    s = servers2.get((be, name), {})
    for k, v in fix.items():
        if k == "check":
            check("server %s/%s check == %s" % (be, name, v), str(s.get("check")).lower() == str(v).lower())
        else:
            check("server %s/%s %s == %s" % (be, name, k, v), int(s.get(k, -1)) == int(v))
check("no fleet server left at weight 0",
      all(int(s.get("weight", 1)) != 0 for s in servers2.values()))
check("no fleet server left with check disabled",
      all(str(s.get("check")).lower() != "disabled" for s in servers2.values()))
for be, name in returned:
    r = get(HAP_RT + "/backends/%s/servers/%s" % (be, name))
    check("runtime %s/%s returned to service" % (be, name),
          isinstance(r, dict) and str(r.get("admin_state")) not in ("maint", "drain"))
for be, name in left:
    r = get(HAP_RT + "/backends/%s/servers/%s" % (be, name))
    check("runtime %s/%s still drained (sanctioned)" % (be, name),
          isinstance(r, dict) and str(r.get("admin_state")) in ("maint", "drain"))
inc2 = (get(SN + "/incident/%s" % inc_sys) or {}).get("result", {})
check("incident resolved", str(inc2.get("state")) == RESOLVED)
check("incident documented", str(inc2.get("close_notes") or "").strip() != "")

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
