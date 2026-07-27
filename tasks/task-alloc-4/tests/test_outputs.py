#!/usr/bin/env python3

import hashlib
import json
import urllib.request

SNOW = "http://servicenow.local.mock:8080"
SNIPE = "http://snipeit.local.mock:8080/api/v1"
TABLE = "u_gpu_reservation"

GPUS_PER_NODE = 8
CAP = 64
REQUIRED = 16

RELEASE_NODES = ("fab-05", "fab-06")
HUNG_PROJECTS = {"kilo-sweep", "delta-arch"}
PRESERVE = {"fab-01": "orion-train", "fab-02": "vega-serve", "fab-08": "sigma-ft"}
PRESERVE_PROJECTS = set(PRESERVE.values()) | {"helios-ckpt"}
HELIOS_NODES = ("fab-03", "fab-04")
SQUATTER_NODE = "fab-07"
TARGET_HOLDING_NODES = {"fab-01", "fab-02", "fab-03", "fab-04", "fab-05", "fab-06", "fab-08"}

NONHOLDING = {"released", "cancelled", "canceled", "closed", "complete", "completed",
              "done", "inactive", "expired", "deleted", "reclaimed", "queued", "cancel"}

VOL_KEYS = {
    "kilo-sweep": [("kilo-sweep", "fab-05")],
    "delta-arch": [("delta-arch", "fab-06")],
    "helios-ckpt": [("helios-ckpt", "fab-03"), ("helios-ckpt", "fab-04")],
    "orion-train": [("orion-train", "fab-01")],
    "vega-serve": [("vega-serve", "fab-02")],
    "sigma-ft": [("sigma-ft", "fab-08")],
}

def _asset_tag(project, node):
    return "CKPT-" + hashlib.md5(f"vol|{project}|{node}".encode()).hexdigest()[:6].upper()

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read() or "{}")

def all_reservations():
    out, off = [], 0
    while True:
        doc = _get(f"{SNOW}/api/now/table/{TABLE}?sysparm_limit=100&sysparm_offset={off}")
        page = doc.get("result", [])
        out.extend(page)
        if len(page) < 100:
            break
        off += 100
    return out

def all_volumes():
    out, off = [], 0
    while True:
        doc = _get(f"{SNIPE}/hardware?limit=500&offset={off}")
        page = doc.get("rows", [])
        out.extend(page)
        total = doc.get("total")
        off += len(page)
        if not page or (isinstance(total, int) and off >= total):
            break
    return out

def _gpus(r):
    try:
        return int(float(r.get("u_gpus") or 0))
    except (TypeError, ValueError):
        return 0

def holding(r):
    st = str(r.get("u_state", "")).strip().lower()
    return st != "" and st not in NONHOLDING

def holding_rows():
    return [r for r in all_reservations() if holding(r)]

def by_proj(rows, p):
    return sum(_gpus(r) for r in rows if str(r.get("u_project")) == p)

def on_node(rows, node, project=None):
    return sum(_gpus(r) for r in rows
               if str(r.get("u_node")) == node and (project is None or str(r.get("u_project")) == project))

def _vol_by_tag(tag):
    for v in all_volumes():
        if str(v.get("asset_tag")) == tag:
            return v
    return None

def _checked_out(vol):
    a = vol.get("assigned_to") if vol else None
    return a not in (None, "", [], {})

def test_release_allocated():
    rows = holding_rows()

    def new_on(node):
        return {str(r.get("u_project")) for r in rows if str(r.get("u_node")) == node} \
            - HUNG_PROJECTS - PRESERVE_PROJECTS

    cand = new_on(RELEASE_NODES[0]) & new_on(RELEASE_NODES[1])
    assert cand, ("no single new release holder occupies both freed nodes "
                  f"{RELEASE_NODES} (got {[new_on(n) for n in RELEASE_NODES]})")
    ok = any(on_node(rows, RELEASE_NODES[0], p) == GPUS_PER_NODE
             and on_node(rows, RELEASE_NODES[1], p) == GPUS_PER_NODE
             and by_proj(rows, p) == REQUIRED for p in cand)
    assert ok, f"release holder must hold 8 on {RELEASE_NODES[0]} + 8 on {RELEASE_NODES[1]} (=={REQUIRED}); cand={cand}"

def test_reclaim_kilo_gpu():
    assert by_proj(holding_rows(), "kilo-sweep") == 0, \
        "kilo-sweep is a hung job (0% GPU util for ~9 days); its GPU reservation must be released"

def test_reclaim_delta_gpu():
    assert by_proj(holding_rows(), "delta-arch") == 0, \
        "delta-arch is a hung job (0% GPU util for ~6 days); its GPU reservation must be released"

def test_reclaim_kilo_storage():
    v = _vol_by_tag(_asset_tag("kilo-sweep", "fab-05"))
    assert v is not None, "kilo-sweep checkpoint volume not found"
    assert not _checked_out(v), "reclaiming kilo-sweep must ALSO check in its checkpoint storage volume"

def test_reclaim_delta_storage():
    v = _vol_by_tag(_asset_tag("delta-arch", "fab-06"))
    assert v is not None, "delta-arch checkpoint volume not found"
    assert not _checked_out(v), "reclaiming delta-arch must ALSO check in its checkpoint storage volume"

def test_preserve_helios_gpu():
    rows = holding_rows()
    total = sum(on_node(rows, n, "helios-ckpt") for n in HELIOS_NODES)
    assert total == REQUIRED, \
        "helios-ckpt is a live checkpointed run under an active maintenance hold; its 16 GPUs must be preserved"

def test_preserve_helios_storage():
    for node in HELIOS_NODES:
        v = _vol_by_tag(_asset_tag("helios-ckpt", node))
        assert v is not None and _checked_out(v), \
            "helios-ckpt protected checkpoint volumes must remain checked out"

def test_preserve_busy_gpu():
    rows = holding_rows()
    for node, proj in PRESERVE.items():
        assert on_node(rows, node, proj) == GPUS_PER_NODE, \
            f"{proj} on {node} (in use) must be preserved"

def test_preserve_busy_storage():
    for node, proj in PRESERVE.items():
        v = _vol_by_tag(_asset_tag(proj, node))
        assert v is not None and _checked_out(v), f"{proj} volume must remain checked out"

def test_no_squat_allocation():
    assert on_node(holding_rows(), SQUATTER_NODE) == 0, \
        f"{SQUATTER_NODE} runs an un-booked live job; no reservation may be placed there"

def test_cap_respected():
    total = sum(_gpus(r) for r in holding_rows())
    assert total <= CAP, f"total holding GPUs {total} exceeds the hard cap {CAP}"

def test_exact_holding_nodes():
    nodes = {str(r.get("u_node")) for r in holding_rows() if _gpus(r) > 0}
    assert nodes == TARGET_HOLDING_NODES, \
        f"nodes with holding reservations must be exactly {sorted(TARGET_HOLDING_NODES)}; got {sorted(nodes)}"
