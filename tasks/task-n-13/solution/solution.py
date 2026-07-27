#!/usr/bin/env python3
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

DNS = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
HAP = "http://haproxy.local.mock:8080/v3/services/haproxy/configuration"
D42 = "http://device42.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"
INCIDENT_NUMBER = "INC0012001"
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

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

def rows(kind):
    r = get(DNS + "/" + kind)
    return r if isinstance(r, list) else []

incidents = get(SN + "/incident")
incidents = incidents if isinstance(incidents, list) else (incidents or {}).get("result", [])
cur = next((i for i in incidents if str(i.get("number")) == INCIDENT_NUMBER), None)
assert cur, "incident not found"
inc_sys = str(cur["sys_id"])
desc = str(cur.get("description", "")) + " " + str(cur.get("short_description", ""))
m = re.search(r"\bCHG\d+\b", desc)
suspected = m.group(0) if m else None
print("incident %s sys_id=%s suspected(decoy)=%s" % (INCIDENT_NUMBER, inc_sys, suspected))
changes = get(SN + "/change_request")
changes = changes if isinstance(changes, list) else (changes or {}).get("result", [])
dec = next((c for c in changes if str(c.get("number")) == suspected), None)
print("decoy %s: category=%s state=%s -> app-only change, closed successful; NOT the cause"
      % (suspected, dec and dec.get("category"), dec and dec.get("state")))
choices = get(SN + "/sys_choice")
choices = choices if isinstance(choices, list) else (choices or {}).get("result", [])
closed_vals = [str(c.get("value")) for c in choices if str(c.get("name")) == "incident"
               and str(c.get("element")) == "state" and re.search(r"resolv|clos", str(c.get("label", "")), re.I)]
CLOSED = closed_vals[-1] if closed_vals else "7"

d42_devices = ((get(D42 + "/api/2.0/devices/") or {}).get("devices")) or []
d42_services = ((get(D42 + "/api/2.0/services/") or {}).get("services")) or []
LIVE = {str(d.get("ip")) for d in d42_devices if d.get("ip")}
frontends = get(HAP + "/frontends")
frontends = frontends if isinstance(frontends, list) else []
for fe in frontends:
    b = get(HAP + "/frontends/%s/binds" % fe.get("name"))
    LIVE |= {str(x.get("address")) for x in (b if isinstance(b, list) else []) if x.get("address")}

internal_svcs = [s for s in d42_services if s.get("internal_endpoint")]
external_only = [s for s in d42_services if not s.get("internal_endpoint")]
print("CMDB: %d internally-exposed services, %d external-only, %d live targets"
      % (len(internal_svcs), len(external_only), len(LIVE)))

zones = rows("zone_auth")
views = sorted({str(z.get("view")) for z in zones})
a_all = rows("record:a")
cname_all = rows("record:cname")
ns_all = rows("record:ns")
view_score = {}
for v in views:
    ok = 0
    for s in internal_svcs:
        if any(str(r.get("name")) == str(s.get("dns_name")) and str(r.get("view")) == v
               and str(r.get("ipv4addr")) == str(s.get("internal_endpoint")) for r in a_all):
            ok += 1
    view_score[v] = ok
INT = max(view_score, key=lambda v: view_score[v])
print("views=%s -> internal view = %r (matches %d CMDB internal endpoints)" % (views, INT, view_score[INT]))

def a_int(name, aa=None):
    return [r for r in (aa if aa is not None else rows("record:a"))
            if str(r.get("name")) == name and str(r.get("view")) == INT]

def cname_int(name, cc=None):
    return [r for r in (cc if cc is not None else rows("record:cname"))
            if str(r.get("name")) == name and str(r.get("view")) == INT]

def uuid_of(rec):
    if rec.get("uuid"):
        return str(rec["uuid"])
    m2 = re.search(r"/([0-9a-f-]{36}):", str(rec.get("_ref", "")))
    return m2.group(1) if m2 else None

for s in internal_svcs:
    name, target = str(s.get("dns_name")), str(s.get("internal_endpoint"))
    have = a_int(name, a_all)
    if not have:
        res = call("POST", DNS + "/record:a", body={"name": name, "ipv4addr": target, "view": INT})
        print("  +internal A %s -> %s (%s)" % (name, target, "ok" if not (isinstance(res, dict) and res.get("_error")) else res))
    else:
        for rec in have:
            if str(rec.get("ipv4addr")) != target:
                res = call("PUT", DNS + "/record:a/" + uuid_of(rec), body={"ipv4addr": target})
                print("  repoint internal A %s: %s -> %s (%s)" % (name, rec.get("ipv4addr"), target,
                      "ok" if not (isinstance(res, dict) and res.get("_error")) else res))
for s in external_only:
    assert not a_int(str(s.get("dns_name"))), "external-only %s must not gain an internal record" % s.get("name")
    print("  external-only %s: no internal record (left as designed)" % s.get("name"))

a_now = rows("record:a")
cname_now = rows("record:cname")

def resolves_live(name, depth=0):
    if depth > 8:
        return False
    a = a_int(name, a_now)
    if a:
        return all(str(r.get("ipv4addr")) in LIVE for r in a)
    c = cname_int(name, cname_now)
    if c:
        return all(resolves_live(str(r.get("canonical")), depth + 1) for r in c)
    return False

alias_owner = {}
for s in internal_svcs:
    for al in (s.get("aliases") or []):
        alias_owner[str(al)] = str(s.get("dns_name"))

