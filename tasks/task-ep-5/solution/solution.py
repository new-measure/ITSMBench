#!/usr/bin/env python3

import json
import re
import sys
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timedelta

TICKET_ID = "1873"
SEARCH = "http://search.local.mock:8080/search"

WRITES = []

def die(gate, msg):
    print(f"GATE FAILED [{gate}]: {msg}", file=sys.stderr)
    sys.exit(2)

def http(method, url, body=None, ok=(200, 201, 202, 204)):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        status = e.code
    if status not in ok:
        die("http", f"{method} {url} -> {status}: {raw[:300]!r}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return raw.decode("utf-8", "replace")

def get(url):
    return http("GET", url)

def find_op(query, want_path_fragment):
    res = get(f"{SEARCH}?q={urllib.parse.quote(query)}&limit=25")
    for row in res.get("results", []):
        if want_path_fragment in row.get("path", ""):
            return (row["host"], row["path"])
    die("search", f"no operation matching {want_path_fragment!r} for query {query!r}")

def base(host_path, strip_after):
    host, path = host_path
    idx = path.index(strip_after)
    return f"http://{host}:8080{path[:idx]}"

ZOHO = base(find_op("helpdesk tickets list", "/tickets"), "/tickets")
PUR = base(find_op("ediscovery cases list", "/security/cases/ediscoveryCases"),
           "/security/cases/ediscoveryCases")
SP = base(find_op("sharepoint sites lists items", "/sites/{site-id}/lists"), "/sites")
OD = base(find_op("drive items children onedrive", "/drives/{drive-id}/items"), "/drives")
CONF = base(find_op("confluence spaces pages", "/spaces/{id}/pages"), "/spaces")
SLACK = base(find_op("conversations list channels", "/api/conversations.list"),
             "/api/conversations.list")

def graph_list(url):
    out, skip = [], 0
    sep = "&" if "?" in url else "?"
    while True:
        page = get(f"{url}{sep}$top=200&$skip={skip}")
        batch = page.get("value", [])
        out.extend(batch)
        if len(batch) < 200:
            return out
        skip += 200

def conf_list(url):
    out, cursor = [], None
    sep = "&" if "?" in url else "?"
    while True:
        u = f"{url}{sep}limit=200" + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else "")
        page = get(u)
        out.extend(page.get("results", []))
        nxt = (page.get("_links") or {}).get("next")
        if not nxt:
            return out
        cursor = urllib.parse.parse_qs(urllib.parse.urlparse(nxt).query).get("cursor", [None])[0]
        if not cursor:
            return out

def slack_list(url, key):
    out, cursor = [], ""
    sep = "&" if "?" in url else "?"
    while True:
        u = f"{url}{sep}limit=199" + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else "")
        page = get(u)
        out.extend(page.get(key, []))
        cursor = ((page.get("response_metadata") or {}).get("next_cursor") or "").strip()
        if not cursor:
            return out

def parse_ts(s):
    return datetime.fromisoformat(str(s or "").replace("Z", "+00:00"))

def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()

def tokens(s):
    return set(norm(s).split())

ticket = get(f"{ZOHO}/tickets/{TICKET_ID}")
ticket_text = f"{ticket.get('subject', '')} {ticket.get('description', '')}"
print(f"[1] ticket {TICKET_ID}: {ticket.get('subject')!r}")

cases = graph_list(f"{PUR}/security/cases/ediscoveryCases")
tick_toks = tokens(ticket_text)
matches = [c for c in cases
           if str(c.get("status", "")).lower() == "active"
           and {t for t in (tokens(c.get("displayName", "")) & tick_toks)
                if any(ch.isdigit() for ch in t)}]
if len(matches) != 1:
    die("case", f"expected exactly one active matching case, got {len(matches)}")
case = matches[0]
HOLD = parse_ts(case["createdDateTime"])
print(f"[2] case {case['id']} {case['displayName']!r}, hold boundary {HOLD.isoformat()}")

