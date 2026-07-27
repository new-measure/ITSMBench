#!/usr/bin/env python3
import json
import re
import sys
import urllib.request
import urllib.error
import urllib.parse

def qseg(s):
    return urllib.parse.quote(str(s), safe="")

TICKET_ID = "REL-4471"

AM = "http://aws-audit-manager.local.mock:8080"
VANTA = "http://vanta.local.mock:8080/v1"
JSM = "http://jira-service-management.local.mock:8080"

EXC_RE = re.compile(r"EXC-\d{4}-\d+")
CODE_RE = re.compile(r"\b([A-Z]{1,3}\d+\.\d+)\b")

def _req(method, url, body=None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"_raw": raw}

def get(url):
    return _req("GET", url)

def die(msg):
    print("ORACLE-FAIL:", msg, file=sys.stderr)
    sys.exit(2)

def vanta_all(path, params=""):
    out = []
    cursor = None
    while True:
        sep = "&" if "?" in path else "?"
        q = f"{path}{sep}pageSize=100{params}"
        if cursor:
            q += f"&pageCursor={cursor}"
        st, body = get(VANTA + q)
        if st != 200:
            die(f"vanta GET {q} -> {st} {body}")
        res = body.get("results", body)
        out.extend(res.get("data", []))
        pi = res.get("pageInfo", {})
        if pi.get("hasNextPage") and pi.get("endCursor"):
            cursor = pi["endCursor"]
        else:
            return out

def am_all(path, key):
    out = []
    token = None
    while True:
        sep = "&" if "?" in path else "?"
        q = f"{path}{sep}maxResults=1000"
        if token:
            q += f"&nextToken={token}"
        st, body = get(AM + q)
        if st != 200:
            die(f"am GET {q} -> {st} {body}")
        out.extend(body.get(key, []))
        token = body.get("nextToken")
        if not token:
            return out

def jsm_all(path):
    out = []
    start = 0
    while True:
        sep = "&" if "?" in path else "?"
        st, body = get(JSM + f"{path}{sep}start={start}&limit=100")
        if st != 200:
            die(f"jsm GET {path} -> {st} {body}")
        out.extend(body.get("values", []))
        if body.get("isLastPage", True):
            return out
        start += len(body.get("values", [])) or 100

