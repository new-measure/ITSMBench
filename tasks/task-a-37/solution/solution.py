#!/usr/bin/env python3
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

TICKET = "501"
SEARCH = "http://search.local.mock:8080/search"
SLACK = "http://slack.local.mock:8080/api"
NOTION = "http://notion.local.mock:8080/v1"
SCIM = "http://notion-admin.local.mock:8080/scim/v2"
GW = "http://google-workspace.local.mock:8080/admin/directory/v1"
GH = "http://github.local.mock:8080"
ZOHO = "http://zohodesk.local.mock:8080/api/v1"

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
        for k in keys + ("data", "results", "members", "value", "values", "items", "Resources", "users", "groups"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def check(desc, ok):
    print(("  READBACK OK   " if ok else "  READBACK FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

def prop_text(page, name):
    prop = (page.get("properties") or {}).get(name) or {}
    rich = prop.get("rich_text") or prop.get("title") or []
    return "".join(x.get("plain_text", "") for x in rich).strip()

for q in ("service desk ticket", "list users", "notion data source", "deploy keys"):
    hits = as_list(get(SEARCH + "?q=" + urllib.parse.quote(q) + "&limit=3"))
    print("search %-20r -> %s" % (q, [str(h.get("path") or h.get("route") or h.get("id")) for h in hits]))

ticket = get(ZOHO + "/tickets/" + TICKET)
assert ticket and not ticket.get("_error"), "cannot read ticket %s" % TICKET
desc = str(ticket.get("description", ""))
print("\nticket %s status=%s" % (TICKET, ticket.get("status")))

names = re.findall(r"^\s*\d+\)\s*([A-Z][\w'-]+ [A-Z][\w'-]+)\s*-", desc, re.M)
assert names, "no collaborators parsed from ticket description"
ticket_emails = set(re.findall(r"[\w.+-]+@[\w.-]+", desc))
print("departed collaborators discovered from ticket:", names)

lower_names = {n.lower() for n in names}
dash = {n: (n.split()[0] + "-" + n.split()[1]).lower() for n in names}
dash_logins = set(dash.values())

inferred = []
for t in as_list(get(ZOHO + "/tickets")):
    if str(t.get("id")) == TICKET or str(t.get("status", "")).lower() != "closed":
        continue
    text = str(t.get("description", ""))
    for c in as_list(get(ZOHO + "/tickets/%s/comments" % t.get("id"))):
        text += "\n" + str(c.get("content", ""))
    for line in text.splitlines():
        m = re.match(r"\s*-\s*([A-Za-z][\w /()]+?):", line)
        if m:
            inferred.append((m.group(1).strip(), line.strip()))
print("\ninferred completeness standard from PRECEDENT ticket(s):")
for sysname, line in inferred:
    print("   *", line)
assert inferred, "no precedent found to infer the standard from"

sl_users = as_list(get(SLACK + "/users.list"), "users")
print("\nslack: %d workspace users" % len(sl_users))
departed_sl = [u for u in sl_users if str(u.get("real_name", "")).lower() in lower_names]
for u in departed_sl:
    uid = str(u.get("id"))
    call("POST", SLACK + "/admin.users.remove", {"user_id": uid})
    rb = get(SLACK + "/users.info?user=" + uid) or {}
    check("slack %s (%s / %s) deactivated" % (uid, u.get("real_name"), u.get("profile", {}).get("email")),
          bool((rb.get("user") or {}).get("deleted")))
departed_sl_ids = {str(u.get("id")) for u in departed_sl}
for ch in as_list(get(SLACK + "/conversations.list"), "channels"):
    cid = str(ch.get("id"))
    members = {str(m) for m in as_list(get(SLACK + "/conversations.members?channel=" + cid))}
    for uid in sorted(members & departed_sl_ids):
        call("POST", SLACK + "/conversations.kick", {"channel": cid, "user": uid})
        left = {str(m) for m in as_list(get(SLACK + "/conversations.members?channel=" + cid))}
        check("slack %s removed from channel %s" % (uid, ch.get("name")), uid not in left)

scim_users = as_list(get(SCIM + "/Users?count=1000"), "Resources")
print("\nnotion-admin: %d scim users" % len(scim_users))
for u in scim_users:
    disp = str(u.get("displayName") or u.get("name", {}).get("formatted") or "").lower()
    if disp in lower_names and u.get("active"):
        uid = str(u.get("id"))
        call("PATCH", SCIM + "/Users/" + uid,
             {"schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
              "Operations": [{"op": "replace", "path": "active", "value": False}]})
        check("scim %s (%s) deactivated" % (uid, disp), get(SCIM + "/Users/" + uid).get("active") is False)

ds_ids = []
for db in as_list(get(NOTION + "/databases") or call("POST", NOTION + "/search", {"filter": {"value": "data_source", "property": "object"}})):
    for ds in db.get("data_sources", []) if isinstance(db, dict) else []:
        ds_ids.append(str(ds.get("id")))
for r in as_list(call("POST", NOTION + "/search", {})):
    if r.get("object") == "data_source":
        ds_ids.append(str(r.get("id")))
ds_ids = sorted(set(ds_ids))
print("\nnotion: data sources discovered:", ds_ids)

def ds_rows(ds_id):
    return as_list(call("POST", NOTION + "/data_sources/%s/query" % ds_id, {}))

for ds_id in ds_ids:
    rows = ds_rows(ds_id)
    for row in rows:
        collab = ""
        for key in ("Collaborator", "Name", "Person"):
            collab = prop_text(row, key)
            if collab:
                break
        if collab.lower() in lower_names:
            pid = str(row.get("id"))
            call("PATCH", NOTION + "/pages/" + pid, {"archived": True})
            still = {str(r.get("id")) for r in ds_rows(ds_id)}
            check("notion share row %s (%s) revoked" % (pid, collab), pid not in still)
    for row in rows:
        owner = prop_text(row, "Owner")
        space = prop_text(row, "Space")
        if not owner or not space:
            continue
        owner_departed = owner.lower() in {e.lower() for e in ticket_emails} or owner.lower() in lower_names
        if owner_departed:
            members = [m.strip() for m in re.split(r"[;,]", prop_text(row, "Members")) if m.strip()]
            replacement = next((m for m in members if m.lower() not in lower_names), None) or "Workspace Admin"
            pid = str(row.get("id"))
            call("PATCH", NOTION + "/pages/" + pid,
                 {"properties": {"Owner": {"rich_text": [{"type": "text", "text": {"content": replacement},
                                                          "plain_text": replacement}]}}})
            rb = next((r for r in ds_rows(ds_id) if str(r.get("id")) == pid), None)
            new_owner = prop_text(rb, "Owner").lower() if rb else ""
            check("notion teamspace %r owner reassigned to %r (not orphaned)" % (space, replacement),
                  bool(rb) and new_owner and new_owner not in lower_names
                  and new_owner not in {e.lower() for e in ticket_emails})

gw_users = as_list(get(GW + "/users"), "users")
print("\ngoogle-workspace: %d directory users" % len(gw_users))
departed_gw_emails = set()
for u in gw_users:
    if str(u.get("name", {}).get("fullName", "")).lower() in lower_names:
        email = str(u["primaryEmail"])
        departed_gw_emails.add(email.lower())
        call("PATCH", GW + "/users/" + email, {"suspended": True})
        check("gw user %s suspended" % email, bool((get(GW + "/users/" + email) or {}).get("suspended")))
target_emails = departed_gw_emails | {e.lower() for e in ticket_emails}
for g in as_list(get(GW + "/groups"), "groups"):
    gkey = g.get("email") or g.get("id")
    for m in as_list(get(GW + "/groups/%s/members" % gkey)):
        memail = str(m.get("email") or m.get("id"))
        if memail.lower() in target_emails:
            call("DELETE", GW + "/groups/%s/members/%s" % (gkey, memail))
            left = {str(x.get("email") or x.get("id")).lower() for x in as_list(get(GW + "/groups/%s/members" % gkey))}
            check("gw %s removed from group %s" % (memail, gkey), memail.lower() not in left)

for o in as_list(get(GH + "/organizations")) or [{"login": "northwind"}]:
    org = str(o.get("login"))
    outside = {str(m.get("login")) for m in as_list(get(GH + "/orgs/%s/outside_collaborators?per_page=100" % org))}
    for login in sorted(outside & dash_logins):
        call("DELETE", GH + "/orgs/%s/outside_collaborators/%s" % (org, login))
        left = {str(m.get("login")) for m in as_list(get(GH + "/orgs/%s/outside_collaborators?per_page=100" % org))}
        check("gh %s removed from org %s outside collaborators" % (login, org), login not in left)
    for r in as_list(get(GH + "/orgs/%s/repos?per_page=100" % org)):
        repo = str(r.get("name"))
        for c in as_list(get(GH + "/repos/%s/%s/collaborators?per_page=100" % (org, repo))):
            login = str(c.get("login"))
            if login in dash_logins:
                call("DELETE", GH + "/repos/%s/%s/collaborators/%s" % (org, repo, login))
                left = {str(x.get("login")) for x in as_list(get(GH + "/repos/%s/%s/collaborators?per_page=100" % (org, repo)))}
                check("gh %s removed as %s/%s collaborator" % (login, org, repo), login not in left)
        for k in as_list(get(GH + "/repos/%s/%s/keys?per_page=100" % (org, repo))):
            title = str(k.get("title", "")).lower()
            added_by = str((k.get("added_by") or {}).get("login", "")).lower()
            if added_by in dash_logins or any(n in title for n in lower_names):
                call("DELETE", GH + "/repos/%s/%s/keys/%s" % (org, repo, k.get("id")))
                left = {str(x.get("id")) for x in as_list(get(GH + "/repos/%s/%s/keys?per_page=100" % (org, repo)))}
                check("gh deploy key %s (%s) deleted from %s/%s" % (k.get("id"), title, org, repo),
                      str(k.get("id")) not in left)

call("PATCH", ZOHO + "/tickets/" + TICKET, {"status": "Closed"})
rb = get(ZOHO + "/tickets/" + TICKET) or {}
check("ticket %s closed" % TICKET, str(rb.get("status", "")).lower() == "closed")

print("\n%d readback mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
if MISMATCHES:
    sys.exit(1)
print("oracle complete: standard inferred cold from PRECEDENT + LINEAGE + ANOMALY; every mutation verified")
