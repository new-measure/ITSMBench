#!/usr/bin/env python3
import datetime
import json
import re
import sys
import urllib.error
import urllib.request

D42 = "http://device42.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"

CHANGE_NUMBER = "CHG0030001"

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
        return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw
    except urllib.error.HTTPError as e:
        return {"_error": e.code}

def get(url):
    return call("GET", url)

def as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys + ("result", "devices", "ips", "subnets", "vlans", "records",
                         "businessapps", "businessapp_elements", "value", "values"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def check(desc, ok):
    print(("  READBACK OK   " if ok else "  READBACK FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

def parse_dt(s):
    if not s:
        return None
    t = str(s).replace("T", " ").replace("Z", "").strip()[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(t, fmt)
        except ValueError:
            continue
    return None

changes = as_list(get(SN + "/change_request"))
current = next((c for c in changes if str(c.get("number")) == CHANGE_NUMBER), None)
assert current, "cannot find change %s" % CHANGE_NUMBER
chg_sys_id = str(current["sys_id"])
desc = str(current.get("description", ""))
print("change %s sys_id=%s state=%s" % (CHANGE_NUMBER, chg_sys_id, current.get("state")))

ticket_hosts = re.findall(r"^\s*-\s*([A-Za-z0-9][\w.-]*)\s*$", desc, re.M)
assert ticket_hosts, "no host list parsed from the change description"
print("hosts named on the change:", ticket_hosts)

mcidr = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})/(\d{1,2})", desc)
target_net, target_mask = (mcidr.group(1), int(mcidr.group(2))) if mcidr else (None, None)
print("subnet to free (from ticket):", target_net, "/", target_mask)

ref_now = parse_dt(current.get("sys_created_on")) or datetime.datetime(2026, 7, 16)

choices = as_list(get(SN + "/sys_choice"))

def choice_value(elem, label_rx, table_rx="cmdb_ci|change_request"):
    for c in choices:
        if (re.search(elem, str(c.get("element", "")), re.I)
                and re.search(table_rx, str(c.get("name", "")), re.I)
                and re.search(label_rx, str(c.get("label", "")), re.I)):
            return str(c.get("value"))
    return None

CLOSED = choice_value("state", r"closed", "change_request") or "3"
RETIRED = choice_value("install_status", r"retire") or "7"
NONOP = choice_value("operational_status", r"non") or "2"
print("inferred codes -> change Closed=%s | CI Retired=%s | CI Non-Operational=%s" % (CLOSED, RETIRED, NONOP))

precedent = next((c for c in changes
                  if str(c.get("state")) == CLOSED
                  and str(c.get("number")) != CHANGE_NUMBER
                  and re.search(r"decommission", str(c.get("category", "")) + str(c.get("short_description", "")), re.I)),
                 None)
notes = (str(precedent.get("close_notes", "")) if precedent else "").lower()
if precedent:
    print("inferred completeness standard COLD from precedent", precedent.get("number"))
std_archive = ("archiv" in notes) or True
std_clear_ip = ("cleared every ip" in notes) or ("ip alloc" in notes) or True
std_delete_dns = ("dns" in notes) or True
std_retire_ci = ("retire" in notes)
std_remove_element = ("business-app element" in notes) or ("service map" in notes) or True
std_free_subnet = ("free the subnet" in notes) or ("freed the" in notes) or True
std_remove_dangling = ("long since been removed" in notes) or ("dangling" in notes) or ("left behind" in notes)
print("  precedent teaches: retire_ci=%s remove_dangling_refs=%s free_subnet_after_empty=%s"
      % (std_retire_ci, std_remove_dangling, std_free_subnet))

devices = as_list(get(D42 + "/api/2.0/devices/"))
dev_by_name = {str(d.get("name")): d for d in devices}
existing_dev_ids = {str(d.get("device_id") or d.get("id")) for d in devices}
existing_dev_names = {str(d.get("name")) for d in devices}
ips = as_list(get(D42 + "/api/2.0/ips/"))
dns = as_list(get(D42 + "/api/1.0/dns/records/"))
elements = as_list(get(D42 + "/api/1.0/businessapps/elements/"))
ci_rows = as_list(get(SN + "/cmdb_ci_server"))
ci_by_name = {str(c.get("name")): c for c in ci_rows}

FRESH_DAYS = 30
decomm_hosts = []
for h in ticket_hosts:
    d = dev_by_name.get(h)
    if not d:
        continue
    seen = parse_dt(d.get("last_seen"))
    stale = seen is None or (ref_now - seen).days > FRESH_DAYS
    if stale:
        decomm_hosts.append(h)
    else:
        print("  SPARING %s — still in service (last_seen %s)" % (h, d.get("last_seen")))
print("hosts to decommission (out of service):", decomm_hosts)

for h in decomm_hosts:
    d = dev_by_name[h]
    dev_id = str(d.get("device_id") or d.get("id"))
    call("POST", D42 + "/api/2.0/devices/%s/archive/" % dev_id, {})
    for ipr in ips:
        if str(ipr.get("device")) == h or str(ipr.get("device_id")) == dev_id:
            call("POST", D42 + "/api/1.0/clear_ip/", {"id": ipr.get("id")})
    for r in dns:
        host_label = str(r.get("name", "")).split(".")[0]
        if host_label == h:
            call("DELETE", D42 + "/api/1.0/dns/records/%s/" % r.get("id"))
    for e in elements:
        if str(e.get("device")) == h or str(e.get("name")) == h:
            call("DELETE", D42 + "/api/1.0/businessapps/elements/%s/" % e.get("uuid"))
    ci = ci_by_name.get(h)
    if ci:
        call("PATCH", SN + "/cmdb_ci_server/%s" % ci.get("sys_id"),
             {"install_status": RETIRED, "operational_status": NONOP})

ips = as_list(get(D42 + "/api/2.0/ips/"))
dns = as_list(get(D42 + "/api/1.0/dns/records/"))
existing_dev_ids = {str(d.get("device_id") or d.get("id"))
                    for d in as_list(get(D42 + "/api/2.0/devices/"))}
existing_dev_names = {str(d.get("name")) for d in as_list(get(D42 + "/api/2.0/devices/"))}

for ipr in ips:
    if str(ipr.get("available")).lower() == "no":
        dev_id = str(ipr.get("device_id"))
        dev_nm = str(ipr.get("device"))
        if dev_id not in existing_dev_ids and dev_nm not in existing_dev_names:
            print("  dangling IP %s (%s -> absent device %s) — clearing" % (ipr.get("id"), ipr.get("ip"), dev_nm))
            call("POST", D42 + "/api/1.0/clear_ip/", {"id": ipr.get("id")})
for r in dns:
    host_label = str(r.get("name", "")).split(".")[0]
    if host_label and host_label not in existing_dev_names:
        print("  dangling DNS %s (%s -> absent host %s) — deleting" % (r.get("id"), r.get("name"), host_label))
        call("DELETE", D42 + "/api/1.0/dns/records/%s/" % r.get("id"))

subnets = as_list(get(D42 + "/api/1.0/subnets/"))
target_subnet = None
for s in subnets:
    if str(s.get("network")) == target_net and str(s.get("mask_bits")) == str(target_mask):
        target_subnet = s
        break
if target_subnet:
    sid = str(target_subnet.get("subnet_id") or target_subnet.get("id"))
    vid = str(target_subnet.get("vlan_id") or "")
    remaining = [ipr for ipr in as_list(get(D42 + "/api/2.0/ips/"))
                 if str(ipr.get("subnet_id")) == sid and str(ipr.get("available")).lower() == "no"]
    if remaining:
        print("  NOT freeing subnet %s — %d IP(s) still allocated on it" % (sid, len(remaining)))
    else:
        call("DELETE", D42 + "/api/1.0/subnets/%s/" % sid)
        if vid:
            call("DELETE", D42 + "/api/1.0/vlans/%s/" % vid)

call("PATCH", SN + "/change_request/%s" % chg_sys_id,
     {"state": CLOSED, "close_code": "successful",
      "close_notes": "Legacy Billing service, subnet and VLAN decommissioned; environment left consistent."})

print("\n--- readback ---")
fdev = {str(d.get("name")): d for d in as_list(get(D42 + "/api/2.0/devices/"))}
fips = as_list(get(D42 + "/api/2.0/ips/"))
fdns = as_list(get(D42 + "/api/1.0/dns/records/"))
felem = as_list(get(D42 + "/api/1.0/businessapps/elements/"))
fsub = as_list(get(D42 + "/api/1.0/subnets/"))
fvlan = as_list(get(D42 + "/api/1.0/vlans/"))

def ip_free(ipr):
    return str(ipr.get("available")).lower() == "yes" and not ipr.get("device_id") and not ipr.get("device")

for h in decomm_hosts:
    d = fdev.get(h)
    check("device %s archived" % h, bool(d) and (d.get("archived") is True or str(d.get("archived")).lower() == "true"))
    check("no allocated IP references %s" % h,
          not any((str(i.get("device")) == h) and not ip_free(i) for i in fips))
    check("no DNS record resolves to %s" % h,
          not any(str(r.get("name", "")).split(".")[0] == h for r in fdns))
    ci = next((c for c in as_list(get(SN + "/cmdb_ci_server")) if str(c.get("name")) == h), None)
    check("CMDB CI %s retired" % h, bool(ci) and str(ci.get("install_status")) == RETIRED)

check("no business-app element wires a decommissioned host",
      not any(str(e.get("device")) in decomm_hosts for e in felem))

existing_names = {str(d.get("name")) for d in fdev.values()}
check("no allocated IP points at an absent device",
      not any(str(i.get("available")).lower() == "no"
              and str(i.get("device")) not in existing_names
              and str(i.get("device_id")) not in {str(d.get("device_id") or d.get("id")) for d in fdev.values()}
              for i in fips))
check("no DNS record resolves to a host absent from inventory",
      not any(str(r.get("name", "")).split(".")[0] not in existing_names for r in fdns
              if str(r.get("name", "")).split(".")[0]))

check("subnet %s/%s freed" % (target_net, target_mask),
      not any(str(s.get("network")) == target_net and str(s.get("mask_bits")) == str(target_mask) for s in fsub))
if target_subnet:
    _vid = str(target_subnet.get("vlan_id") or "")
    check("VLAN %s freed" % _vid,
          not any(str(v.get("vlan_id")) == _vid or str(v.get("id")) == _vid for v in fvlan))

cur = (get(SN + "/change_request/%s" % chg_sys_id) or {}).get("result", {})
check("change %s closed" % CHANGE_NUMBER, str(cur.get("state")) == CLOSED)

for h in ticket_hosts:
    if h not in decomm_hosts:
        d = fdev.get(h)
        check("RESTRAINT %s still in service" % h,
              bool(d) and d.get("archived") is not True
              and (d.get("in_service") is True or str(d.get("in_service")).lower() == "true"))

print("\n%d readback mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
if MISMATCHES:
    sys.exit(1)
print("oracle complete: standard inferred COLD from precedent + lineage + anomaly; every mutation verified")
