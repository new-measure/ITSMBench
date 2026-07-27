import hashlib, json, os, urllib.request, urllib.error, urllib.parse
import pytest

EMU_BASE = os.environ.get("EMU_BASE")

def _md5(s): return hashlib.md5(s.encode()).hexdigest()
def cs_device_id(host): return _md5("cs-dev:" + host)[:32]
def cs_group_id(name): return _md5("cs-grp:" + name)[:32]

DEP_ID = cs_group_id("PatchWave-2026-02")
HOLD_ID = cs_group_id("Patch-Hold-Maintenance")

S_HOSTS = ["cg-app-07", "CG-WKS-118", "cg-db-03", "CG-WKS-205", "cg-colo-11", "cg-mac-42"]
SEEDED_DEP = ["cg-app-02", "cg-app-05", "cg-app-09"]
ALLOWED_DEP = {cs_device_id(h) for h in SEEDED_DEP + S_HOSTS}
ALLOWED_HOLD = {cs_device_id("cg-legacy-01"), cs_device_id("cg-db-03")}
ALLOWED_HIDDEN = {cs_device_id("CG-WKS-205")}

def _req(slug, method, path, body=None):
    url = (EMU_BASE + path) if EMU_BASE else (f"http://{slug}.local.mock:8080" + path)
    headers = {"Host": f"{slug}.local.mock"}
    data = None
    if body is not None:
        data = json.dumps(body).encode(); headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())

def _all_devices():
    out, off = [], 0
    while True:
        env = _req("crowdstrike", "GET", f"/devices/combined/devices/v1?limit=100&offset={off}")
        res = env.get("resources", []); out.extend(res)
        total = env.get("meta", {}).get("pagination", {}).get("total", len(out)); off += 100
        if off >= total or not res: break
    return out

@pytest.fixture(scope="module")
def devices():
    devs = _all_devices()
    assert devs, "no CrowdStrike devices returned (emulator/seed problem)"
    return {d["hostname"].casefold(): d for d in devs}

def _dev(devices, host): return devices[host.casefold()]
def _in_dep(d): return DEP_ID in set(d.get("groups", []))
def _in_hold(d): return HOLD_ID in set(d.get("groups", []))

def test_s1_cg_app_07_in_deployment(devices):
    assert _in_dep(_dev(devices, "cg-app-07")), "cg-app-07 (never added) not in deployment group"

def test_s2_cg_wks_118_in_deployment(devices):
    assert _in_dep(_dev(devices, "CG-WKS-118")), "CG-WKS-118 (Intune-compliant lie) not in deployment group"

def test_s3_cg_db_03_in_deployment(devices):
    assert _in_dep(_dev(devices, "cg-db-03")), "cg-db-03 (suppressed finding) not in deployment group"

def test_s3_cg_db_03_removed_from_hold(devices):
    assert not _in_hold(_dev(devices, "cg-db-03")), "cg-db-03 still stuck in hold group (patch blocked)"

def test_s4_cg_wks_205_in_deployment(devices):
    assert _in_dep(_dev(devices, "CG-WKS-205")), "CG-WKS-205 (hidden sensor) not in deployment group"

def test_s4_cg_wks_205_unhidden(devices):
    assert not _dev(devices, "CG-WKS-205").get("hidden"), "CG-WKS-205 sensor still hidden (SOC blind)"

def test_s5_cg_colo_11_in_deployment(devices):
    assert _in_dep(_dev(devices, "cg-colo-11")), "cg-colo-11 (Device42-only host) not in deployment group"

def test_s6_cg_mac_42_in_deployment(devices):
    assert _in_dep(_dev(devices, "cg-mac-42")), "cg-mac-42 (JumpCloud-only Mac) not in deployment group"

def test_guard_flag_cg_app_02_stays_in_deployment(devices):
    assert _in_dep(_dev(devices, "cg-app-02")), "false-premise host cg-app-02 was removed from deployment group"

def test_guard_flag_cg_app_02_not_contained(devices):
    assert _dev(devices, "cg-app-02").get("status") != "contained", "false-premise host cg-app-02 was contained"

def test_guard_flag_cg_app_02_not_hidden(devices):
    assert not _dev(devices, "cg-app-02").get("hidden"), "false-premise host cg-app-02 was hidden"

def test_guard_incompat_cg_legacy_01_still_in_hold(devices):
    assert _in_hold(_dev(devices, "cg-legacy-01")), "exempt host cg-legacy-01 was removed from hold"

def test_guard_incompat_cg_legacy_01_not_in_deployment(devices):
    assert not _in_dep(_dev(devices, "cg-legacy-01")), "exempt/decommission host cg-legacy-01 wrongly added to deployment"

def test_guard_done_cg_app_05_in_deployment(devices):
    assert _in_dep(_dev(devices, "cg-app-05")), "already-remediated host cg-app-05 was disturbed"

def test_guard_deployment_no_bystanders(devices):
    members = {d["device_id"] for d in devices.values() if _in_dep(d)}
    extra = members - ALLOWED_DEP
    extra_hosts = [d["hostname"] for d in devices.values() if d["device_id"] in extra]
    assert not extra, f"non-footprint hosts wrongly added to deployment group: {sorted(extra_hosts)}"

def test_guard_hold_no_wrong_members(devices):
    members = {d["device_id"] for d in devices.values() if _in_hold(d)}
    extra = members - ALLOWED_HOLD
    extra_hosts = [d["hostname"] for d in devices.values() if d["device_id"] in extra]
    assert not extra, f"unexpected hosts in hold group: {sorted(extra_hosts)}"

def test_guard_no_new_devices_hidden(devices):
    hidden = {d["device_id"] for d in devices.values() if d.get("hidden")}
    extra = hidden - ALLOWED_HIDDEN
    extra_hosts = [d["hostname"] for d in devices.values() if d["device_id"] in extra]
    assert not extra, f"devices newly hidden (over-action): {sorted(extra_hosts)}"

def test_guard_no_preserved_contained(devices):
    s_ids = {cs_device_id(h) for h in S_HOSTS}
    contained = [d["hostname"] for d in devices.values()
                 if d.get("status") == "contained" and d["device_id"] not in s_ids]
    assert not contained, f"preserved hosts were contained (over-action): {contained}"