custodians = graph_list(f"{PUR}/security/cases/ediscoveryCases/{case['id']}/custodians")
cust_emails = {}
for cu in custodians:
    if str(cu.get("holdStatus", "")).lower() != "applied":
        die("custodian-hold", f"custodian {cu.get('displayName')} hold is {cu.get('holdStatus')}")
    srcs = cu.get("userSources") or []
    email = (srcs[0].get("email") if srcs else None) or cu.get("email")
    if not email:
        die("custodian-email", f"custodian {cu.get('displayName')} has no email source")
    cust_emails[email.lower()] = cu.get("displayName")
if len(cust_emails) < 3:
    die("custodians", f"expected several custodians, got {len(cust_emails)}")
print(f"[2] {len(cust_emails)} held custodians: {sorted(cust_emails)}")

def is_custodian(email):
    return str(email or "").lower() in cust_emails

def personal_handle(email):
    return email.split("@")[0].replace(".", "_").lower()

q = http("POST", f"{PUR}/security/auditLog/queries", {
    "displayName": "ep5-oracle-window",
    "filterStartDateTime": (HOLD - timedelta(days=150)).isoformat(),
    "filterEndDateTime": (HOLD + timedelta(days=365)).isoformat(),
})
audit = graph_list(f"{PUR}/security/auditLog/queries/{q['id']}/records")
if len(audit) < 50:
    die("audit", f"audit window looks empty ({len(audit)} records)")
for r in audit:
    r["_t"] = parse_ts(r.get("createdDateTime"))
    r["_actor"] = str(r.get("userPrincipalName", "")).lower()
    r["_obj"] = str(r.get("objectId", ""))
audit.sort(key=lambda r: r["_t"])
print(f"[3] audit records: {len(audit)}")

drives = graph_list(f"{OD}/drives")
cust_drives = {}
for d in drives:
    email = str(((d.get("owner") or {}).get("user") or {}).get("email", "")).lower()
    if is_custodian(email) and str(d.get("driveType", "")) == "personal":
        cust_drives[email] = d
if len(cust_drives) < 3:
    die("drives", f"found only {len(cust_drives)} custodian personal drives")

def od_items(drive_id):
    return graph_list(f"{OD}/drives/{drive_id}/items")

def od_eff_parent(item):
    return (item.get("parentReference") or {}).get("id") or item.get("parentId")

def od_root(items, drive_id):
    for it in items:
        if it.get("root") is not None or it.get("name") == "root":
            return it
    die("od-root", f"no root item in drive {drive_id}")

flagged = [(e, n) for e, n in cust_emails.items() if norm(n) in norm(ticket_text)]
if len(flagged) != 1:
    die("flagged", f"expected exactly one custodian named in the ticket, got {len(flagged)}")
f_email, f_disp = flagged[0]
if f_email not in cust_drives:
    die("flagged-drive", f"no personal drive for {f_email}")
f_items = od_items(cust_drives[f_email]["id"])
report_hits = [it for it in f_items
               if "design validation" in norm(it.get("name", "")) and it.get("file") is not None]
if len(report_hits) != 1:
    die("flagged-file", f"expected exactly one design-validation file, got {len(report_hits)}")
report = report_hits[0]
if parse_ts(report.get("lastModifiedDateTime")) >= HOLD:
    die("flagged-file", "flagged file modified after the hold — premise not refutable")
handle = personal_handle(f_email)
own_trail = [r for r in audit
             if r["_actor"] == f_email and r["_t"] < HOLD
             and r.get("operation") in ("FileRenamed", "FileMoved")
             and f"/personal/{handle}/" in r["_obj"]]
if not own_trail:
    die("flagged-file", "no pre-hold owner rename/move trail for the flagged file")
foreign_post_hold = [r for r in audit
                     if r["_t"] >= HOLD and f"/personal/{handle}/" in r["_obj"]
                     and r["_actor"] != f_email]
if foreign_post_hold:
    die("flagged-file", "post-hold non-owner ops exist on the flagged drive — premise may be true")
