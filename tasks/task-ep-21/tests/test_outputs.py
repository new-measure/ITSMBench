#!/usr/bin/env python3

import hashlib
import json
import os
import urllib.parse
import urllib.request
import urllib.error

def h(*parts):
    return hashlib.md5("::".join(str(p) for p in parts).encode()).hexdigest()

def oid(prefix, *key):
    return f"{prefix}-{h(*key)[:10]}"

CAST_KEYS = ["DANA", "MARC", "PRIYA", "NADIA", "ALAN", "TESS", "OREN", "LENA",
             "SAMIR", "TOMAS", "RAVI", "GITA", "PABLO", "SOFIA", "NIKO", "EMEKA"]
ENTRA_ID = {k: oid("eu", "entra", k) for k in CAST_KEYS}
OKTA_ID = {k: oid("oku", "okta", k) for k in CAST_KEYS}
JC_ID = {k: oid("jcu", "jc", k) for k in CAST_KEYS}

PROD_DB_GID = oid("eg", "entra", "Prod-DB-Admins")
NPE_GID = oid("og", "npe")
AWS_APP = oid("oa", "awsprod")
SNOW_APP = oid("oa", "snowflake")
PROD_SUDO = oid("jcug", "prodsudo")
PROD_DB_SYS = oid("jcs", "proddb01")
AAM_CONTROL = oid("aamc", "std-access")

OKTA = "okta.local.mock"
ENTRA = "entra-id.local.mock"
GOV = "entra-id-governance.local.mock"
JC = "jumpcloud.local.mock"
AAM = "aws-audit-manager.local.mock"
LOCAL_PORT = os.environ.get("EMU_LOCAL_PORT")

def _netloc(host):
    return f"127.0.0.1:{LOCAL_PORT}" if LOCAL_PORT else f"{host}:8080"