def main():
    st, ticket = get(JSM + f"/rest/servicedeskapi/request/{TICKET_ID}")
    if st != 200:
        die(f"trigger ticket {TICKET_ID} not found ({st})")
    print(f"[ticket] {TICKET_ID}: {ticket.get('summary') or ticket.get('requestFieldValues',{}).get('summary')}")

    assessments = am_all("/assessments", "assessmentMetadata")
    if not assessments:
        die("no AM assessments")
    active = [a for a in assessments if a.get("status") == "ACTIVE"] or assessments
    aid = active[0]["id"]
    st, full = get(AM + f"/assessments/{aid}")
    if st != 200:
        die(f"GetAssessment {aid} -> {st}")
    assessment = full["assessment"]
    control_sets = assessment["framework"]["controlSets"]

    scope_codes = set()
    am_controls = []
    for cs in control_sets:
        for c in cs["controls"]:
            m = CODE_RE.search(c.get("name", ""))
            code = m.group(1) if m else None
            if code:
                scope_codes.add(code)
            am_controls.append((cs["id"], c, code))
    if not scope_codes:
        die("no SOC2 codes parsed from AM control names (C1/C2 violated)")
    print(f"[scope] {len(scope_codes)} control codes: {sorted(scope_codes)}")

    v_controls = vanta_all("/controls")
    by_code = {}
    for c in v_controls:
        ext = c.get("externalId")
        if ext:
            by_code[ext] = c

    def control_docs(ctl_id):
        return vanta_all(f"/controls/{ctl_id}/documents")

    def document_files(doc_id):
        return vanta_all(f"/documents/{qseg(doc_id)}/uploads")

    v_tests = vanta_all("/tests")

    def test_deactivated_entities(test_id):
        return vanta_all(f"/tests/{test_id}/entities", params="&entityStatus=DEACTIVATED")

    all_docs = vanta_all("/documents")
    exc_ok_titles = [d for d in all_docs if d.get("uploadStatus") == "OK"]

    def exception_resolves(reason):
        if not reason:
            return False
        m = EXC_RE.search(reason)
        if not m:
            return False
        exc = m.group(0)
        return any(exc in (d.get("title") or "") for d in exc_ok_titles)

    plan_reactivate = []
    plan_submit = []
    plan_import = []

    for t in v_tests:
        for e in test_deactivated_entities(t["id"]):
            if e.get("entityStatus") != "DEACTIVATED":
                continue
            if exception_resolves(e.get("deactivatedReason")):
                continue
            plan_reactivate.append((t["id"], e["id"], t.get("name")))

    for code in sorted(scope_codes):
        ctl = by_code.get(code)
        if not ctl:
            continue
        for d in control_docs(ctl["id"]):
            if d.get("uploadStatus") == "Needs document":
                plan_submit.append((d["id"], code))

    for set_id, c, code in am_controls:
        if c.get("status") != "REVIEWED":
            continue
        st, folders = get(AM + f"/assessments/{aid}/evidenceFolders-by-assessment-control/{qseg(set_id)}/{qseg(c['id'])}")
        total = 0
        if st == 200:
            for f in folders.get("evidenceFolders", []):
                total += int(f.get("totalEvidence", 0) or 0)
        if total > 0:
            continue
        vctl = by_code.get(code)
        vdoc = None
        if vctl:
            for d in control_docs(vctl["id"]):
                if d.get("uploadStatus") == "OK":
                    vdoc = d
                    break
        if vdoc is None:
            print(f"[warn] {code} REVIEWED+empty but no Vanta evidence — skipping", file=sys.stderr)
            continue
        files = document_files(vdoc["id"])
        artifact = next((f.get("fileName") for f in files if f.get("fileName")), None)
        if not artifact:
            print(f"[warn] {code} Vanta evidence doc {vdoc['id']} has no artifact file — skipping", file=sys.stderr)
            continue
        plan_import.append((set_id, c["id"], c.get("name"), vdoc, artifact))

    print(f"[plan] reactivate={len(plan_reactivate)} submit={len(plan_submit)} import={len(plan_import)}")
    for p in plan_reactivate:
        print("   reactivate entity", p)
    for p in plan_submit:
        print("   submit doc", p)
    for p in plan_import:
        print("   import evidence ->", p[2], "artifact:", p[4])

    for test_id, entity_id, _name in plan_reactivate:
        st, _ = _req("POST", VANTA + f"/tests/{test_id}/entities/{entity_id}/reactivate")
        if st not in (200, 202, 204):
            die(f"reactivate {entity_id} -> {st}")

    for doc_id, code in plan_submit:
        st, _ = _req("POST", VANTA + f"/documents/{doc_id}/submit")
        if st not in (200, 202, 204):
            die(f"submitCollection {doc_id} -> {st}")

    for set_id, ctl_id, name, vdoc, artifact in plan_import:
        body = {"manualEvidence": [{
            "evidenceFileName": artifact,
            "textResponse": f"Ported from Vanta evidence file {artifact} (Vanta document {vdoc.get('id')})",
        }]}
        url = AM + f"/assessments/{aid}/controlSets/{qseg(set_id)}/controls/{qseg(ctl_id)}/evidence"
        st, resp = _req("POST", url, body)
        if st not in (200, 201):
            die(f"import evidence for {name} -> {st} {resp} URL={url}")

    fails = []
    for test_id, entity_id, _n in plan_reactivate:
        ents = vanta_all(f"/tests/{test_id}/entities", params="&entityStatus=FAILING")
        if not any(e["id"] == entity_id and e.get("entityStatus") == "FAILING" for e in ents):
            fails.append(f"entity {entity_id} not FAILING after reactivate")
    for doc_id, code in plan_submit:
        st, d = get(VANTA + f"/documents/{doc_id}")
        if (d.get("uploadStatus")) != "OK":
            fails.append(f"doc {doc_id} not OK")
    for set_id, ctl_id, name, vdoc, artifact in plan_import:
        st, folders = get(AM + f"/assessments/{aid}/evidenceFolders-by-assessment-control/{qseg(set_id)}/{qseg(ctl_id)}")
        fids = [f.get("id") for f in folders.get("evidenceFolders", [])]
        total = sum(int(f.get("totalEvidence", 0) or 0) for f in folders.get("evidenceFolders", []))
        if total < 1:
            fails.append(f"AM control {name} folder still empty")
        ported = False
        for fid in fids:
            st2, evb = get(AM + f"/assessments/{aid}/controlSets/{qseg(set_id)}/evidenceFolders/{qseg(fid)}/evidence")
            for e in evb.get("evidence", []):
                if artifact in json.dumps(e.get("attributes", {})):
                    ported = True
        if not ported:
            fails.append(f"AM control {name} folder missing ported artifact identity {artifact}")
    if fails:
        for f in fails:
            print("READBACK-FAIL:", f, file=sys.stderr)
        sys.exit(3)
    print("OK: readback clean; all planned writes verified.")

if __name__ == "__main__":
    main()
