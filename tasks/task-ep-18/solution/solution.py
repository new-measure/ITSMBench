#!/usr/bin/env python3
import json, os, sys, urllib.request, urllib.error, urllib.parse

TRIGGER = "INC0010478"
FIX = (7, 4, 2)
EMU_BASE = os.environ.get("EMU_BASE")

def _host(slug): return f"{slug}.local.mock"

def req(slug, method, path, body=None, query=None):
    if query:
        path += ("&" if "?" in path else "?") + urllib.parse.urlencode(query, doseq=True)
    url = (EMU_BASE + path) if EMU_BASE else (f"http://{_host(slug)}:8080" + path)
    data = None
    headers = {"Host": _host(slug)}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        if e.code >= 500:
            die(f"{method} {slug}{path} -> HTTP {e.code}: {raw[:200]}")
        return {"__status": e.code, "__raw": raw}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"__raw": raw}

def die(msg):
    print(f"ORACLE ABORT: {msg}", file=sys.stderr); sys.exit(2)

def parse_ver(v):
    try: return tuple(int(x) for x in str(v).split("."))
    except Exception: return None
def vuln(v):
    pv = parse_ver(v); return pv is not None and pv < FIX

def cs_combined(path, key="resources", page=100):
    out, off = [], 0
    while True:
        env = req("crowdstrike", "GET", path, query={"limit": page, "offset": off})
        res = env.get(key, [])
        out.extend(res)
        total = env.get("meta", {}).get("pagination", {}).get("total", len(out))
        off += page
        if off >= total or not res: break
    return out

def sn_table(table, query=None):
    out, off = [], 0
    while True:
        q = {"sysparm_limit": 100, "sysparm_offset": off}
        if query: q["sysparm_query"] = query
        res = req("servicenow", "GET", f"/api/now/table/{table}", query=q).get("result", [])
        out.extend(res); off += 100
        if len(res) < 100: break
    return out

def d42_all():
    out, off = [], 0
    while True:
        env = req("device42", "GET", "/api/1.0/devices/all/", query={"limit": 100, "offset": off})
        devs = env.get("devices", []); out.extend(devs)
        total = env.get("total_count", len(out)); off += 100
        if off >= total or not devs: break
    return out

def jc_systems():
    out, skip = [], 0
    while True:
        env = req("jumpcloud", "GET", "/api/systems", query={"limit": 100, "skip": skip})
        res = env.get("results", []); out.extend(res)
        total = env.get("totalCount", len(out)); skip += 100
        if skip >= total or not res: break
    return out

def intune_devices():
    out = []
    env = req("microsoft-intune", "GET", "/v1.0/deviceManagement/managedDevices")
    while True:
        out.extend(env.get("value", []))
        nxt = env.get("@odata.nextLink")
        if not nxt: break
        p = urllib.parse.urlparse(nxt); env = req("microsoft-intune", "GET", p.path + ("?" + p.query if p.query else ""))
    return out

