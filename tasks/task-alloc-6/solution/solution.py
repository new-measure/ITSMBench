#!/usr/bin/env python3
import json
import sys
import urllib.request
import urllib.parse
import urllib.error

TRIGGER = "RSV0001188"

SNIPE = "http://snipeit.local.mock:8080/api/v1"
SNOW = "http://servicenow.local.mock:8080/api/now/table"
FRESH = "http://freshdesk.local.mock:8080/api/v2"
RES_TABLE = "u_hw_provisioning_request"

def die(msg):
    print(f"SOLUTION-ABORT: {msg}", file=sys.stderr)
    sys.exit(1)

def _req(method, url, body=None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return 200, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw

def get(url):
    return _req("GET", url)

def snipe_list(path, **params):
    out, offset = [], 0
    while True:
        q = dict(params, limit=500, offset=offset)
        code, body = get(f"{SNIPE}{path}?{urllib.parse.urlencode(q)}")
        if code != 200 or not isinstance(body, dict):
            die(f"snipeit list {path} failed: {code} {body}")
        rows = body.get("rows", [])
        out.extend(rows)
        offset += len(rows)
        if not rows or offset >= body.get("total", len(out)):
            break
    return out

def snow_list(table, **params):
    out, offset = [], 0
    while True:
        q = dict(params, sysparm_limit=1000, sysparm_offset=offset)
        code, body = get(f"{SNOW}/{table}?{urllib.parse.urlencode(q)}")
        if code != 200 or not isinstance(body, dict):
            die(f"servicenow list {table} failed: {code} {body}")
        rows = body.get("result", [])
        out.extend(rows)
        offset += len(rows)
        if not rows or len(rows) < 1000:
            break
    return out

def fresh_list(path, **params):
    out, page = [], 1
    while True:
        q = dict(params, page=page, per_page=100)
        code, body = get(f"{FRESH}{path}?{urllib.parse.urlencode(q)}")
        if code != 200 or not isinstance(body, list):
            die(f"freshdesk list {path} failed: {code} {body}")
        out.extend(body)
        if len(body) < 100:
            break
        page += 1
    return out

def norm(v):
    return str(v or "").strip().lower()

def main():
    matches = snow_list(RES_TABLE, number=TRIGGER)
    trig = next((r for r in matches if norm(r.get("number")) == norm(TRIGGER)), None)
    if not trig:
        die(f"trigger request {TRIGGER} not found in {RES_TABLE}")
    qty = int(str(trig.get("u_qty") or 0))
    want_model = trig.get("u_model") or ""
    dest_name = trig.get("u_destination") or ""
    if not (qty and want_model and dest_name):
        die(f"trigger missing u_qty/u_model/u_destination: {trig}")
    print(f"[trigger] issue {qty} x '{want_model}' -> location '{dest_name}'")

    locs = snipe_list("/locations")
    dest = [l for l in locs if norm(l.get("name")) == norm(dest_name)]
    if len(dest) != 1:
        die(f"destination location '{dest_name}' resolved to {len(dest)} matches")
    dest_id = dest[0]["id"]

    requests = snow_list(RES_TABLE)
    res_by_num = {norm(r.get("number")): r for r in requests}
    cancelled_names = {}
    for r in requests:
        if norm(r.get("state")) == "cancelled" and r.get("u_asset_tag"):
            cancelled_names.setdefault(norm(r["u_asset_tag"]), r)
    hardware = snipe_list("/hardware")
    tickets = fresh_list("/tickets")
    labels = get(f"{SNIPE}/statuslabels?limit=500")[1].get("rows", [])
    status_meta = {str(s.get("id")): norm(s.get("status_meta") or s.get("status_type")) for s in labels}
    ready_id = next((s["id"] for s in labels if norm(s.get("status_meta")) == "deployable"
                     or "ready" in norm(s.get("name"))), 1)

    def fd_signals(serial):
        s = norm(serial)
        rows = [t for t in tickets if norm(t.get("serial")) == s]
        open_rma = any(norm(t.get("fault_status")) == "rma_hold" and str(t.get("status")) in ("2", "3") for t in rows)
        open_rep = any(norm(t.get("fault_status")) == "awaiting_parts" and str(t.get("status")) in ("2", "3") for t in rows)
        done = any(norm(t.get("fault_status")) == "repair_complete" and str(t.get("status")) in ("4", "5") for t in rows)
        return open_rma, open_rep, done

    reclaim = []
    for a in hardware:
        if norm((a.get("model") or {}).get("name")) != norm(want_model):
            continue
        meta = status_meta.get(str(a.get("status_id")), "")
        assigned = bool(a.get("assigned_to"))
        if meta == "deployable" and not assigned:
            continue
        open_rma, open_rep, done = fd_signals(a.get("serial"))
        if open_rma or open_rep:
            continue
        backlink = norm(a.get("_snipeit_reservation"))
        gov = norm(res_by_num.get(backlink, {}).get("state")) if backlink \
            else norm(cancelled_names.get(norm(a.get("asset_tag")), {}).get("state"))
        if gov == "cancelled":
            reclaim.append(a)
        elif done and meta == "undeployable" and not assigned:
            reclaim.append(a)

    print(f"[reclaim] {len(reclaim)}: {sorted(a.get('asset_tag') for a in reclaim)}")
    if len(reclaim) != qty:
        die(f"reclaimable count {len(reclaim)} != required qty {qty}")

    for a in reclaim:
        aid = a["id"]
        if a.get("assigned_to"):
            code, body = _req("POST", f"{SNIPE}/hardware/{aid}/checkin", {})
        else:
            code, body = _req("PATCH", f"{SNIPE}/hardware/{aid}", {"status_id": ready_id})
        if code != 200 or (isinstance(body, dict) and body.get("status") == "error"):
            die(f"reclaim prep {aid} failed: {code} {body}")
        code, body = _req("POST", f"{SNIPE}/hardware/{aid}/checkout",
                          {"assigned_location": dest_id, "checkout_to_type": "location"})
        if code != 200 or (isinstance(body, dict) and body.get("status") == "error"):
            die(f"checkout {aid} -> location {dest_id} failed: {code} {body}")

    hardware2 = snipe_list("/hardware")
    at_dest = [h for h in hardware2
               if norm((h.get("assigned_to") or {}).get("type")) == "location"
               and str((h.get("assigned_to") or {}).get("id")) == str(dest_id)
               and norm((h.get("model") or {}).get("name")) == norm(want_model)]
    at_tags = sorted(norm(h.get("asset_tag")) for h in at_dest)
    want_tags = sorted(norm(a.get("asset_tag")) for a in reclaim)
    if at_tags != want_tags:
        die(f"readback mismatch: at_dest={at_tags} want={want_tags}")
    print(f"[alloc] issued {len(at_tags)} '{want_model}' to '{dest_name}': {at_tags}")

    code, body = _req("PATCH", f"{SNOW}/{RES_TABLE}/{trig.get('sys_id')}", {"state": "Fulfilled"})
    if code != 200 or not isinstance(body, dict) or norm((body.get("result") or {}).get("state")) != "fulfilled":
        die(f"flagship fulfil PATCH failed: {code} {body}")
    print(f"[done] request {TRIGGER} -> Fulfilled")

if __name__ == "__main__":
    main()