content = get(f"{OD}/drives/{cust_drives[f_email]['id']}/items/{report['id']}/content")
if not content:
    die("flagged-file", "flagged file has no content")
print(f"[4] false premise verified: {report['name']!r} was renamed/moved by its owner "
      f"pre-hold and is intact; no action needed")

move_plan = []

od_reloc = {}
for r in audit:
    if r.get("operation") != "FileMoved" or r["_t"] < HOLD or "/personal/" not in r["_obj"]:
        continue
    m = re.search(r"/personal/([^/]+)/", r["_obj"])
    if not m:
        continue
    owner = next((e for e in cust_emails if personal_handle(e) == m.group(1).lower()), None)
    if not owner:
        continue
    name = r["_obj"].rstrip("/").split("/")[-1]
    od_reloc.setdefault((owner, name), []).append(r)

for (owner, name), recs in sorted(od_reloc.items()):
    first = min(recs, key=lambda r: r["_t"])
    if first["_actor"] == owner:
        print(f"[5a] {owner}: {name!r} first relocated by its owner — leaving as-is")
        continue
    after = first["_obj"].split("/personal/", 1)[1].split("/", 1)[1]
    parent_segs = [s for s in after.split("/") if s][1:-1]
    drive = cust_drives.get(owner) or die("od-move", f"no drive for {owner}")
    items = od_items(drive["id"])
    root = od_root(items, drive["id"])
    cands = [it for it in items if it.get("name") == name]
    if len(cands) != 1:
        die("od-move", f"{owner}: expected exactly one item named {name!r}, got {len(cands)}")
    item = cands[0]
    target = root
    for seg in parent_segs:
        kids = [k for k in items if od_eff_parent(k) == target["id"] and k.get("name") == seg]
        if len(kids) != 1:
            die("od-move", f"{owner}: cannot resolve source folder segment {seg!r}")
        target = kids[0]
    if od_eff_parent(item) == target["id"]:
        print(f"[5a] {owner}: {name!r} already at its hold-time location — no-op")
        continue
    d_id, i_id, t_id = drive["id"], item["id"], target["id"]

    def mk_od(d_id=d_id, i_id=i_id, t_id=t_id, name=name, owner=owner):
        def run():
            url = f"{OD}/drives/{d_id}/items/{i_id}"
            http("PATCH", url, {"parentId": t_id,
                                "parentReference": {"driveId": d_id, "id": t_id}})
            WRITES.append((f"onedrive move {owner}:{name!r}", "PATCH", url))
            if od_eff_parent(get(url)) != t_id:
                die("readback", f"onedrive move of {name!r} did not stick")
        return run
    move_plan.append(mk_od())

grantees = {}
for owner, drive in cust_drives.items():
    for it in od_items(drive["id"]):
        if it.get("folder") is None:
            continue
        for p in graph_list(f"{OD}/drives/{drive['id']}/items/{it['id']}/permissions"):
            for em in re.findall(r"[a-z0-9._%+-]+@[a-z0-9.-]+", json.dumps(p).lower()):
                if em not in cust_emails:
                    grantees.setdefault(em, p)
if len(grantees) != 1:
    die("grantee", f"expected exactly one collection grantee, got {sorted(grantees)}")
grantee_email, template_perm = next(iter(grantees.items()))
template_roles = template_perm.get("roles") or ["read"]
print(f"[5b] collection grantee template: {grantee_email} roles={template_roles}")

