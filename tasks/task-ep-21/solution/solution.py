#!/usr/bin/env python3

import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error

TRIGGER_PRINCIPAL_NAME = "Dana Whitfield"

OKTA = "okta.local.mock"
ENTRA = "entra-id.local.mock"
GOV = "entra-id-governance.local.mock"
JC = "jumpcloud.local.mock"
AAM = "aws-audit-manager.local.mock"

LOCAL_PORT = os.environ.get("EMU_LOCAL_PORT")
VERIFIER = os.environ.get("EMU_VERIFIER") == "1"

WRITES = []

def _netloc(host):
    return f"127.0.0.1:{LOCAL_PORT}" if LOCAL_PORT else f"{host}:8080"

def request(method, host, path, query=None, body=None):
    url = f"http://{_netloc(host)}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    headers = {"Host": f"{host}:8080", "Accept": "application/json"}
    if VERIFIER:
        headers["x-taskgen-verifier"] = "1"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            hdrs = {k.lower(): v for k, v in resp.getheaders()}
            try:
                return resp.status, hdrs, json.loads(raw) if raw else None
            except json.JSONDecodeError:
                return resp.status, hdrs, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            body = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            body = raw
        return e.code, {}, body

def okta_all(path, query=None):
    q = dict(query or {})
    q.setdefault("limit", "200")
    out = []
    host, p = OKTA, path
    cur_q = q
    while True:
        status, hdrs, body = request("GET", host, p, cur_q)
        if status >= 400:
            raise RuntimeError(f"okta GET {p} -> {status}: {body}")
        out.extend(body or [])
        link = hdrs.get("link", "")
        nxt = None
        for part in link.split(","):
            if 'rel="next"' in part:
                s = part.find("<")
                e = part.find(">")
                if s != -1 and e != -1:
                    nxt = part[s + 1:e]
        if not nxt:
            return out
        u = urllib.parse.urlparse(nxt)
        p = u.path
        cur_q = dict(urllib.parse.parse_qsl(u.query))

def graph_all(host, path, query=None):
    out = []
    q = dict(query or {})
    p = path
    while True:
        status, hdrs, body = request("GET", host, p, q)
        if status >= 400:
            raise RuntimeError(f"graph GET {host}{p} -> {status}: {body}")
        out.extend((body or {}).get("value", []))
        nxt = (body or {}).get("@odata.nextLink")
        if not nxt:
            return out
        u = urllib.parse.urlparse(nxt)
        p = u.path
        q = dict(urllib.parse.parse_qsl(u.query))

def jc_all(path, query=None):
    out = []
    skip = 0
    while True:
        q = dict(query or {})
        q["limit"] = "100"
        q["skip"] = str(skip)
        status, hdrs, body = request("GET", JC, path, q)
        if status >= 400:
            raise RuntimeError(f"jc GET {path} -> {status}: {body}")
        rows = body.get("results") if isinstance(body, dict) else body
        rows = rows or []
        out.extend(rows)
        total = None
        if "x-total-count" in hdrs:
            try:
                total = int(hdrs["x-total-count"])
            except ValueError:
                total = None
        if isinstance(body, dict) and "totalCount" in body:
            total = body.get("totalCount")
        skip += 100
        if len(rows) < 100 or (total is not None and skip >= total):
            return out

def discover_all_decisions():
    defs = graph_all(GOV, "/v1.0/identityGovernance/accessReviews/definitions")
    out = []
    for d in defs:
        did = d.get("id")
        insts = graph_all(
            GOV, f"/v1.0/identityGovernance/accessReviews/definitions/{did}/instances"
        )
        for inst in insts:
            iid = inst.get("id")
            out.extend(graph_all(
                GOV,
                f"/v1.0/identityGovernance/accessReviews/definitions/{did}/instances/{iid}/decisions",
            ))
    return out

def superseded_by_later_approval(all_decisions, deny):
    pid = deny["principal"]["id"]
    rname = (deny.get("resource") or {}).get("displayName")
    dtime = deny.get("reviewedDateTime", "")
    for d in all_decisions:
        if (str(d.get("decision", "")).lower() == "approve"
                and d["principal"]["id"] == pid
                and (d.get("resource") or {}).get("displayName") == rname
                and str(d.get("reviewedDateTime", "")) > str(dtime)):
            return True
    return False

