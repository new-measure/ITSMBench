#!/usr/bin/env python3

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

SN = "http://servicenow.local.mock:8080"
CS = "http://crowdstrike.local.mock:8080"
INTUNE = "http://microsoft-intune.local.mock:8080"
SNIPE = "http://snipeit.local.mock:8080/api/v1"
M365 = "http://microsoft-365.local.mock:8080"
ZOOM = "http://zoom-admin.local.mock:8080"

RESPONDER = "IT Security Operations"
TIMEOUT = 30

def fail(msg):
    print(f"ORACLE-FAIL: {msg}", file=sys.stderr)
    sys.exit(1)

def log(msg):
    print(f"[oracle] {msg}", file=sys.stderr)

def http(method, url, body=None, headers=None):
    data = None
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.getcode()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        status = exc.code
    except urllib.error.URLError as exc:
        fail(f"cannot reach {url}: {exc}")
    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        parsed = raw
    return status, parsed

def get(url):
    return http("GET", url)

def sn_list(table, query=None, extra=None):
    params = {}
    if query:
        params["sysparm_query"] = query
    if extra:
        params.update(extra)
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    status, data = get(f"{SN}/api/now/table/{table}{qs}")
    if status != 200 or not isinstance(data, dict):
        return []
    result = data.get("result", [])
    return result if isinstance(result, list) else []

def cs_resources(path):
    status, data = get(f"{CS}{path}")
    if isinstance(data, dict):
        return data.get("resources", []) or []
    return []

def fql_eq(field, value):
    return urllib.parse.quote(f"{field}:'{value}'", safe="")

def find_incident():
    candidates = sn_list("incident", "active=true^descriptionLIKEslow")
    if not candidates:
        candidates = sn_list("incident", "active=true")
    if not candidates:
        candidates = sn_list("incident")

    def score(rec):
        text = " ".join(
            str(rec.get(f, "")) for f in ("short_description", "description")
        ).lower()
        return sum(
            1 for kw in ("slow", "update", "zoom", "chrome", "freeze", "crash") if kw in text
        )

    scored = sorted(candidates, key=score, reverse=True)
    if not scored or score(scored[0]) < 2:
        fail("could not find the reported 'slow after update' incident")
    return scored[0]

def resolve_ref(value):
    if isinstance(value, dict):
        return value.get("value") or value.get("display_value") or ""
    return value or ""

def get_user(sys_id):
    if not sys_id:
        return {}
    status, data = get(f"{SN}/api/now/table/sys_user/{sys_id}")
    if status == 200 and isinstance(data, dict):
        return data.get("result", {}) or {}
    return {}

def snipe_asset_for(email, name):
    term = email or name
    status, data = get(f"{SNIPE}/users?{urllib.parse.urlencode({'search': term})}")
    rows = data.get("rows", []) if isinstance(data, dict) else []
    user = None
    for row in rows:
        if email and str(row.get("email", "")).lower() == email.lower():
            user = row
            break
    if user is None and rows:
        user = rows[0]
    if not user:
        return None, None
    uid = user.get("id")
    status, data = get(f"{SNIPE}/users/{uid}/assets")
    assets = data.get("rows", []) if isinstance(data, dict) else []
    laptop = None
    for asset in assets:
        if asset.get("serial"):
            laptop = asset
            break
    if laptop is None and assets:
        laptop = assets[0]
    if not laptop:
        return None, None
    return laptop, laptop.get("serial")

def cs_device(serial, hostname_hint):
    devices = []
    if serial:
        devices = cs_resources(
            f"/devices/combined/devices/v1?filter={fql_eq('serial_number', serial)}"
        )
    if not devices and hostname_hint:
        devices = cs_resources(
            f"/devices/combined/devices/v1?filter={fql_eq('hostname', hostname_hint)}"
        )
    return devices[0] if devices else None

def cs_alerts_for(device_id, hostname):
    alerts = cs_resources(
        f"/alerts/combined/alerts/v1?filter={fql_eq('agent_id', device_id)}"
    )
    if not alerts and hostname:
        alerts = cs_resources(
            f"/alerts/combined/alerts/v1?filter={fql_eq('device.hostname', hostname)}"
        )
    return alerts

def intel_confirms(sha256):
    inds = cs_resources(
        f"/intel/combined/indicators/v1?filter={fql_eq('indicator', sha256)}"
    )
    if not inds:
        inds = cs_resources(f"/intel/combined/indicators/v1?q={urllib.parse.quote(sha256)}")
    for ind in inds:
        conf = str(ind.get("malicious_confidence", "")).lower()
        fams = ind.get("malware_families") or []
        if conf in ("high", "medium") or fams:
            return ind
    return None