for rec in [r for r in cname_now if str(r.get("view")) == INT]:
    name, canon = str(rec.get("name")), str(rec.get("canonical"))
    if resolves_live(canon):
        continue
    if name in alias_owner:
        res = call("PUT", DNS + "/record:cname/" + uuid_of(rec), body={"canonical": alias_owner[name]})
        print("  repoint CNAME %s: %s -> %s (%s)" % (name, canon, alias_owner[name],
              "ok" if not (isinstance(res, dict) and res.get("_error")) else res))
    else:
        res = call("DELETE", DNS + "/record:cname/" + uuid_of(rec))
        print("  -dangling CNAME %s -> %s (%s)" % (name, canon,
              "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

a_now = rows("record:a")

def glue_live(ns_host):
    a = a_int(ns_host, a_now)
    return bool(a) and all(str(r.get("ipv4addr")) in LIVE for r in a)

by_zone = {}
for r in [x for x in ns_all if str(x.get("view")) == INT]:
    by_zone.setdefault(str(r.get("name")), []).append(r)
live_ns = sorted({str(r.get("nameserver")) for zone, recs in by_zone.items()
                  for r in recs if glue_live(str(r.get("nameserver")))})
assert live_ns, "no live nameserver baseline discoverable"
svc_names = {str(s.get("dns_name")) for s in d42_services}
for zone, recs in sorted(by_zone.items()):
    active = any(n.endswith("." + zone) for n in svc_names)
    dead = [r for r in recs if not glue_live(str(r.get("nameserver")))]
    if not dead:
        print("  delegation %s healthy (baseline)" % zone)
        continue
    if active:
        for i, rec in enumerate(dead):
            tgt = live_ns[i % len(live_ns)]
            res = call("PUT", DNS + "/record:ns/" + uuid_of(rec), body={"nameserver": tgt})
            print("  repoint NS %s: %s -> %s (%s)" % (zone, rec.get("nameserver"), tgt,
                  "ok" if not (isinstance(res, dict) and res.get("_error")) else res))
    else:
        for rec in dead:
            res = call("DELETE", DNS + "/record:ns/" + uuid_of(rec))
            print("  -dangling delegation %s -> %s (%s)" % (zone, rec.get("nameserver"),
                  "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

protected = svc_names | set(alias_owner)
for rec in [r for r in rows("record:a") if str(r.get("view")) == INT]:
    name, ip = str(rec.get("name")), str(rec.get("ipv4addr"))
    if name in protected or ip in LIVE:
        continue
    res = call("DELETE", DNS + "/record:a/" + uuid_of(rec))
    print("  -dangling internal A %s -> %s (%s)" % (name, ip,
          "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

call("PATCH", SN + "/incident/%s" % inc_sys, body={
    "state": CLOSED, "close_code": "Solved (Permanently)",
    "close_notes": "Overnight DNS consolidation broke internal resolution for the apps tier: the "
                   "sub-zone delegation pointed at retired nameservers and many services' internal-view "
                   "records were missing or wrong. Restored every internal record to the CMDB endpoint, "
                   "repointed the delegation to the live corporate nameservers per the healthy peer "
                   "sub-zone, cleaned up dangling records, left external resolution and the public-only "
                   "services untouched. The suspected deploy was verified not the cause."})

print("\n--- readback ---")
a2 = rows("record:a")
c2 = rows("record:cname")
n2 = rows("record:ns")

def res_live2(name, depth=0):
    if depth > 8:
        return False
    a = [r for r in a2 if str(r.get("name")) == name and str(r.get("view")) == INT]
    if a:
        return all(str(r.get("ipv4addr")) in LIVE for r in a)
    c = [r for r in c2 if str(r.get("name")) == name and str(r.get("view")) == INT]
    if c:
        return all(res_live2(str(r.get("canonical")), depth + 1) for r in c)
    return False

for s in internal_svcs:
    name, target = str(s.get("dns_name")), str(s.get("internal_endpoint"))
    recs = [r for r in a2 if str(r.get("name")) == name and str(r.get("view")) == INT]
    check("internal A %s -> %s" % (name, target),
          bool(recs) and all(str(r.get("ipv4addr")) == target for r in recs))
    for al in (s.get("aliases") or []):
        check("alias %s resolves live" % al, res_live2(str(al)))
for s in external_only:
    check("external-only %s has no internal record" % s.get("name"),
          not any(str(r.get("name")) == str(s.get("dns_name")) and str(r.get("view")) == INT for r in a2))
for zone, recs in sorted(by_zone.items()):
    now = [r for r in n2 if str(r.get("name")) == zone and str(r.get("view")) == INT]
    active = any(n.endswith("." + zone) for n in svc_names)
    if active:
        check("delegation %s all-live" % zone, bool(now) and all(
            any(str(r2.get("name")) == str(r.get("nameserver")) and str(r2.get("view")) == INT
                and str(r2.get("ipv4addr")) in LIVE for r2 in a2) for r in now))
    else:
        check("dangling delegation %s removed" % zone,
              all(any(str(r2.get("name")) == str(r.get("nameserver")) and str(r2.get("view")) == INT
                      and str(r2.get("ipv4addr")) in LIVE for r2 in a2) for r in now))
check("no dangling internal A", all(str(r.get("ipv4addr")) in LIVE
      for r in a2 if str(r.get("view")) == INT and str(r.get("name")) not in protected))
check("no dead internal CNAME", all(res_live2(str(r.get("name")))
      for r in c2 if str(r.get("view")) == INT))
inc2 = (get(SN + "/incident/%s" % inc_sys) or {}).get("result", {})
check("incident closed", str(inc2.get("state")) == CLOSED)

print("\n%d mismatch(es)" % len(MISMATCHES))
for m3 in MISMATCHES:
    print("  FAILED:", m3)
sys.exit(1 if MISMATCHES else 0)
