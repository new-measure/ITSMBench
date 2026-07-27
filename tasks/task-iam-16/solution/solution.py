#!/usr/bin/env python3
import datetime
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

TICKET = "INC0071500"
SEARCH = "http://search.local.mock:8080/search"
ENTRA = "http://entra-id.local.mock:8080/v1.0"
SP = "http://sharepoint.local.mock:8080/v1.0"
OD = "http://onedrive.local.mock:8080/v1.0"
SN = "http://servicenow.local.mock:8080/api/now/table"

MISMATCHES = []

def call(method, url, body=None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
        return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        return {"_error": e.code}

def get(url):
    return call("GET", url)

def as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys + ("value", "values", "result", "results", "items", "members", "users"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

def ts(value):
    s = str(value or "").strip()
    if not s:
        return None
    s = s.replace("Z", "").replace("T", " ")
    s = re.split(r"\.", s)[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt).replace(tzinfo=datetime.timezone.utc).timestamp()
        except ValueError:
            continue
    return None

for q in ("incident table", "sharepoint site permissions", "onedrive item permissions",
          "entra group members", "cmdb classification", "change request"):
    hits = as_list(get(SEARCH + "?q=" + urllib.parse.quote(q) + "&limit=3"))
    print("search %-30r -> %s" % (q, [str(h.get("path") or h.get("route") or h.get("id")) for h in hits][:3]))

rows = as_list(get(SN + "/incident?sysparm_query=number=" + TICKET))
assert rows, "cannot read ticket %s" % TICKET
finding = rows[0]
FIND_TEXT = (finding.get("short_description", "") + "\n" + finding.get("description", ""))
FIND_LOW = FIND_TEXT.lower()
print("\nticket %s state=%s" % (TICKET, finding.get("state")))

NOW_TS = ts("2026-07-18 00:00:00")

ALL_GROUPS = as_list(get(ENTRA + "/groups?$top=200"))
GROUP_IDS = {str(g["id"]) for g in ALL_GROUPS}
ALL_USERS = as_list(get(ENTRA + "/users?$top=400"))
ORG_USER_IDS = {str(u["id"]) for u in ALL_USERS if str(u.get("userType", "Member")) != "Guest"}

def expand_group(gid, seen=None):
    seen = seen or set()
    if gid in seen:
        return set()
    seen.add(gid)
    out = set()
    for m in as_list(get(ENTRA + "/groups/%s/members?$top=200" % gid)):
        mid = str(m.get("id"))
        if mid in GROUP_IDS:
            out |= expand_group(mid, seen)
        else:
            out.add(mid)
    return out

def group_by_audience(audience_text):
    low = str(audience_text).lower()
    best = None
    for g in ALL_GROUPS:
        name = str(g.get("displayName", ""))
        if name.lower() in low:
            if best is None or len(name) > len(str(best.get("displayName", ""))):
                best = g
    return best

approved_ext = set()
for c in as_list(get(SN + "/change_request?sysparm_query=" + urllib.parse.quote("state=3"))) or \
         as_list(get(SN + "/change_request")):
    blob = (c.get("short_description", "") + " " + c.get("description", "") + " " + c.get("close_notes", "")).lower()
    end = ts(c.get("end_date") or c.get("work_end"))
    active = end is None or (NOW_TS is not None and end >= NOW_TS)
    if not active:
        continue
    for em in re.findall(r"[\w.+-]+@[\w.-]+", blob):
        if not em.endswith("@meridiancap.example"):
            approved_ext.add(em.lower())
print("approved ACTIVE external advisors:", sorted(approved_ext))

CMDB = as_list(get(SN + "/cmdb_ci")) or as_list(get(SN + "/cmdb_ci_service"))

def _norm(name):
    s = str(name).lower()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\.(xlsx|docx|pptx|pdf|csv|txt)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s

def cmdb_for(resource_name):
    r = _norm(resource_name)
    for ci in CMDB:
        c = _norm(ci.get("name", ""))
        if r and (r in c or c in r):
            return ci
    return None

sites = as_list(get(SP + "/sites?$top=200")) or as_list(get(SP + "/sites"))
flagged_sites = [s for s in sites if str(s.get("displayName", "")) and str(s.get("displayName")).lower() in FIND_LOW]

drives = as_list(get(OD + "/drives"))
DRIVE = str(drives[0]["id"]) if drives else None
drive_items = []
if DRIVE:
    queue = list(as_list(get(OD + "/drives/%s/root/children" % DRIVE)))
    seen = set()
    while queue:
        it = queue.pop(0)
        iid = str(it.get("id"))
        if iid in seen:
            continue
        seen.add(iid)
        drive_items.append(it)
        if it.get("folder"):
            queue.extend(as_list(get(OD + "/drives/%s/items/%s/children" % (DRIVE, iid))))
flagged_items = [it for it in drive_items if str(it.get("name", "")).lower() in FIND_LOW]

print("flagged sites:", [s.get("displayName") for s in flagged_sites])
print("flagged items:", [it.get("name") for it in flagged_items])

def keep_perm(perm, intended_gid, owner_email):
    if perm.get("link"):
        return False
    g = (perm.get("grantedToV2", {}) or {}).get("group", {}) or {}
    if intended_gid and str(g.get("id")) == str(intended_gid):
        return True
    u = (perm.get("grantedToV2", {}) or {}).get("user", {}) or {}
    email = str(u.get("email", "")).lower()
    if owner_email and email == str(owner_email).lower():
        return True
    if email and email in approved_ext:
        return True
    return False

def remediate(resource_name, perms, del_url):
    ci = cmdb_for(resource_name.split(" (")[0])
    audience = ci.get("u_intended_audience") if ci else ""
    owner_email = (ci.get("owned_by") if ci else "") or ""
    grp = group_by_audience(audience)
    intended_gid = grp["id"] if grp else None
    print("  %-40s intended=%-26s owner=%s" % (resource_name[:40], str(audience)[:26], owner_email))
    for p in perms:
        if not keep_perm(p, intended_gid, owner_email):
            call("DELETE", del_url(p))

for s in flagged_sites:
    sid = s["id"]
    perms = as_list(get(SP + "/sites/%s/permissions" % sid))
    remediate(str(s.get("displayName")), perms, lambda p, sid=sid: SP + "/sites/%s/permissions/%s" % (sid, p["id"]))

for it in flagged_items:
    iid = it["id"]
    perms = as_list(get(OD + "/drives/%s/items/%s/permissions" % (DRIVE, iid)))
    remediate(str(it.get("name")), perms, lambda p, iid=iid: OD + "/drives/%s/items/%s/permissions/%s" % (DRIVE, iid, p["id"]))

call("PATCH", SN + "/incident/%s" % finding["sys_id"],
     {"state": "7", "close_code": "Closed complete",
      "close_notes": "Remediated each flagged resource to least exposure: removed the over-broad "
                     "access paths (nested/over-broad group grants, anonymous and organization "
                     "sharing links, stale external guests, and direct over-shares) while retaining "
                     "the intended team audience, the resource owner, and the approved active "
                     "external advisor. Correctly-shared peers were left untouched."})

print("\n--- readback ---")

def eff_audience(perms):
    aud = set()
    for pm in perms:
        link = pm.get("link")
        if link:
            sc = str(link.get("scope"))
            if sc in ("anonymous", "anyone"):
                aud.add("*ANON*")
            elif sc in ("organization", "users"):
                aud |= ORG_USER_IDS
            continue
        g = pm.get("grantedToV2", {}) or {}
        if "group" in g:
            aud |= expand_group(str(g["group"].get("id")))
        elif "user" in g:
            aud.add(str(g["user"].get("id")))
    return aud

def uid_by_email(email):
    for u in ALL_USERS:
        if str(u.get("mail", "")).lower() == email.lower() or str(u.get("userPrincipalName", "")).lower() == email.lower():
            return str(u["id"])
    return None

def site_perms(display):
    sid = next((s["id"] for s in sites if str(s.get("displayName")) == display), None)
    return as_list(get(SP + "/sites/%s/permissions" % sid)) if sid else []

def item_perms(name):
    iid = next((it["id"] for it in drive_items if str(it.get("name")) == name), None)
    return as_list(get(OD + "/drives/%s/items/%s/permissions" % (DRIVE, iid))) if iid else []

D = "@meridiancap.example"
fin = site_perms("Corporate Finance")
titan = site_perms("Deal Room - Project Titan")
board = item_perms("Board Materials")
model = item_perms("Project Titan - Financial Model.xlsx")
dd = item_perms("Project Titan - Due Diligence")

def out(perms, email):
    aud = eff_audience(perms)
    if "*ANON*" in aud:
        return False
    u = uid_by_email(email)
    return u is None or u not in aud

def no_link(perms, scopes):
    return not any(str((p.get("link") or {}).get("scope")) in scopes for p in perms)

def ext_gone(perms, email):
    return not any(str(((p.get("grantedToV2", {}) or {}).get("user", {}) or {}).get("email", "")).lower() == email
                   for p in perms)

def grp_gone(perms, name):
    return not any(str(((p.get("grantedToV2", {}) or {}).get("group", {}) or {}).get("displayName")) == name
                   for p in perms)

check("finance: analytics-guild (nested) cut", out(fin, "kofi.mensah" + D))
check("finance: marketing group cut", out(fin, "lena.fischer" + D))
check("finance: direct-internal cut", out(fin, "tunde.okafor" + D))
check("finance: stale external vendor cut", out(fin, "vendor@brightledger.example"))
check("titan: corpdev group cut", out(titan, "sven.larsson" + D))
check("titan: direct-internal cut", out(titan, "rohan.singh" + D))
check("titan: stale external zenith cut", out(titan, "former@zenithpartners.example"))
check("board: no anonymous link", no_link(board, {"anonymous", "anyone"}))
check("board: no organization link", no_link(board, {"organization", "users"}))
check("board: stale external klein cut", ext_gone(board, "p.klein@northbridge.example"))
check("board: direct-internal cut", ext_gone(board, "jia.tan" + D))
check("model: no anonymous link", no_link(model, {"anonymous", "anyone"}))
check("model: finance-extended group cut", grp_gone(model, "Finance Extended"))
check("model: stale external contractor cut", ext_gone(model, "contractor@brightledger.example"))
check("dd: no organization link", no_link(dd, {"organization", "users"}))
check("dd: no anonymous link", no_link(dd, {"anonymous", "anyone"}))
check("dd: stale external zenith2 cut", ext_gone(dd, "dd.temp@zenithpartners.example"))
check("dd: corpdev group cut", grp_gone(dd, "Corporate Development"))

check("finance: finance member retained", not out(fin, "nadia.cho" + D))
check("finance: owner retained", not out(fin, "diane.holloway" + D))
check("titan: deal team retained", not out(titan, "aaron.cole" + D))
check("titan: approved external Apex retained", not ext_gone(titan, "m.reyes@apexadvisory.example"))
check("board: exec retained", not out(board, "ingrid.sato" + D))
check("model: deal team retained", not out(model, "aaron.cole" + D))
check("dd: deal team retained", not out(dd, "aaron.cole" + D))

rb = as_list(get(SN + "/incident?sysparm_query=number=" + TICKET))
check("ticket closed", rb and str(rb[0].get("state")) in ("6", "7"))

print("\n%d readback mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