def main():
    inc = sn_table("incident", query=f"number={TRIGGER}")
    if not inc: die(f"trigger incident {TRIGGER} not found")
    inc = inc[0]
    flagged = inc.get("cmdb_ci", "")
    print(f"[trigger] {TRIGGER}: flagged host = {flagged!r}")

    groups = cs_combined("/devices/combined/host-groups/v1")
    dep = next((g for g in groups if "patchwave" in (g["name"] + g.get("description", "")).lower()), None)
    hold = next((g for g in groups if "hold" in (g["name"] + g.get("description", "")).lower()), None)
    if not dep: die("could not identify deployment host group")
    if not hold: die("could not identify hold host group")
    DEP, HOLD = dep["id"], hold["id"]
    print(f"[groups] deployment={dep['name']} ({DEP})  hold={hold['name']} ({HOLD})")

    cs_devices = cs_combined("/devices/combined/devices/v1")
    cs_by_host = {d["hostname"].casefold(): d for d in cs_devices}
    spot = cs_combined("/spotlight/combined/vulnerabilities/v1")
    computers = sn_table("cmdb_ci_computer")
    sn_by_host = {c["name"].casefold(): c for c in computers}
    d42 = d42_all()
    d42_by_host = {d["name"].casefold(): d for d in d42}
    jc = jc_systems()
    jc_by_host = {s.get("hostname", s.get("displayName", "")).casefold(): s for s in jc}

    def d42_field(rec, key):
        for f in rec.get("custom_fields", []) or []:
            if (f.get("key") or f.get("name")) == key: return f.get("value")
        return None

    def installed_version(host):
        if host in sn_by_host and sn_by_host[host].get("u_pulselink_version"):
            return sn_by_host[host]["u_pulselink_version"]
        if host in d42_by_host:
            v = d42_field(d42_by_host[host], "pulselink_version")
            if v: return v
        if host in jc_by_host and jc_by_host[host].get("pulselink_version"):
            return jc_by_host[host]["pulselink_version"]
        return None

    def in_scope(host):
        if host in sn_by_host:
            c = sn_by_host[host]
            if str(c.get("u_environment", "")).lower() not in ("production", ""): return False
            if str(c.get("u_patch_status", "")).lower() == "exempt": return False
            if str(c.get("install_status", "")) == "7": return False
        elif host in d42_by_host:
            if str(d42_by_host[host].get("service_level", "")).lower() not in ("production", ""): return False
        return True

    all_hosts = set(cs_by_host) | set(sn_by_host) | set(d42_by_host) | set(jc_by_host)
    footprint = []
    for host in sorted(all_hosts):
        v = installed_version(host)
        if not vuln(v): continue
        if not in_scope(host): continue
        if host not in cs_by_host:
            print(f"[warn] {host}: vulnerable but no CrowdStrike sensor; skipping"); continue
        footprint.append(host)

    fv = installed_version(flagged.casefold())
    if vuln(fv):
        print(f"[note] flagged host {flagged} is genuinely vulnerable ({fv})")
    else:
        print(f"[premise] flagged host {flagged} installed version {fv} >= fix -> already patched (false positive); not acting on it")

    print(f"[footprint] {len(footprint)} truly-vulnerable in-scope host(s): {footprint}")

    plan = []
    for host in footprint:
        d = cs_by_host[host]; g = set(d.get("groups", []))
        acts = []
        if DEP not in g: acts.append(("add_dep", d["device_id"]))
        if HOLD in g: acts.append(("rm_hold", d["device_id"]))
        if d.get("hidden"): acts.append(("unhide", d["device_id"]))
        if acts: plan.append((host, acts))
    for host, acts in plan:
        print(f"[plan] {host}: {[a for a, _ in acts]}")

    for host, acts in plan:
        for act, did in acts:
            if act == "add_dep":
                r = req("crowdstrike", "POST", "/devices/entities/host-group-actions/v1?action_name=add-hosts",
                        body={"ids": [DEP], "action_parameters": [{"name": "filter", "value": f"(device_id:['{did}'])"}]})
            elif act == "rm_hold":
                r = req("crowdstrike", "POST", "/devices/entities/host-group-actions/v1?action_name=remove-hosts",
                        body={"ids": [HOLD], "action_parameters": [{"name": "filter", "value": f"(device_id:['{did}'])"}]})
            elif act == "unhide":
                r = req("crowdstrike", "POST", "/devices/entities/devices-actions/v2?action_name=unhide_host",
                        body={"ids": [did]})
            if isinstance(r, dict) and r.get("__status", 200) >= 400:
                die(f"{act} on {host} failed: {r}")

    ids = [cs_by_host[h]["device_id"] for h in footprint]
    if ids:
        detail = req("crowdstrike", "POST", "/devices/entities/devices/v2", body={"ids": ids})
        by_id = {d["device_id"]: d for d in detail.get("resources", [])}
        for host in footprint:
            d = by_id[cs_by_host[host]["device_id"]]; g = set(d.get("groups", []))
            if DEP not in g: die(f"readback: {host} not in deployment group")
            if HOLD in g: die(f"readback: {host} still in hold group")
            if d.get("hidden"): die(f"readback: {host} still hidden")
    print(f"[done] remediated {len(footprint)} host(s); all readbacks OK")

if __name__ == "__main__":
    main()