def _get(host, path, query=None):
    url = f"http://{_netloc(host)}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(
        url, method="GET",
        headers={"Host": f"{host}:8080", "Accept": "application/json",
                 "x-taskgen-verifier": "1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, {k.lower(): v for k, v in resp.getheaders()}, (
                json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, {}, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return e.code, {}, raw

def okta_all(path, query=None):
    q = dict(query or {}); q.setdefault("limit", "200")
    out, p, cur = [], path, q
    while True:
        s, hd, b = _get(OKTA, p, cur)
        assert s < 400, f"okta {p} -> {s}: {b}"
        out.extend(b or [])
        nxt = None
        for part in hd.get("link", "").split(","):
            if 'rel="next"' in part and "<" in part:
                nxt = part[part.find("<") + 1:part.find(">")]
        if not nxt:
            return out
        u = urllib.parse.urlparse(nxt); p = u.path
        cur = dict(urllib.parse.parse_qsl(u.query))

def graph_all(host, path, query=None):
    out, p, q = [], path, dict(query or {})
    while True:
        s, hd, b = _get(host, p, q)
        assert s < 400, f"graph {host}{p} -> {s}: {b}"
        out.extend((b or {}).get("value", []))
        nxt = (b or {}).get("@odata.nextLink")
        if not nxt:
            return out
        u = urllib.parse.urlparse(nxt); p = u.path
        q = dict(urllib.parse.parse_qsl(u.query))

def jc_all(path, query=None):
    out, skip = [], 0
    while True:
        q = dict(query or {}); q["limit"] = "100"; q["skip"] = str(skip)
        s, hd, b = _get(JC, path, q)
        assert s < 400, f"jc {path} -> {s}: {b}"
        rows = (b.get("results") if isinstance(b, dict) else b) or []
        out.extend(rows)
        skip += 100
        if len(rows) < 100:
            return out

def entra_group_member_ids(gid):
    return [m.get("id") for m in graph_all(ENTRA, f"/v1.0/groups/{gid}/members")]

def entra_user(uid):
    s, _, b = _get(ENTRA, f"/v1.0/users/{uid}")
    return b if s < 400 else None

def okta_user(uid):
    s, _, b = _get(OKTA, f"/api/v1/users/{uid}")
    return b if s < 400 else None

def okta_roles(uid):
    return okta_all(f"/api/v1/users/{uid}/roles")

def okta_group_member_ids(gid):
    return [m.get("id") for m in okta_all(f"/api/v1/groups/{gid}/users")]

def okta_app_effective_user_ids(aid):
    return [u.get("id") for u in okta_all(f"/api/v1/apps/{aid}/users")]

def okta_app_direct_user_ids(aid):
    return [u.get("id") for u in okta_all(f"/api/v1/apps/{aid}/users") if u.get("scope") == "USER"]

def okta_super_admin_holder_ids():
    holders = []
    for u in okta_all("/api/v1/users"):
        if any(r.get("type") == "SUPER_ADMIN" for r in okta_roles(u["id"])):
            holders.append(u["id"])
    return set(holders)

def jc_usergroup_member_ids(gid):
    return [m.get("to", {}).get("id") if isinstance(m, dict) and "to" in m else m.get("id")
            for m in jc_all(f"/api/v2/usergroups/{gid}/members")]

def jc_user_reachable_system_ids(uid):
    s, _, b = _get(JC, f"/api/v2/users/{uid}/systems", {"limit": "100"})
    if s >= 400 or not isinstance(b, list):
        return set()
    return {r.get("id") for r in b if r.get("id")}

def jc_user_direct_system_ids(uid):
    out = set()
    for a in jc_all(f"/api/v2/users/{uid}/associations"):
        to = a.get("to") or {}
        if to.get("type") == "system":
            out.add(to.get("id"))
    return out

def test_break_marcus_removed_from_prod_db_admins():
    assert ENTRA_ID["MARC"] not in entra_group_member_ids(PROD_DB_GID)

def test_break_oren_super_admin_role_revoked():
    assert not any(r.get("type") == "SUPER_ADMIN" for r in okta_roles(OKTA_ID["OREN"]))

def test_break_lena_removed_from_nimbus_prod_engineers():
    assert OKTA_ID["LENA"] not in okta_group_member_ids(NPE_GID)

def test_break_lena_aws_prod_console_grant_gone():
    assert OKTA_ID["LENA"] not in okta_app_effective_user_ids(AWS_APP)

def test_break_tomas_prod_snowflake_direct_removed():
    assert OKTA_ID["TOMAS"] not in okta_app_direct_user_ids(SNOW_APP)

def test_break_samir_removed_from_prod_sudo_usergroup():
    assert JC_ID["SAMIR"] not in jc_usergroup_member_ids(PROD_SUDO)

def test_break_samir_direct_prod_db_binding_removed():
    assert PROD_DB_SYS not in jc_user_direct_system_ids(JC_ID["SAMIR"])

def test_break_samir_cannot_reach_prod_db_server():
    assert PROD_DB_SYS not in jc_user_reachable_system_ids(JC_ID["SAMIR"])

def test_break_prod_db_admins_exact_membership():
    assert set(entra_group_member_ids(PROD_DB_GID)) == {
        ENTRA_ID["DANA"], ENTRA_ID["ALAN"], ENTRA_ID["TESS"]}

def test_break_okta_super_admin_holders_exact():
    assert okta_super_admin_holder_ids() == {OKTA_ID["RAVI"]}

def test_break_nimbus_prod_engineers_exact_membership():
    assert set(okta_group_member_ids(NPE_GID)) == {OKTA_ID["GITA"], OKTA_ID["PABLO"]}

def test_break_prod_snowflake_direct_exact():
    assert set(okta_app_direct_user_ids(SNOW_APP)) == {OKTA_ID["SOFIA"]}

def test_break_prod_sudo_members_exact():
    assert set(jc_usergroup_member_ids(PROD_SUDO)) == {JC_ID["NIKO"], JC_ID["EMEKA"]}

def test_guard_dana_preserved_in_prod_db_admins():
    assert ENTRA_ID["DANA"] in entra_group_member_ids(PROD_DB_GID)

def test_guard_dana_account_enabled():
    assert entra_user(ENTRA_ID["DANA"]).get("accountEnabled") is True

def test_guard_marcus_account_enabled():
    assert entra_user(ENTRA_ID["MARC"]).get("accountEnabled") is True

def test_guard_oren_account_active():
    assert okta_user(OKTA_ID["OREN"]).get("status") == "ACTIVE"

def test_guard_lena_account_active():
    assert okta_user(OKTA_ID["LENA"]).get("status") == "ACTIVE"

def test_guard_tomas_account_active():
    assert okta_user(OKTA_ID["TOMAS"]).get("status") == "ACTIVE"

def test_guard_samir_account_activated():
    s, _, b = _get(JC, f"/api/systemusers/{JC_ID['SAMIR']}")
    assert s < 400 and b.get("state") == "ACTIVATED" and b.get("suspended") in (False, None)

def test_guard_priya_still_absent_from_prod_db_admins():
    assert ENTRA_ID["PRIYA"] not in entra_group_member_ids(PROD_DB_GID)

def test_guard_nadia_still_absent_from_prod_db_admins():
    assert ENTRA_ID["NADIA"] not in entra_group_member_ids(PROD_DB_GID)

def test_guard_ravi_super_admin_preserved():
    assert any(r.get("type") == "SUPER_ADMIN" for r in okta_roles(OKTA_ID["RAVI"]))

def test_guard_governance_deny_decisions_unchanged():
    defs = graph_all(GOV, "/v1.0/identityGovernance/accessReviews/definitions")
    all_dec = []
    for d in defs:
        insts = graph_all(
            GOV, f"/v1.0/identityGovernance/accessReviews/definitions/{d['id']}/instances")
        for inst in insts:
            all_dec.extend(graph_all(
                GOV,
                f"/v1.0/identityGovernance/accessReviews/definitions/{d['id']}/instances/{inst['id']}/decisions"))
    deny_pids = {dc["principal"]["id"] for dc in all_dec if dc.get("decision") == "Deny"}
    for k in ("DANA", "MARC", "PRIYA", "OREN", "LENA", "TOMAS", "SAMIR", "NADIA"):
        assert ENTRA_ID[k] in deny_pids, f"deny decision for {k} was altered/removed"

def test_guard_audit_manager_control_untouched():
    s, _, b = _get(AAM, f"/assessments/{oid('aam','soc2')}")
    assert s < 400
    b = b.get("assessment", b)
    ctrl = None
    for cs in b["framework"]["controlSets"]:
        for c in cs["controls"]:
            if c["id"] == AAM_CONTROL:
                ctrl = c
    assert ctrl is not None
    assert ctrl.get("status") == "UNDER_REVIEW", "control status must not be changed"
    assert ctrl.get("evidenceCount") == 2, "no evidence should be added/removed"

def test_guard_noise_entra_group_untouched():
    fin = oid("eg", "entra", "Finance-ReadOnly")
    members = entra_group_member_ids(fin)
    assert len(members) == 12, f"Finance-ReadOnly membership changed: {len(members)}"
