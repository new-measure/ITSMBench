#!/usr/bin/env python3

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

INCIDENT_NUM = "INC0010042"

SNOW = "http://servicenow.local.mock:8080"
D42 = "http://device42.local.mock:8080"
CAL = "http://calendar.local.mock:8080"
SNIPE = "http://snipeit.local.mock:8080/api/v1"

IDLE_UTIL = 10
STALE_DAYS = 3
RES_FIELDS = {"u_node", "u_gpus", "u_state"}
NODE_RE = re.compile(r"[a-z]+-\d{2,}")

_NOW = None

def _req(method, url, body=None):
    data = None
    hdrs = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            _cap_now(resp.headers.get("Date"))
            if not raw:
                return {}, resp.status
            try:
                return json.loads(raw), resp.status
            except json.JSONDecodeError:
                return raw.decode("utf-8", "replace"), resp.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return json.loads(raw), e.code
        except Exception:
            return raw.decode("utf-8", "replace"), e.code

def _cap_now(h):
    global _NOW
    if _NOW is None and h:
        try:
            dt = parsedate_to_datetime(h)
            _NOW = (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc))
        except Exception:
            pass

def now():
    return _NOW or datetime.now(timezone.utc)

def get(url):
    return _req("GET", url)

def parse_dt(v):
    if not v:
        return None
    s = str(v).strip().replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except Exception:
        return None

def die(msg):
    print("ORACLE-ABORT:", msg)
    sys.exit(2)

def load_trigger():
    doc, st = get(f"{SNOW}/api/now/table/incident?sysparm_query=number={INCIDENT_NUM}")
    rows = doc.get("result", []) if isinstance(doc, dict) else []
    if st != 200 or not rows:
        die(f"trigger incident {INCIDENT_NUM} not readable (status {st})")
    inc = rows[0]
    text = " ".join(str(inc.get(k, "")) for k in ("short_description", "description"))
    m = re.search(r"(\d+)\s*GPU", text, re.IGNORECASE)
    if not m:
        die("could not read required GPU count from trigger")
    return int(m.group(1)), inc.get("caller_id", "release-eng"), text

def list_table(table):
    out, off = [], 0
    while True:
        doc, st = get(f"{SNOW}/api/now/table/{table}?sysparm_limit=100&sysparm_offset={off}")
        if st != 200 or not isinstance(doc, dict):
            break
        page = doc.get("result", [])
        out.extend(page)
        if len(page) < 100:
            break
        off += 100
    return out

def find_ledger():
    cat, st = get(f"{SNOW}/api/now/table/sys_db_object?sysparm_limit=1000")
    names = [str(r.get("name")) for r in cat.get("result", [])] if st == 200 else []
    for name in [n for n in names if n.startswith("u_")] + [n for n in names if not n.startswith("u_")]:
        rows = list_table(name)
        if rows and RES_FIELDS.issubset(set(rows[0].keys())):
            return name, rows
    die("could not locate the reservation ledger table")

def list_devices():
    out, off = [], 0
    while True:
        doc, st = get(f"{D42}/api/1.0/devices/?limit=1000&offset={off}")
        if st != 200 or not isinstance(doc, dict):
            break
        page = doc.get("devices") or []
        out.extend(page)
        total = doc.get("total_count")
        off += len(page)
        if not page or (isinstance(total, int) and off >= total):
            break
    return out

def cf(dev):
    return {str(e.get("key") or e.get("name")): e.get("value") for e in (dev.get("custom_fields") or []) if isinstance(e, dict)}

def list_calendars():
    doc, st = get(f"{CAL}/calendar/v3/users/me/calendarList?maxResults=250")
    return [str(i.get("id")) for i in doc.get("items", [])] if st == 200 and isinstance(doc, dict) else []

def list_events(cal_id):
    out, tok = [], None
    while True:
        url = f"{CAL}/calendar/v3/calendars/{urllib.parse.quote(cal_id, safe='')}/events?maxResults=250&singleEvents=true"
        if tok:
            url += f"&pageToken={tok}"
        doc, st = get(url)
        if st != 200 or not isinstance(doc, dict):
            break
        out.extend(doc.get("items", []))
        tok = doc.get("nextPageToken")
        if not tok:
            break
    return out

def list_volumes():
    out, off = [], 0
    while True:
        doc, st = get(f"{SNIPE}/hardware?limit=500&offset={off}")
        if st != 200 or not isinstance(doc, dict):
            break
        page = doc.get("rows") or []
        out.extend(page)
        total = doc.get("total")
        off += len(page)
        if not page or (isinstance(total, int) and off >= total):
            break
    return out

def nodes_in(text):
    return set(NODE_RE.findall(text.lower()))