def reapproved_principal_ids():
    ids = set()
    reqs = graph_all(
        GOV, "/v1.0/identityGovernance/entitlementManagement/assignmentRequests"
    )
    for r in reqs:
        rt = str(r.get("requestType", "")).lower()
        state = str(r.get("state", "")).lower()
        if "adminadd" in rt and state == "delivered":
            for pid in _principal_ids_of(r):
                ids.add(pid)
    asgn = graph_all(
        GOV, "/v1.0/identityGovernance/entitlementManagement/assignments"
    )
    for a in asgn:
        if str(a.get("state", "")).lower() == "delivered":
            for pid in _principal_ids_of(a):
                ids.add(pid)
    return ids

def _principal_ids_of(obj):
    out = set()
    for key in ("target", "requestor", "principal", "accessPackageAssignment"):
        v = obj.get(key)
        if isinstance(v, dict):
            for k2 in ("id", "objectId", "userPrincipalName", "email", "principalId"):
                if v.get(k2):
                    out.add(str(v[k2]).lower())
            tgt = v.get("target")
            if isinstance(tgt, dict):
                for k2 in ("id", "objectId", "userPrincipalName", "email"):
                    if tgt.get(k2):
                        out.add(str(tgt[k2]).lower())
    for k2 in ("principalId", "targetId"):
        if obj.get(k2):
            out.add(str(obj[k2]).lower())
    return out

def entra_groups():
    return graph_all(ENTRA, "/v1.0/groups")

def entra_group_members(gid):
    return graph_all(ENTRA, f"/v1.0/groups/{gid}/members")

def entra_user(uid):
    status, _, body = request("GET", ENTRA, f"/v1.0/users/{uid}")
    if status >= 400:
        return None
    return body

def email_for_principal(principal):
    email = principal.get("userPrincipalName") or principal.get("mail") or principal.get("email")
    if email:
        return email
    u = entra_user(principal.get("id"))
    if u:
        return u.get("mail") or u.get("userPrincipalName")
    return None

def okta_users():
    return okta_all("/api/v1/users")

def okta_user_by_login(login):
    for u in okta_users():
        prof = u.get("profile", {})
        if str(prof.get("login", "")).lower() == login.lower() or str(
            prof.get("email", "")
        ).lower() == login.lower():
            return u
    return None

def okta_groups():
    return okta_all("/api/v1/groups")

def okta_apps():
    return okta_all("/api/v1/apps")

def jc_user_by_email(email):
    for u in jc_all("/api/systemusers"):
        if str(u.get("email", "")).lower() == email.lower():
            return u
    return None

def remove_entra_member(gid, uid, label):
    members = [m.get("id") for m in entra_group_members(gid)]
    if uid not in members:
        WRITES.append(f"NOOP entra member already absent {label}")
        return
    status, _, body = request(
        "DELETE", ENTRA, f"/v1.0/groups/{gid}/members/{uid}/$ref"
    )
    if status not in (204, 200):
        raise RuntimeError(f"entra remove member {label} -> {status}: {body}")
    WRITES.append(f"REMOVE entra membership {label}")

def remove_okta_role(user, label):
    roles = okta_all(f"/api/v1/users/{user['id']}/roles")
    target = None
    for r in roles:
        if str(r.get("label", "")) == label or str(r.get("type", "")) == label:
            target = r
    if not target:
        WRITES.append(f"NOOP okta role already absent {label}")
        return
    status, _, body = request(
        "DELETE", OKTA, f"/api/v1/users/{user['id']}/roles/{target['id']}"
    )
    if status not in (204, 200):
        raise RuntimeError(f"okta remove role {label} -> {status}: {body}")
    WRITES.append(f"REMOVE okta role {label} from {user['profile'].get('login')}")

def remove_okta_group_member(group, user, label):
    members = okta_all(f"/api/v1/groups/{group['id']}/users")
    if user["id"] not in [m.get("id") for m in members]:
        WRITES.append(f"NOOP okta group member absent {label}")
        return
    status, _, body = request(
        "DELETE", OKTA, f"/api/v1/groups/{group['id']}/users/{user['id']}"
    )
    if status not in (204, 200):
        raise RuntimeError(f"okta remove group member {label} -> {status}: {body}")
    WRITES.append(f"REMOVE okta group membership {label} for {user['profile'].get('login')}")