def intune_device(serial, upn):
    def query(flt):
        url = f"{INTUNE}/v1.0/deviceManagement/managedDevices?{urllib.parse.urlencode({'$filter': flt})}"
        status, data = get(url)
        if isinstance(data, dict):
            return data.get("value", []) or []
        return []

    devices = []
    if serial:
        devices = query(f"serialNumber eq '{serial}'")
    if not devices and upn:
        devices = query(f"userPrincipalName eq '{upn}'")
    if not devices:
        url = f"{INTUNE}/v1.0/deviceManagement/managedDevices?{urllib.parse.urlencode({'$top': 999})}"
        status, data = get(url)
        alld = data.get("value", []) if isinstance(data, dict) else []
        for d in alld:
            if serial and str(d.get("serialNumber", "")) == str(serial):
                devices = [d]
                break
            if upn and str(d.get("userPrincipalName", "")).lower() == str(upn).lower():
                devices = [d]
                break
    return devices[0] if devices else None

def main():
    log("Discovery: locating the incident")
    incident = find_incident()
    inc_id = incident.get("sys_id")
    log(f"incident {incident.get('number')} ({inc_id})")

    caller_id = resolve_ref(incident.get("caller_id"))
    caller = get_user(caller_id)
    email = caller.get("email", "")
    name = caller.get("name", "")
    if not (email or name):
        fail("incident has no resolvable caller_id -> sys_user identity")
    log(f"caller: {name} <{email}>")

    laptop, serial = snipe_asset_for(email, name)
    if not laptop:
        fail("could not resolve the caller's laptop asset in Snipe-IT")
    asset_id = laptop.get("id")
    asset_name = laptop.get("name") or laptop.get("asset_tag")
    log(f"asset id={asset_id} serial={serial} name={asset_name}")

    device = cs_device(serial, asset_name)
    if not device:
        fail("caller's device not found in CrowdStrike (serial/hostname join failed)")
    device_id = device.get("device_id")
    hostname = device.get("hostname")
    contained = str(device.get("status", "")).lower() == "contained"
    log(f"crowdstrike device {hostname} ({device_id}) status={device.get('status')}")
    if not contained:
        fail("device is not CONTAINED in CrowdStrike; the diagnosed reality does not hold")

    alerts = cs_alerts_for(device_id, hostname)
    detection = None
    for alert in alerts:
        status_new = str(alert.get("status", "")).lower() in ("new", "in_progress")
        try:
            sev = float(alert.get("severity", 0))
        except (TypeError, ValueError):
            sev = 0
        if status_new and sev >= 70 and alert.get("sha256"):
            detection = alert
            break
    if not detection:
        fail("no active high-severity CrowdStrike detection with a sha256 on the device")
    sha256 = detection.get("sha256")
    composite_id = detection.get("composite_id")
    log(f"detection {composite_id} sev={detection.get('severity')} sha256={sha256}")

    intel = intel_confirms(sha256)
    if not intel:
        fail(f"CrowdStrike intel does not confirm sha256 {sha256} as malicious")
    log(f"intel confirms malware: {intel.get('malware_families')}")

    itd = intune_device(serial, email)
    if not itd:
        fail("device not found in Intune to verify the update is healthy")
    compliance = str(itd.get("complianceState", "")).lower()
    if compliance and compliance != "compliant":
        fail(f"Intune device is {compliance}, not compliant; blamed update may be real")
    log(
        f"intune device {itd.get('id')} compliance={itd.get('complianceState')} "
        f"lastSync={itd.get('lastSyncDateTime')} (blamed update is healthy)"
    )
    itd_id = itd.get("id")

    existing_iocs = [
        i
        for i in cs_resources(
            f"/iocs/combined/indicator/v1?filter={fql_eq('value', sha256)}"
        )
        if not i.get("deleted")
    ]
    log(f"existing non-deleted IOCs for hash: {len(existing_iocs)}")

    already = [i for i in existing_iocs if str(i.get("action", "")).lower() == "prevent"]
    to_escalate = [i for i in existing_iocs if str(i.get("action", "")).lower() != "prevent"]
    if already:
        log("step1: hash already blocked (prevent) -> no-op")
    elif to_escalate:
        ioc = to_escalate[0]
        status, data = http(
            "PATCH",
            f"{CS}/iocs/entities/indicators/v1",
            {"indicators": [{"id": ioc.get("id"), "action": "prevent"}]},
        )
        if status not in (200, 201):
            fail(f"failed to escalate IOC to prevent: {status} {data}")
        log("step1: escalated existing detect IOC -> prevent")
    else:
        status, data = http(
            "POST",
            f"{CS}/iocs/entities/indicators/v1",
            {
                "indicators": [
                    {
                        "type": "sha256",
                        "value": sha256,
                        "action": "prevent",
                        "severity": "high",
                        "platforms": ["windows"],
                        "description": "Confirmed malware on contained endpoint (ticket remediation)",
                        "source": "incident-response",
                    }
                ]
            },
        )
        if status not in (200, 201):
            fail(f"failed to create prevent IOC: {status} {data}")
        log("step1: created prevent IOC for hash")

    status, _ = http(
        "POST", f"{INTUNE}/v1.0/deviceManagement/managedDevices/{itd_id}/windowsDefenderScan", {}
    )
    if status not in (200, 202, 204):
        fail(f"failed to trigger Intune Defender scan: {status}")
    log("step2: Intune Defender scan triggered")

    status, data = http(
        "POST",
        f"{CS}/devices/entities/devices-actions/v2?action_name=lift_containment",
        {"ids": [device_id]},
    )
    if status not in (200, 202):
        fail(f"failed to lift containment: {status} {data}")
    log("step3: containment lifted (device -> normal)")

    status, _ = http(
        "POST", f"{INTUNE}/v1.0/deviceManagement/managedDevices/{itd_id}/syncDevice", {}
    )
    if status not in (200, 202, 204):
        fail(f"failed to sync device: {status}")
    log("step4: Intune sync forced")

    status, data = http(
        "PATCH",
        f"{CS}/alerts/entities/alerts/v3",
        {
            "composite_ids": [composite_id],
            "action_parameters": [
                {"name": "update_status", "value": "closed"},
                {"name": "assign_to_name", "value": RESPONDER},
            ],
        },
    )
    if status != 200:
        fail(f"failed to resolve/assign alert: {status} {data}")
    log("step5+6: alert closed and assigned")

    status, data = http(
        "PATCH",
        f"{SN}/api/now/table/incident/{inc_id}",
        {
            "category": "security",
            "work_notes": (
                "Reclassified: root cause is a confirmed CrowdStrike malware "
                "detection and resulting network containment, not the OS update."
            ),
        },
    )
    if status != 200:
        fail(f"failed to reclassify incident: {status} {data}")
    log("step7: incident category -> security")

    families = ",".join(intel.get("malware_families") or []) or "n/a"
    root_cause = (
        f"Confirmed malware (sha256 {sha256}, families {families}) executing on "
        f"{hostname}; CrowdStrike network containment made the endpoint appear "
        f"'slow' and broke Zoom/Chrome. The blamed OS/app update was healthy "
        f"(Intune compliant). Remediated: hash blocked, host scanned, containment "
        f"lifted."
    )
    status, data = http(
        "POST",
        f"{SN}/api/now/table/problem",
        {
            "short_description": f"Malware on {hostname} misreported as a slow-after-update issue",
            "root_cause": root_cause,
            "u_product_area": "endpoint security",
        },
    )
    if status not in (200, 201):
        fail(f"failed to create problem record: {status} {data}")
    prb = (data or {}).get("result", {}) if isinstance(data, dict) else {}
    log(f"step8: problem {prb.get('number')} opened")

    status, data = http(
        "PATCH",
        f"{SN}/api/now/table/incident/{inc_id}",
        {
            "state": "7",
            "active": False,
            "close_code": "Solved (Permanently)",
            "close_notes": (
                "Root cause was NOT the update. CrowdStrike detected malware "
                f"(sha256 {sha256}) on {hostname} and network-contained the host, "
                "which is what made it slow and broke Zoom/Chrome. Blocked the hash "
                "(prevent), ran an endpoint AV scan, lifted containment, resolved the "
                f"EDR detection, and opened {prb.get('number', 'a Problem')}. The OS/app "
                "update was verified healthy (Intune compliant) and left in place."
            ),
        },
    )
    if status != 200:
        fail(f"failed to close incident: {status} {data}")
    log("step9: incident closed (state 7)")

    status, data = http("POST", f"{SNIPE}/hardware/audit", {"id": asset_id})
    if isinstance(data, dict) and data.get("status") == "error":
        fail(f"failed to audit asset: {data.get('messages')}")
    log("step10: asset audited")

    log("DONE: real cause remediated, containment lifted, ticket closed, update untouched")

if __name__ == "__main__":
    main()
