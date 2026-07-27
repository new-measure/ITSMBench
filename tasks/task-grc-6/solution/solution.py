#!/usr/bin/env python3
import email.utils
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

SP = "http://sharepoint.local.mock:8080/v1.0"
SN = "http://servicenow.local.mock:8080/api/now/table"
INCIDENT_NUMBER = "INC0030001"

ANON = {"anonymous", "anyone"}
ELEVATED = {"write", "owner"}
INTERNAL_DOMAINS = {"acme.example"}
PERMISSIVE_CAP = "externalUserAndGuestSharing"
SENSITIVE = {"Confidential", "Restricted"}
MISMATCHES = []
_SERVER_NOW = [None]

def call(method, url, body=None, form=False):
    data, headers = None, {"Accept": "application/json"}
    if form:
        data = urllib.parse.urlencode(body or {}).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            if _SERVER_NOW[0] is None and resp.headers.get("Date"):
                try:
                    _SERVER_NOW[0] = email.utils.parsedate_to_datetime(resp.headers["Date"]).date().isoformat()
                except Exception:
                    pass
            raw = resp.read().decode()
        return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:200]}

def get(url):
    return call("GET", url)

def gvalue(url):
    d = get(url)
    return (d or {}).get("value", []) if isinstance(d, dict) else (d if isinstance(d, list) else [])

def sn_rows(table, query=None):
    url = SN + "/" + table + (("?" + urllib.parse.urlencode(query)) if query else "")
    d = get(url)
    return (d or {}).get("result", []) if isinstance(d, dict) else []

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

incidents = sn_rows("incident")
cur = next((i for i in incidents if str(i.get("number")) == INCIDENT_NUMBER), None)
assert cur, "incident not found"
inc_sys = str(cur["sys_id"])
choices = sn_rows("sys_choice")
closed = [str(c.get("value")) for c in choices if str(c.get("name")) == "incident"
          and str(c.get("element")) == "state" and str(c.get("label", "")).lower() in ("resolved", "closed")]
CLOSE_STATE = closed[-1] if closed else "7"

classification = {str(r.get("u_key")): (str(r.get("u_classification")), str(r.get("u_status", "active")))
                  for r in sn_rows("u_site")}
NOW_DATE = _SERVER_NOW[0] or "2026-07-20"
valid_targets = set()
for r in sn_rows("u_data_exception"):
    if str(r.get("u_state")) == "approved" and str(r.get("u_valid_to", ""))[:10] >= NOW_DATE:
        valid_targets.add(str(r.get("u_target")))
print("now=%s | sensitive sites=%s | valid exception targets=%s"
      % (NOW_DATE, [k for k, (c, s) in classification.items() if c in SENSITIVE and s == "active"],
         sorted(valid_targets)))

def is_sensitive_live(site_id):
    c, s = classification.get(site_id, ("", "active"))
    return c in SENSITIVE and s == "active"

def perm_external(p):
    g = p.get("grantedToV2") or {}
    if g.get("group"):
        return False
    em = (g.get("user") or {}).get("email") or ""
    return bool(em) and em.split("@")[-1].lower() not in INTERNAL_DOMAINS

def perm_elevated(p):
    return bool({str(r).lower() for r in p.get("roles", [])} & ELEVATED)

def link_anon_active(it):
    lk = it.get("link") or {}
    if str(lk.get("scope", "")).lower() not in ANON:
        return False
    exp = lk.get("expirationDateTime")
    return not (exp and str(exp)[:10] < NOW_DATE)

sites = gvalue(SP + "/sites")
for s in sites:
    sid = s["id"]
    if not is_sensitive_live(sid):
        continue
    if s.get("sharingCapability") == PERMISSIVE_CAP:
        call("PATCH", SP + "/sites/%s" % sid, body={"sharingCapability": "disabled"})
        print("  cap  %s -> disabled" % sid)
    for p in gvalue(SP + "/sites/%s/permissions" % sid):
        if perm_external(p) and perm_elevated(p) and str(p["id"]) not in valid_targets:
            call("DELETE", SP + "/sites/%s/permissions/%s" % (sid, p["id"]))
            print("  perm %s/%s removed" % (sid, p["id"]))
    for lst in gvalue(SP + "/sites/%s/lists" % sid):
        if str(lst.get("template")) == "documentLibrary" and str(lst.get("defaultLinkScope", "")).lower() in ANON:
            call("PATCH", SP + "/sites/%s/lists/%s" % (sid, lst["id"]), body={"defaultLinkScope": "organization"})
            print("  list %s/%s -> organization" % (sid, lst["id"]))
    for dr in gvalue(SP + "/sites/%s/drives" % sid):
        for it in gvalue(SP + "/drives/%s/items/root/children" % dr["id"]):
            if link_anon_active(it) and str(it["id"]) not in valid_targets:
                call("PATCH", SP + "/drives/%s/items/%s" % (dr["id"], it["id"]), body={"link": None})
                print("  link %s/%s removed" % (dr["id"], it["id"]))

call("PATCH", SN + "/incident/%s" % inc_sys,
     body={"state": CLOSE_STATE, "close_code": "Solved (Permanently)",
           "close_notes": "Cleaned up actual data-oversharing across the sensitive workspaces: tightened site "
                          "sharing capability, removed external write/owner grants, removed anonymous document "
                          "links, and reset document-library default scopes - while leaving Public/Internal "
                          "workspaces, internal principals, internal-scope links, and formally-approved shares "
                          "untouched."})

print("\n--- readback ---")
sites2 = gvalue(SP + "/sites")
for s in sites2:
    sid = s["id"]
    if not is_sensitive_live(sid):
        continue
    check("cap safe %s" % sid, s.get("sharingCapability") != PERMISSIVE_CAP)
    for p in gvalue(SP + "/sites/%s/permissions" % sid):
        if str(p["id"]) in valid_targets:
            continue
        if perm_external(p):
            check("no external elevated perm %s/%s" % (sid, p["id"]), not perm_elevated(p))
    for lst in gvalue(SP + "/sites/%s/lists" % sid):
        if str(lst.get("template")) == "documentLibrary":
            check("library scope safe %s/%s" % (sid, lst["id"]),
                  str(lst.get("defaultLinkScope", "")).lower() not in ANON)
    for dr in gvalue(SP + "/sites/%s/drives" % sid):
        for it in gvalue(SP + "/drives/%s/items/root/children" % dr["id"]):
            if str(it["id"]) in valid_targets:
                continue
            check("no active anon link %s/%s" % (dr["id"], it["id"]), not link_anon_active(it))
inc2 = (get(SN + "/incident/%s" % inc_sys) or {}).get("result", {})
check("incident closed", str(inc2.get("state")) in ("6", "7"))

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