def remove_okta_app_user(app, user, label):
    assn = okta_all(f"/api/v1/apps/{app['id']}/users")
    rec = None
    for a in assn:
        if a.get("id") == user["id"]:
            rec = a
    if not rec:
        WRITES.append(f"NOOP okta app assignment absent {label}")
        return
    if str(rec.get("scope")) == "GROUP":
        raise RuntimeError(
            f"okta app {label} for {user['id']} is GROUP-derived; remove via group"
        )
    status, _, body = request(
        "DELETE", OKTA, f"/api/v1/apps/{app['id']}/users/{user['id']}"
    )
    if status not in (204, 200):
        raise RuntimeError(f"okta remove app user {label} -> {status}: {body}")
    WRITES.append(f"REMOVE okta app assignment {label} for {user['profile'].get('login')}")

def jc_remove_membership(gid, uid, label):
    status, _, body = request(
        "POST", JC, f"/api/v2/usergroups/{gid}/members",
        body={"op": "remove", "type": "user", "id": uid},
    )
    if status not in (204, 200):
        raise RuntimeError(f"jc remove usergroup member {label} -> {status}: {body}")
    WRITES.append(f"REMOVE jumpcloud usergroup membership {label}")

def jc_remove_user_system_edges(uid, prod_system_ids, label):
    assoc = jc_all(f"/api/v2/users/{uid}/associations")
    removed = 0
    for a in assoc:
        to = a.get("to") or {}
        if to.get("type") in ("system",) and to.get("id") in prod_system_ids:
            status, _, body = request(
                "POST", JC, f"/api/v2/users/{uid}/associations",
                body={"op": "remove", "type": "system", "id": to.get("id")},
            )
            if status not in (204, 200):
                raise RuntimeError(f"jc remove user->system {label} -> {status}: {body}")
            removed += 1
    WRITES.append(f"REMOVE jumpcloud direct prod-system bindings ({removed}) {label}")

def jc_prod_systems_of_usergroup(gid):
    reached = jc_all(f"/api/v2/usergroups/{gid}/systems")
    return {r.get("id") for r in reached if r.get("id")}

def main():
    all_decisions = discover_all_decisions()
    denied = [d for d in all_decisions if str(d.get("decision", "")).lower() == "deny"]
    reapproved = reapproved_principal_ids()
    print(f"denied decisions: {len(denied)}; reapproved principals: {len(reapproved)}")

    egroups = {g.get("displayName"): g for g in entra_groups()}
    ogroups = {g.get("profile", {}).get("name"): g for g in okta_groups()}
    oapps = {a.get("label"): a for a in okta_apps()}
    jgroups = {g.get("name"): g for g in jc_all("/api/v2/usergroups")}

    for dec in denied:
        principal = dec.get("principal", {}) or {}
        pid = str(principal.get("id", "")).lower()
        email = email_for_principal(principal) or ""
        resource = dec.get("resource", {}) or {}
        rname = resource.get("displayName", "")
        label = f"[{principal.get('displayName')} :: {rname}]"

        if (superseded_by_later_approval(all_decisions, dec)
                or pid in reapproved or (email and email.lower() in reapproved)):
            WRITES.append(f"PRESERVE re-approved {label}")
            continue

        rtype = str(resource.get("type", "")).lower()
        acted = False
        if rname in egroups and rtype != "directoryrole":
            remove_entra_member(egroups[rname]["id"], principal.get("id"), label)
            acted = True
        if not acted:
            ouser = okta_user_by_login(email) if email else None
            if ouser is not None:
                if rtype == "directoryrole":
                    remove_okta_role(ouser, rname)
                    acted = True
                elif rname in ogroups:
                    remove_okta_group_member(ogroups[rname], ouser, label)
                    acted = True
                elif rname in oapps:
                    remove_okta_app_user(oapps[rname], ouser, label)
                    acted = True
        if not acted and rname in jgroups:
            juser = jc_user_by_email(email) if email else None
            if juser is not None:
                gid = jgroups[rname]["id"]
                prod_systems = jc_prod_systems_of_usergroup(gid)
                jc_remove_membership(gid, juser["id"], label)
                jc_remove_user_system_edges(juser["id"], prod_systems, label)
                acted = True

        if not acted:
            WRITES.append(f"UNRESOLVED {label} (no live grant located)")

    print("\n--- WRITE LIST ---")
    for w in WRITES:
        print(" ", w)
    unresolved = [w for w in WRITES if w.startswith("UNRESOLVED")]
    if unresolved:
        print(f"\nERROR: {len(unresolved)} unresolved denied grants", file=sys.stderr)
        sys.exit(2)
    print("\nOK: oracle completed")

if __name__ == "__main__":
    main()