seen_shares = set()
for r in audit:
    if r.get("operation") != "SharingRevoked" or r["_t"] < HOLD or "/personal/" not in r["_obj"]:
        continue
    m = re.search(r"/personal/([^/]+)/", r["_obj"])
    if not m:
        continue
    owner = next((e for e in cust_emails if personal_handle(e) == m.group(1).lower()), None)
    if not owner or r["_actor"] == owner:
        continue
    name = r["_obj"].rstrip("/").split("/")[-1]
    if (owner, name) in seen_shares:
        continue
    seen_shares.add((owner, name))
    drive = cust_drives[owner]
    hits = [it for it in od_items(drive["id"]) if it.get("name") == name]
    if len(hits) != 1:
        die("share", f"{owner}: cannot resolve revoked-share item {name!r}")
    item = hits[0]
    perms = graph_list(f"{OD}/drives/{drive['id']}/items/{item['id']}/permissions")
    if any(grantee_email in json.dumps(p).lower() for p in perms):
        print(f"[5b] {owner}: {name!r} share already restored — no-op")
        continue
    d_id, i_id = drive["id"], item["id"]

    def mk_share(d_id=d_id, i_id=i_id, name=name, owner=owner):
        def run():
            url = f"{OD}/drives/{d_id}/items/{i_id}/permissions"
            http("POST", url, {"roles": list(template_roles),
                               "grantedToV2": {"user": {"email": grantee_email,
                                                        "displayName": grantee_email}}})
            WRITES.append((f"onedrive share {owner}:{name!r} -> {grantee_email}", "POST", url))
            if not any(grantee_email in json.dumps(p).lower() for p in graph_list(url)):
                die("readback", f"share restore on {name!r} did not stick")
        return run
    move_plan.append(mk_share())

sites = graph_list(f"{SP}/sites")

def site_for(obj):
    hits = [s for s in sites if obj.startswith(str(s.get("webUrl", "")) + "/")]
    return max(hits, key=lambda s: len(s.get("webUrl", ""))) if hits else None

_site_drives, _sp_items, _site_lists, _rows_cache = {}, {}, {}, {}

def sp_drives(site):
    if site["id"] not in _site_drives:
        _site_drives[site["id"]] = graph_list(f"{SP}/sites/{site['id']}/drives")
    return _site_drives[site["id"]]

def sp_lists(site):
    if site["id"] not in _site_lists:
        _site_lists[site["id"]] = graph_list(f"{SP}/sites/{site['id']}/lists")
    return _site_lists[site["id"]]

def list_rows(site_id, list_id):
    if (site_id, list_id) not in _rows_cache:
        _rows_cache[(site_id, list_id)] = graph_list(f"{SP}/sites/{site_id}/lists/{list_id}/items")
    return _rows_cache[(site_id, list_id)]

def try_get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        die("http", f"GET {url} -> {e.code}")

def sp_root(site, drive):
    root = try_get(f"{SP}/drives/{drive['id']}/root")
    if root is not None:
        return root
    for lst in sp_lists(site):
        for row in list_rows(site["id"], lst["id"]):
            it = try_get(f"{SP}/sites/{site['id']}/lists/{lst['id']}/items/{row['id']}/driveItem")
            if not it or str(it.get("driveId", "")) != str(drive["id"]):
                continue
            while True:
                pid = (it.get("parentReference") or {}).get("id")
                if not pid:
                    return it
                it = get(f"{SP}/drives/{drive['id']}/items/{pid}")
    die("sp-root", f"cannot resolve root of drive {drive.get('name')} on {site.get('displayName')}")

def sp_drive_items(drive_id, site=None):
    if drive_id not in _sp_items:
        drive = {"id": drive_id}
        root = sp_root(site, drive) if site is not None else get(f"{SP}/drives/{drive_id}/root")
        all_items, frontier, seen = [root], [root["id"]], {root["id"]}
        while frontier:
            nid = frontier.pop()
            for k in graph_list(f"{SP}/drives/{drive_id}/items/{nid}/children"):
                if k["id"] in seen:
                    continue
                seen.add(k["id"])
                all_items.append(k)
                if k.get("folder") is not None:
                    frontier.append(k["id"])
        _sp_items[drive_id] = all_items
    return _sp_items[drive_id]

def sp_eff_parent(item):
    return item.get("parentId") or (item.get("parentReference") or {}).get("id")

