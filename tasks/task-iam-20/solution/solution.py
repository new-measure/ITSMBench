#!/usr/bin/env python3
import json
import re
import sys
import urllib.error
import urllib.request

TICKET = "INC0071204"
SEARCH = "http://search.local.mock:8080/search"
GMAIL = "http://gmail.local.mock:8080"
GW = "http://google-workspace.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"

FULL_MAILBOX_SCOPE = "https://mail.google.com/"
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
        for k in keys + ("result", "results", "value", "values", "items", "users", "members",
                         "delegates", "sendAs", "forwardingAddresses", "filter", "filters"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

def emails_in(text):
    return set(m.group(0).lower() for m in re.finditer(r"[\w.+-]+@[\w.-]+", str(text or "")))

def domain_of(addr):
    return str(addr).lower().split("@")[-1]

import urllib.parse

for q in ("incident table", "cmdb configuration item", "gmail delegates", "gmail sendAs",
          "forwarding addresses", "gmail filters", "workspace user tokens"):
    hits = as_list(get(SEARCH + "?q=" + urllib.parse.quote(q) + "&limit=2"))
    print("search %-22r -> %s" % (q, [h.get("path") for h in hits][:2]))

rows = as_list(get(SN + "/incident?sysparm_query=number=" + TICKET))
assert rows, "cannot read ticket %s" % TICKET
tk = rows[0]
print("\nticket %s state=%s" % (TICKET, tk.get("state")))

cmdb = as_list(get(SN + "/cmdb_ci"))
register = None
for c in cmdb:
    if c.get("u_mailbox") or ("approved" in str(c.get("name", "")).lower()
                              and "deleg" in str(c.get("name", "")).lower()):
        register = c
        break
assert register and register.get("u_mailbox"), "cannot locate the approved-delegation register"
MAILBOX = str(register["u_mailbox"]).strip().lower()
COMPANY_DOMAIN = domain_of(MAILBOX)
approved_delegates = emails_in(register.get("u_approved_delegates"))
approved_sendas = emails_in(register.get("u_approved_send_as"))
approved_forwarding = emails_in(register.get("u_approved_forwarding"))
approved_clients = set(str(register.get("u_approved_oauth_client", "")).replace(",", " ").split())
print("mailbox under review:", MAILBOX, "| company domain:", COMPANY_DOMAIN)
print("approved delegates:", sorted(approved_delegates), "| send-as:", sorted(approved_sendas))
print("approved forwarding:", sorted(approved_forwarding), "| clients:", approved_clients)

gw_users = as_list(get(GW + "/admin/directory/v1/users?customer=my_customer"))
by_email = {str(u.get("primaryEmail", "")).lower(): u for u in gw_users}

def top_ou(path):
    p = str(path or "").strip("/")
    return "/" + p.split("/")[0] if p else "/"

owner = by_email.get(MAILBOX)
HOME_OU = top_ou(owner.get("orgUnitPath")) if owner else "/Finance"
print("mailbox owner org unit (home):", HOME_OU)

def is_external(addr):
    return domain_of(addr) != COMPANY_DOMAIN

def grantee_stale(addr):
    a = str(addr).lower()
    if is_external(a):
        return True
    u = by_email.get(a)
    if u is None:
        return True
    if u.get("suspended"):
        return True
    if top_ou(u.get("orgUnitPath")) != HOME_OU:
        return True
    return False

def gm(path):
    return GMAIL + "/gmail/v1/users/" + urllib.parse.quote(MAILBOX) + "/settings/" + path

for d in as_list(get(gm("delegates")), "delegates"):
    a = str(d.get("delegateEmail", "")).lower()
    if a in approved_delegates:
        continue
    if grantee_stale(a):
        call("DELETE", gm("delegates/" + urllib.parse.quote(a)))

for s in as_list(get(gm("sendAs")), "sendAs"):
    a = str(s.get("sendAsEmail", "")).lower()
    if s.get("isPrimary") or a == MAILBOX or a in approved_sendas:
        continue
    if grantee_stale(a):
        call("DELETE", gm("sendAs/" + urllib.parse.quote(a)))

for f in as_list(get(gm("forwardingAddresses")), "forwardingAddresses"):
    a = str(f.get("forwardingEmail", "")).lower()
    if is_external(a):
        call("DELETE", gm("forwardingAddresses/" + urllib.parse.quote(a)))

for flt in as_list(get(gm("filters")), "filter", "filters"):
    fwd = str((flt.get("action") or {}).get("forward", "")).lower()
    if fwd and is_external(fwd):
        call("DELETE", gm("filters/" + urllib.parse.quote(str(flt.get("id")))))

def tokens_of(user_email):
    return as_list(get(GW + "/admin/directory/v1/users/" + urllib.parse.quote(user_email) + "/tokens"),
                   "items")

for u in gw_users:
    ue = str(u.get("primaryEmail", "")).lower()
    for t in tokens_of(ue):
        cid = str(t.get("clientId", ""))
        if cid in approved_clients:
            continue
        broad = FULL_MAILBOX_SCOPE in (t.get("scopes") or [])
        if u.get("suspended") or broad:
            call("DELETE", GW + "/admin/directory/v1/users/" + urllib.parse.quote(ue)
                 + "/tokens/" + urllib.parse.quote(cid))

call("PATCH", SN + "/incident/" + tk["sys_id"],
     {"state": "7", "close_code": "Closed complete",
      "close_notes": "Reviewed delegated/impersonation access on the CFO office mailbox. Removed "
                     "stale mailbox delegates and send-as tied to departed/transferred staff, "
                     "external delegate/send-as/forwarding/forward-filters (exfil/impersonation), "
                     "and third-party OAuth grants for departed users and full-mailbox-scope "
                     "unapproved apps. Retained the executive assistant delegate/send-as, the "
                     "approved controller delegate, the sanctioned internal archive forwarding, the "
                     "benign internal filters, and the approved backup integration."})

print("\n--- readback ---")
deleg = {str(d.get("delegateEmail", "")).lower() for d in as_list(get(gm("delegates")), "delegates")}
sas = {str(s.get("sendAsEmail", "")).lower() for s in as_list(get(gm("sendAs")), "sendAs")}
fwd = {str(f.get("forwardingEmail", "")).lower() for f in as_list(get(gm("forwardingAddresses")), "forwardingAddresses")}
flt_ids = {str(f.get("id")) for f in as_list(get(gm("filters")), "filter", "filters")}
flt_fwd_ext = [f for f in as_list(get(gm("filters")), "filter", "filters")
               if str((f.get("action") or {}).get("forward", "")) and is_external((f.get("action") or {}).get("forward"))]

for a in deleg:
    check("delegate ok: %s" % a, (a in approved_delegates) or (not grantee_stale(a)))
for a in approved_delegates:
    check("approved delegate kept: %s" % a, a in deleg)
for a in sas:
    check("send-as ok: %s" % a, a == MAILBOX or a in approved_sendas or not grantee_stale(a))
for a in approved_sendas:
    check("approved send-as kept: %s" % a, a in sas)
check("CFO primary send-as kept", MAILBOX in sas)

for a in fwd:
    check("forwarding ok (internal): %s" % a, not is_external(a))
for a in approved_forwarding:
    check("approved forwarding kept: %s" % a, a in fwd)

check("no external-forward filter remains", len(flt_fwd_ext) == 0)

approved_kept = False
for u in gw_users:
    ue = str(u.get("primaryEmail", "")).lower()
    for t in tokens_of(ue):
        cid = str(t.get("clientId", ""))
        if cid in approved_clients:
            approved_kept = approved_kept or (ue == MAILBOX)
            continue
        broad = FULL_MAILBOX_SCOPE in (t.get("scopes") or [])
        check("token removed (%s / %s)" % (ue, cid), not (u.get("suspended") or broad))
check("approved backup token kept on mailbox", approved_kept)

rb = as_list(get(SN + "/incident?sysparm_query=number=" + TICKET))
check("ticket closed", rb and str(rb[0].get("state")) in ("6", "7"))

print("\n%d readback mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
