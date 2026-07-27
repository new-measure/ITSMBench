import json
import urllib.request

D42 = "http://device42.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"

CI_SYS = {
    "billing-db-01": "e933c441a25e2f80d0d3fbdd05e4bdbd",
    "billing-app-02": "5272196dbbea81865edc3266ebf928a6",
    "billing-cache-03": "1780b5569c8ca888ff9b9b55dd783271",
    "billing-lb-04": "85db186810dd34066d09d3572f4bb04d",
    "billing-worker-05": "08ca0fc4e971ade5fb84aa9ceb7f4523",
}
CHG_SYS = "2348f4fe61b3e968ba17df041c5e64c6"

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else None

def _as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys + ("value", "values", "result"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def _devices():
    return _as_list(_get(D42 + "/api/2.0/devices/"), "devices")

def _device_by_name(name):
    return next((d for d in _devices() if str(d.get("name")) == name), None)

def _ips():
    return _as_list(_get(D42 + "/api/2.0/ips/"), "ips")

def _ip_by_id(ip_id):
    return next((x for x in _ips() if str(x.get("id")) == str(ip_id)), None)

def _ip_is_free(ip_id):
    rec = _ip_by_id(ip_id)
    if rec is None:
        return True
    if str(rec.get("available")).lower() != "yes":
        return False
    return not rec.get("device_id") and not rec.get("device")

def _dns_present(dns_id):
    recs = _as_list(_get(D42 + "/api/1.0/dns/records/"), "records")
    return any(str(r.get("id")) == str(dns_id) for r in recs)

def _subnet_present(subnet_id):
    recs = _as_list(_get(D42 + "/api/1.0/subnets/"), "subnets")
    return any(str(r.get("subnet_id")) == str(subnet_id) or str(r.get("id")) == str(subnet_id) for r in recs)

def _vlan_present(vlan_id):
    recs = _as_list(_get(D42 + "/api/1.0/vlans/"), "vlans")
    return any(str(r.get("vlan_id")) == str(vlan_id) or str(r.get("id")) == str(vlan_id) for r in recs)

def _element_present(uuid):
    recs = _as_list(_get(D42 + "/api/1.0/businessapps/elements/"), "businessapp_elements")
    return any(str(r.get("uuid")) == uuid or str(r.get("id")) == uuid for r in recs)

def _device_archived(name):
    d = _device_by_name(name)
    return d is not None and (d.get("archived") is True or str(d.get("archived")).lower() == "true")

def _ci_install_status(sys_id):
    r = _get(SN + "/cmdb_ci_server/" + sys_id)
    rec = (r or {}).get("result") if isinstance(r, dict) else None
    return str((rec or {}).get("install_status")) if rec else None

def _change_state(sys_id):
    r = _get(SN + "/change_request/" + sys_id)
    rec = (r or {}).get("result") if isinstance(r, dict) else None
    return str((rec or {}).get("state")) if rec else None

def test_db01_device_archived():
    assert _device_archived("billing-db-01")

def test_db01_ip_freed():
    assert _ip_is_free(3001)

def test_db01_stale_dns_removed():
    assert not _dns_present(4001)

def test_db01_cmdb_ci_retired():
    assert _ci_install_status(CI_SYS["billing-db-01"]) == "7"

def test_app02_device_archived():
    assert _device_archived("billing-app-02")

def test_app02_primary_ip_freed():
    assert _ip_is_free(3002)

def test_app02_secondary_mgmt_ip_freed():
    assert _ip_is_free(3003)

def test_app02_dns_removed():
    assert not _dns_present(4005)

def test_app02_cmdb_ci_retired():
    assert _ci_install_status(CI_SYS["billing-app-02"]) == "7"

def test_cache03_device_archived():
    assert _device_archived("billing-cache-03")

def test_cache03_ip_freed():
    assert _ip_is_free(3004)

def test_cache03_businessapp_element_removed():
    assert not _element_present("bae-cache-03")

def test_cache03_cmdb_ci_retired():
    assert _ci_install_status(CI_SYS["billing-cache-03"]) == "7"

def test_lb04_device_archived():
    assert _device_archived("billing-lb-04")

def test_lb04_ip_freed():
    assert _ip_is_free(3005)

def test_lb04_cmdb_ci_retired():
    assert _ci_install_status(CI_SYS["billing-lb-04"]) == "7"

def test_worker05_device_archived():
    assert _device_archived("billing-worker-05")

def test_worker05_ip_freed():
    assert _ip_is_free(3006)

def test_worker05_cmdb_ci_retired():
    assert _ci_install_status(CI_SYS["billing-worker-05"]) == "7"

def test_orphan_dns_removed():
    assert not _dns_present(4002)

def test_orphan_ip_freed():
    assert _ip_is_free(3007)

def test_orphan2_dns_removed():
    assert not _dns_present(4006)

def test_orphan2_ip_freed():
    assert _ip_is_free(3009)

def test_subnet_freed():
    assert not _subnet_present(6001)

def test_vlan_freed():
    assert not _vlan_present(7001)