sp_reloc = {}
for r in audit:
    if (r.get("operation") != "FileMoved" or r["_t"] < HOLD
            or "/personal/" in r["_obj"] or "/Lists/" in r["_obj"]):
        continue
    site = site_for(r["_obj"])
    if not site:
        continue
    name = r["_obj"].rstrip("/").split("/")[-1]
    sp_reloc.setdefault((site["id"], name), []).append((site, r))

for (site_id, name), entries in sorted(sp_reloc.items()):
    site, first = min(entries, key=lambda e: e[1]["_t"])
    rel = first["_obj"][len(str(site["webUrl"])) + 1:]
    segs = [s for s in rel.split("/") if s]
    drive_name, folder_segs = segs[0], segs[1:-1]
    drs = [d for d in sp_drives(site)
           if d.get("displayName", d.get("name")) == drive_name or d.get("name") == drive_name]
    if len(drs) != 1:
        die("sp-move", f"cannot resolve drive {drive_name!r} on {site.get('displayName')}")
    drive = drs[0]
    items = sp_drive_items(drive["id"], site)
    hits = [it for it in items if it.get("name") == name]
    if len(hits) != 1:
        die("sp-move", f"expected one item named {name!r} in {drive_name!r}, got {len(hits)}")
    item = hits[0]
    owner = str(((item.get("createdBy") or {}).get("user") or {}).get("email", "")).lower()
    if not is_custodian(owner):
        continue
    if first["_actor"] == owner:
        print(f"[5c] {name!r} first relocated by its owner — leaving as-is")
        continue
    target = next(it for it in items if it.get("root") is not None or it.get("name") == "root")
    for seg in folder_segs:
        kids = [k for k in items if sp_eff_parent(k) == target["id"] and k.get("name") == seg]
        if len(kids) != 1:
            die("sp-move", f"cannot resolve folder segment {seg!r} in {drive_name!r}")
        target = kids[0]
    if sp_eff_parent(item) == target["id"]:
        print(f"[5c] {name!r} already at its hold-time location — no-op")
        continue
    d_id, i_id, t_id = drive["id"], item["id"], target["id"]

    def mk_sp(d_id=d_id, i_id=i_id, t_id=t_id, name=name):
        def run():
            url = f"{SP}/drives/{d_id}/items/{i_id}"
            http("PATCH", url, {"parentId": t_id,
                                "parentReference": {"driveId": d_id, "id": t_id}})
            WRITES.append((f"sharepoint move {name!r}", "PATCH", url))
            if sp_eff_parent(get(url)) != t_id:
                die("readback", f"sharepoint move of {name!r} did not stick")
        return run
    move_plan.append(mk_sp())

row_candidates = {}
for r in audit:
    if r.get("operation") != "ListItemUpdated" or r["_t"] < HOLD or "/Lists/" not in r["_obj"]:
        continue
    site = site_for(r["_obj"])
    if not site:
        continue
    m = re.search(r"/Lists/([^/]+)/items/([^/]+)$", r["_obj"])
    if not m:
        continue
    list_name, item_id = urllib.parse.unquote(m.group(1)), m.group(2)
    lst = [l for l in sp_lists(site)
           if l.get("displayName", l.get("name")) == list_name or l.get("name") == list_name]
    if len(lst) != 1:
        die("sp-rows", f"cannot resolve list {list_name!r} on {site.get('displayName')}")
    row_candidates[(site["id"], lst[0]["id"], item_id)] = site

def product_token(title):
    toks = norm(title).split()
    for t in toks:
        if any(ch.isdigit() for ch in t):
            return t
    return toks[0] if toks else ""

def live_path_of(site, docpath, title):
    fname = str(docpath).rstrip("/").split("/")[-1] if docpath else title
    for d in sp_drives(site):
        items = sp_drive_items(d["id"], site)
        by_id = {x["id"]: x for x in items}
        for it in items:
            if it.get("name") == fname and it.get("file") is not None:
                segs, cur = [], it
                while cur is not None and cur.get("root") is None and cur.get("name") != "root":
                    segs.append(cur.get("name"))
                    cur = by_id.get(sp_eff_parent(cur))
                return "/".join([d.get("displayName", d.get("name"))] + list(reversed(segs)))
    return None