def held_nodes(events, ref):
    held = set()
    for e in events:
        if str(e.get("status")) == "cancelled":
            continue
        s = parse_dt((e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date"))
        en = parse_dt((e.get("end") or {}).get("dateTime") or (e.get("end") or {}).get("date"))
        if s and en and s <= ref <= en:
            held |= nodes_in(f"{e.get('summary','')} {e.get('location','')} {e.get('description','')}")
    return held

def assigned(vol):
    a = vol.get("assigned_to")
    return a not in (None, "", [], {})

def main():
    required, reporter, _ = load_trigger()
    print(f"[trigger] required={required} reporter={reporter!r}")

    table, reservations = find_ledger()
    print(f"[ledger] table={table} rows={len(reservations)}")

    node_tel = {}
    for d in list_devices():
        f = cf(d)
        if "gpu_total" in f or "gpu_utilization_pct" in f:
            nm = str(d.get("name") or "")
            if nm:
                node_tel[nm] = f
    print(f"[telemetry] gpu nodes={sorted(node_tel)}")

    ref = now()
    events = []
    for c in list_calendars():
        events.extend(list_events(c))
    held = held_nodes(events, ref)
    print(f"[now] {ref.isoformat()}  held={sorted(held)}")

    volumes = list_volumes()
    print(f"[storage] volumes={len(volumes)}")

    def holding(r):
        return str(r.get("u_state", "")).strip().lower() in ("active", "paused")

    def gpus(r):
        try:
            return int(float(r.get("u_gpus") or 0))
        except (TypeError, ValueError):
            return 0

    def idle(f):
        try:
            u = float(f.get("gpu_utilization_pct") or 0)
        except (TypeError, ValueError):
            u = 0
        return u < IDLE_UTIL and str(f.get("running_job") or "").strip() == ""

    def stale(f):
        last = parse_dt(f.get("last_job_finished"))
        return last is not None and (ref - last) > timedelta(days=STALE_DAYS)

    reclaim = []
    for r in reservations:
        if not holding(r):
            continue
        node = str(r.get("u_node", ""))
        f = node_tel.get(node, {})
        ok = node in node_tel and idle(f) and stale(f) and node not in held
        tag = "RECLAIM" if ok else "preserve"
        print(f"  [{tag}] {node} proj={r.get('u_project')} state={r.get('u_state')} "
              f"util={f.get('gpu_utilization_pct')} last={f.get('last_job_finished')} held={node in held}")
        if ok:
            reclaim.append(r)

    freed = sum(gpus(r) for r in reclaim)
    if freed < required:
        die(f"reclaimable capacity {freed} < required {required}")

    def volumes_for(project, node):
        m = []
        for v in volumes:
            hay = f"{v.get('name','')} {v.get('asset_tag','')} {v.get('notes','')}".lower()
            if project.lower() in hay or node.lower() in hay:
                m.append(v)
        return m

    reclaim_nodes = {str(r.get("u_node")) for r in reclaim}
    still_holding_nodes = {str(r.get("u_node")) for r in reservations if holding(r)} - reclaim_nodes
    placement = []
    remaining = required
    for node in sorted(reclaim_nodes):
        if remaining <= 0:
            break
        f = node_tel.get(node, {})
        if node in still_holding_nodes or not idle(f):
            continue
        try:
            capn = int(float(f.get("gpu_total") or 8))
        except (TypeError, ValueError):
            capn = 8
        take = min(capn, remaining)
        placement.append({"node": node, "gpus": take})
        remaining -= take
    if remaining > 0:
        die(f"could not place {required} GPUs on freed idle nodes (short {remaining})")

    print("\n[PLAN] release reservations:", [(r.get("u_node"), r.get("u_project")) for r in reclaim])
    print("[PLAN] checkin volumes:", [v.get("asset_tag") for r in reclaim
                                      for v in volumes_for(str(r.get("u_project")), str(r.get("u_node")))])
    print("[PLAN] allocate:", placement)

    for r in reclaim:
        _, st = _req("PATCH", f"{SNOW}/api/now/table/{table}/{r.get('sys_id')}", body={"u_state": "released"})
        if st != 200:
            die(f"release {r.get('sys_id')} failed ({st})")

    for r in reclaim:
        for v in volumes_for(str(r.get("u_project")), str(r.get("u_node"))):
            _, st = _req("POST", f"{SNIPE}/hardware/{v.get('id')}/checkin", body={"note": "reclaimed abandoned job"})
            if st not in (200, 201):
                die(f"checkin volume {v.get('asset_tag')} failed ({st})")

    release_project = "rel-4.2-gate"
    for p in placement:
        payload = {
            "u_project": release_project, "u_node": p["node"], "u_gpus": str(p["gpus"]),
            "u_state": "active", "u_priority": "high", "u_requested_for": reporter or "release-eng",
            "short_description": f"4.2 release gate capacity ({p['gpus']} GPU on {p['node']})",
        }
        _, st = _req("POST", f"{SNOW}/api/now/table/{table}", body=payload)
        if st not in (200, 201):
            die(f"allocate on {p['node']} failed ({st})")

    rows = list_table(table)
    hold = [r for r in rows if holding(r)]
    for p in placement:
        got = sum(gpus(r) for r in hold if str(r.get("u_node")) == p["node"] and str(r.get("u_project")) == release_project)
        if got != p["gpus"]:
            die(f"readback: release on {p['node']} == {got}, expected {p['gpus']}")
    for r in reclaim:
        proj = str(r.get("u_project"))
        if any(str(x.get("u_project")) == proj and holding(x) for x in rows):
            die(f"readback: reclaimed {proj} still holding")
    vols2 = list_volumes()
    for r in reclaim:
        for v in volumes_for(str(r.get("u_project")), str(r.get("u_node"))):
            cur = next((x for x in vols2 if str(x.get("id")) == str(v.get("id"))), {})
            if assigned(cur):
                die(f"readback: volume {v.get('asset_tag')} still checked out")
    total = sum(gpus(r) for r in hold)
    print(f"\n[OK] reserved {required} GPUs for release; released {len(reclaim)} jobs "
          f"+ their storage; total holding now {total} GPUs.")

if __name__ == "__main__":
    main()