conf_plan = []
spaces = conf_list(f"{CONF}/spaces")
conf_users = http("POST", f"{CONF}/users-bulk", {"accountIds": []}).get("results", [])
acct_email = {str(u.get("accountId")): str(u.get("email", "")).lower() for u in conf_users}

for sp_rec in spaces:
    pages = conf_list(f"{CONF}/spaces/{sp_rec['id']}/pages")
    for p in pages:
        owner = acct_email.get(str(p.get("ownerId") or p.get("authorId")), "")
        if not is_custodian(owner):
            continue
        versions = conf_list(f"{CONF}/pages/{p['id']}/versions")
        if not versions:
            continue
        last = max(versions, key=lambda v: int(v.get("number", 0)))
        v_author = acct_email.get(str(last.get("authorId")), str(last.get("authorId")))
        if v_author == owner or parse_ts(last.get("createdAt")) < HOLD:
            continue
        title = str(p.get("title", ""))
        parents = []
        for q_page in pages:
            if str(q_page["id"]) == str(p["id"]):
                continue
            body_val = ""
            body = q_page.get("body")
            if isinstance(body, dict):
                for v in body.values():
                    body_val += str(v.get("value", "")) if isinstance(v, dict) else str(v)
            if title and title in body_val:
                parents.append(q_page)
        if len(parents) != 1:
            die("confluence", f"page {title!r}: expected one index page listing it, got {len(parents)}")
        target = parents[0]
        if str(p.get("parentId")) == str(target["id"]):
            print(f"[5d] page {title!r} already under its index page — no-op")
            continue

        def mk_conf(page_id=p["id"], target_id=str(target["id"]), title=title,
                    t_title=target.get("title")):
            def run():
                url = f"{CONF}/pages/{page_id}"
                cur = get(url)
                ver = int(((cur.get("version") or {}).get("number")) or 1)
                http("PUT", url, {"id": cur["id"], "title": cur.get("title"),
                                  "parentId": target_id, "version": {"number": ver + 1}})
                WRITES.append((f"confluence re-parent {title!r} -> {t_title!r}", "PUT", url))
                if str(get(url).get("parentId")) != target_id:
                    die("readback", f"page {title!r} parent readback mismatch")
            return run
        conf_plan.append(mk_conf())

slack_users = slack_list(f"{SLACK}/api/users.list", "members")
email_to_uid = {str((u.get("profile") or {}).get("email", "")).lower(): u["id"] for u in slack_users}
cust_uids = {email_to_uid[e] for e in cust_emails if e in email_to_uid}
channels = slack_list(f"{SLACK}/api/conversations.list?types=public_channel,private_channel",
                      "channels")
hold_epoch = HOLD.timestamp()
slack_fixes = []
for ch in channels:
    if not ch.get("is_archived"):
        continue
    if len(cust_uids.intersection(ch.get("members") or [])) < 2:
        continue
    msgs = get(f"{SLACK}/api/conversations.history?channel={ch['id']}&limit=5").get("messages", [])
    if not msgs or max(float(m.get("ts", 0)) for m in msgs) < hold_epoch:
        continue
    slack_fixes.append(ch)
if len(slack_fixes) != 1:
    die("slack", f"expected exactly one displaced custodian channel, "
                 f"got {[c.get('name') for c in slack_fixes]}")
the_channel = slack_fixes[0]

def do_slack():
    url = f"{SLACK}/api/conversations.unarchive"
    http("POST", url, {"channel": the_channel["id"]})
    WRITES.append((f"slack unarchive #{the_channel.get('name')}", "POST", url))
    back = get(f"{SLACK}/api/conversations.info?channel={the_channel['id']}")
    if (back.get("channel") or {}).get("is_archived"):
        die("readback", f"channel {the_channel.get('name')} still archived")

print(f"[6] executing {len(move_plan)} relocation/share fixes...")
for p in move_plan:
    p()

_sp_items.clear()
_rows_cache.clear()
row_plan = []
for (site_id, list_id, item_id), site in sorted(row_candidates.items()):
    rows = list_rows(site_id, list_id)
    row = next((x for x in rows if str(x.get("id")) == str(item_id)), None)
    if row is None:
        die("sp-rows", f"audited list item {item_id} not found")
    f = row.get("fields") or {}
    if not is_custodian(str(f.get("Owner", "")).lower()):
        continue
    live_now = live_path_of(site, str(f.get("DocPath", "")), f.get("Title", ""))
    if (live_now is not None and norm(f.get("Status")) == "active"
            and str(f.get("DocPath")) == live_now and f.get("RetentionLabel")):
        print(f"[6] register row {item_id} already healthy — no-op")
        continue
    ptok = product_token(f.get("Title", ""))
    template = [x.get("fields") or {} for x in rows
                if str(x.get("id")) != str(item_id)
                and norm((x.get("fields") or {}).get("Status")) == "active"
                and product_token((x.get("fields") or {}).get("Title", "")) == ptok]
    labels = {t.get("RetentionLabel") for t in template if t.get("RetentionLabel")}
    if len(labels) != 1:
        die("sp-rows", f"no unique template label for product {ptok!r} ({labels})")
    live = live_path_of(site, str(f.get("DocPath", "")), f.get("Title", ""))
    if live is None:
        die("sp-rows", f"row {item_id}: referenced file not found anywhere on site")
    want = {"Status": "Active", "RetentionLabel": next(iter(labels)), "DocPath": live}
    if all(str(f.get(k)) == str(v) for k, v in want.items()):
        print(f"[6] register row {item_id} already correct — no-op")
        continue

    def mk_row(site_id=site_id, list_id=list_id, item_id=item_id, want=dict(want)):
        def run():
            url = f"{SP}/sites/{site_id}/lists/{list_id}/items/{item_id}/fields"
            http("PATCH", url, want)
            WRITES.append((f"register row {item_id} -> {want}", "PATCH", url))
            back = get(url)
            for k, v in want.items():
                if str(back.get(k)) != str(v):
                    die("readback", f"row {item_id} field {k} readback mismatch")
        return run
    row_plan.append(mk_row())

print(f"[6] executing {len(row_plan)} row fixes, {len(conf_plan)} wiki fixes, 1 chat fix...")
for p in row_plan:
    p()
for p in conf_plan:
    p()
do_slack()

http("POST", f"{ZOHO}/tickets/{TICKET_ID}/comments", {
    "isPublic": True,
    "content": (
        "Root cause: the quarterly content-lifecycle job ran after the litigation "
        "holds were applied and processed held custodians' content (site files and "
        "register rows relocated/rewritten, personal-drive folders relocated and a "
        "collection share revoked, wiki pages re-parented, one channel archived; one "
        "relocation failed leaving the index wrong). All custodian content has been "
        "restored to its hold-time state; lifecycle actions on non-custodian content "
        "were left in place. The document counsel flagged was renamed and moved by "
        "its owner before the holds were applied — it was never missing; counsel's "
        "index needs updating. Recommend suspending lifecycle processing for hold "
        "custodians."
    ),
})
http("PATCH", f"{ZOHO}/tickets/{TICKET_ID}", {"status": "Closed"})
if str(get(f"{ZOHO}/tickets/{TICKET_ID}").get("status", "")).lower() not in ("closed", "resolved"):
    die("readback", "ticket did not close")
WRITES.append((f"ticket {TICKET_ID} closed", "PATCH", f"{ZOHO}/tickets/{TICKET_ID}"))

print("\n=== WRITE LIST ===")
for desc, method, url in WRITES:
    print(f"  {method:6s} {url}\n         {desc}")
print(f"=== {len(WRITES)} writes, 0 readback mismatches ===")
