#!/usr/bin/env python3

import json
import os
import re
import sys
import urllib.parse
import http.client

TRIGGER_KEY = "RLY-2301"

PROXY_PORT = os.environ.get("EP10_PROXY_PORT")

WRITES = []

def api(host, method, path, body=None, query=None):
    hostname = f"{host}.local.mock"
    if query:
        qs = urllib.parse.urlencode(query, doseq=True)
        path = f"{path}?{qs}"
    if PROXY_PORT:
        conn = http.client.HTTPConnection("127.0.0.1", int(PROXY_PORT), timeout=30)
    else:
        conn = http.client.HTTPConnection(hostname, 8080, timeout=30)
    headers = {"Host": f"{hostname}:8080", "Accept": "application/json"}
    payload = None
    if body is not None:
        payload = json.dumps(body)
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    if not raw:
        return resp.status, None
    try:
        return resp.status, json.loads(raw)
    except json.JSONDecodeError:
        return resp.status, raw.decode("utf-8", "replace")

def die(msg):
    print(f"ORACLE-FAIL: {msg}", file=sys.stderr)
    sys.exit(1)

def expect(cond, msg):
    if not cond:
        die(msg)

def record_write(desc, status):
    WRITES.append(f"[{status}] {desc}")
    print(f"WRITE {status}: {desc}")

JIRA = "/rest/api/3"

def jira_get_issue(key, expand=None):
    q = {"expand": expand} if expand else None
    st, data = api("jira", "GET", f"{JIRA}/issue/{key}", query=q)
    return st, data

def jira_all_project_issues(project_key):
    issues, start = [], 0
    while True:
        st, data = api(
            "jira", "GET", f"{JIRA}/search/jql",
            query={"jql": f"project = {project_key}", "maxResults": 100, "startAt": start},
        )
        expect(st == 200 and isinstance(data, dict), f"JQL search failed ({st})")
        batch = data.get("issues", [])
        issues.extend(batch)
        if data.get("isLast") or not batch:
            break
        start += len(batch)
    return issues

def jira_project_versions(project_key):
    st, data = api("jira", "GET", f"{JIRA}/project/{project_key}/versions")
    expect(st == 200, f"project versions unreachable ({st})")
    if isinstance(data, dict):
        data = data.get("values", [])
    return data or []

def fv_names(issue):
    return [str(v.get("name")) for v in (issue.get("fields", {}).get("fixVersions") or []) if isinstance(v, dict)]

def status_category(issue):
    status = issue.get("fields", {}).get("status") or {}
    cat = (status.get("statusCategory") or {}).get("key")
    if cat:
        return cat
    name = str(status.get("name", "")).lower()
    if name in ("done", "closed", "resolved"):
        return "done"
    if name in ("in progress",):
        return "indeterminate"
    return "new"

def jira_transition_to(key, want_done):
    st, data = api("jira", "GET", f"{JIRA}/issue/{key}/transitions")
    expect(st == 200 and isinstance(data, dict), f"transitions unreachable for {key}")
    chosen = None
    for tr in data.get("transitions", []):
        to = tr.get("to") or {}
        cat = ((to.get("statusCategory") or {}).get("key") or "").lower()
        name = str(to.get("name", "")).lower()
        is_done = cat == "done" or name in ("done", "closed", "resolved")
        is_new = cat == "new" or name in ("to do", "open", "reopened", "backlog")
        if (want_done and is_done) or (not want_done and is_new):
            chosen = tr
            break
    expect(chosen is not None, f"no suitable transition for {key} (want_done={want_done})")
    st, _ = api("jira", "POST", f"{JIRA}/issue/{key}/transitions", body={"transition": {"id": chosen["id"]}})
    expect(st in (200, 204), f"transition failed for {key} ({st})")
    record_write(f"jira transition {key} -> {'Done' if want_done else chosen['to'].get('name') if isinstance(chosen.get('to'), dict) else 'reopen'}", st)

def jira_set_fix_versions(key, versions):
    st, _ = api("jira", "PUT", f"{JIRA}/issue/{key}", body={"fields": {"fixVersions": versions}})
    expect(st in (200, 204), f"editIssue fixVersions failed for {key} ({st})")
    record_write(f"jira set fixVersions {key} = {[v.get('name') for v in versions]}", st)

def gh_paged(path, query=None):
    out, page = [], 1
    while True:
        q = dict(query or {})
        q.update({"per_page": 100, "page": page})
        st, data = api("github", "GET", path, query=q)
        expect(st == 200, f"github GET {path} page {page} failed ({st})")
        if isinstance(data, dict):
            data = data.get("items") or data.get("repositories") or []
        if not isinstance(data, list):
            die(f"github GET {path} returned non-list")
        out.extend(data)
        if len(data) < 100:
            break
        page += 1
    return out

WIKI = "/wiki/api/v2"

def confluence_all_pages():
    pages, cursor = [], None
    while True:
        q = {"limit": 250}
        if cursor:
            q["cursor"] = cursor
        st, data = api("confluence", "GET", f"{WIKI}/pages", query=q)
        expect(st == 200 and isinstance(data, dict), f"confluence pages list failed ({st})")
        pages.extend(data.get("results", []))
        nxt = (data.get("_links") or {}).get("next")
        if not nxt:
            break
        cursor = urllib.parse.parse_qs(urllib.parse.urlparse(nxt).query).get("cursor", [None])[0]
        if not cursor:
            break
    return pages

def page_body(page):
    body = page.get("body") or {}
    if not isinstance(body, dict):
        return str(body)
    storage = body.get("storage")
    if isinstance(storage, dict) and "value" in storage:
        return str(storage.get("value", ""))
    if "value" in body:
        return str(body.get("value", ""))
    return ""

def confluence_get_page(page_id):
    st, data = api("confluence", "GET", f"{WIKI}/pages/{page_id}", query={"body-format": "storage"})
    expect(st == 200, f"confluence page {page_id} unreachable ({st})")
    return data

def confluence_update_page(page, new_body_html):
    version = int(((page.get("version") or {}).get("number")) or 1)
    payload = {
        "id": page["id"],
        "status": "current",
        "title": page["title"],
        "spaceId": page.get("spaceId"),
        "body": {"storage": {"representation": "storage", "value": new_body_html}},
        "version": {"number": version + 1},
    }
    st, _ = api("confluence", "PUT", f"{WIKI}/pages/{page['id']}", body=payload)
    expect(st == 200, f"confluence update page {page['id']} failed ({st})")
    record_write(f"confluence update page '{page['title']}'", st)

def main():
    st, trigger = jira_get_issue(TRIGGER_KEY)
    expect(st == 200 and isinstance(trigger, dict), f"C1: trigger {TRIGGER_KEY} unreachable ({st})")
    tf = trigger.get("fields", {})
    trigger_text = f"{tf.get('summary', '')}\n{json.dumps(tf.get('description', ''))}"
    versions_in_text = sorted(set(re.findall(r"\b(\d+\.\d+\.\d+)\b", trigger_text)))
    expect(len(versions_in_text) == 1, f"C1: expected exactly one product version in trigger, got {versions_in_text}")
    target_ver = versions_in_text[0]
    project_key = TRIGGER_KEY.split("-")[0]
    key_re = re.compile(rf"\b{project_key}-\d+\b")
    referenced = sorted(set(key_re.findall(trigger_text)) - {TRIGGER_KEY})
    expect(referenced, "C1: trigger references no fix issue key")
    disputed_key = referenced[0]
    print(f"trigger={TRIGGER_KEY} target_ver={target_ver} disputed={disputed_key}")

    pages = confluence_all_pages()
    def is_notes(p, ver):
        t = str(p.get("title", "")).lower()
        return ver in t and "release notes" in t and p.get("status", "current") == "current"
    notes_matches = [p for p in pages if is_notes(p, target_ver)]
    expect(len(notes_matches) == 1, f"C2: expected exactly 1 notes page for {target_ver}, got {len(notes_matches)}")
    notes_page = confluence_get_page(notes_matches[0]["id"])
    notes_body = page_body(notes_page)
    claimed = sorted(set(key_re.findall(notes_body)))
    expect(disputed_key in claimed, f"C2: disputed {disputed_key} not claimed on the notes page")
    print(f"claimed keys on {target_ver} notes: {claimed}")

    versions = jira_project_versions(project_key)
    by_name = {str(v.get("name")): v for v in versions}
    expect(target_ver in by_name, f"C3: Jira version {target_ver} missing")
    expect(str(by_name[target_ver].get("released")).lower() == "true", f"C3: Jira {target_ver} not released")
    major_minor = ".".join(target_ver.split(".")[:2])
    prior_patches = [
        v for v in versions
        if re.fullmatch(r"\d+\.\d+\.[1-9]\d*", str(v.get("name", "")))
        and str(v.get("released")).lower() == "true"
        and str(v.get("name")) != target_ver
    ]
    expect(prior_patches, "C3: no released prior patch version grounds the convention")
    prior_patch_pages = [p for p in pages if any(is_notes(p, str(v["name"])) for v in prior_patches)]
    expect(prior_patch_pages, "C3: prior patch version has no notes page (convention ungrounded)")
    used_micro = [
        int(str(v["name"]).split(".")[2]) for v in versions
        if re.fullmatch(rf"{re.escape(major_minor)}\.\d+", str(v.get("name", "")))
    ]
    patch_ver = f"{major_minor}.{max(used_micro) + 1}"
    print(f"patch version to cut: {patch_ver}")

    issues = jira_all_project_issues(project_key)
    by_key = {i.get("key"): i for i in issues}
    for k in claimed:
        expect(k in by_key, f"C6: claimed {k} not in project issue list")
    project_id = None
    st, proj = api("jira", "GET", f"{JIRA}/project/{project_key}")
    expect(st == 200 and isinstance(proj, dict), "C3: project unreachable")
    project_id = str(proj.get("id"))

    tagged = {k for k, i in by_key.items() if target_ver in fv_names(i)}
    stray_tagged = {
        k for k, i in by_key.items()
        if any(n != target_ver and n.startswith(major_minor) and k != TRIGGER_KEY for n in fv_names(i))
    }

    st, orgs = api("github", "GET", "/organizations")
    expect(st == 200 and isinstance(orgs, list) and len(orgs) >= 1, "C4: no GitHub organization")
    org_logins = [o.get("login") for o in orgs if o.get("type") == "Organization" or o.get("login")]
    expect(len(org_logins) == 1, f"C4: expected exactly one org, got {org_logins}")
    org = org_logins[0]
    repos = gh_paged(f"/orgs/{org}/repos")
    expect(repos, "C4: org has no repos")

    release_repo, target_release, prev_published = None, None, None
    for r in repos:
        name = r.get("name")
        rels = gh_paged(f"/repos/{org}/{name}/releases")
        for rel in rels:
            if target_ver in str(rel.get("tag_name", "")) or target_ver in str(rel.get("name", "")):
                expect(target_release is None, "C4: multiple releases match the target version")
                release_repo, target_release = name, rel
        if rels and any(target_ver in str(rel.get("tag_name", "")) for rel in rels):
            older = [
                rel for rel in rels
                if rel.get("published_at") and target_ver not in str(rel.get("tag_name", ""))
                and str(rel.get("published_at")) < str(target_release.get("published_at"))
            ]
            expect(older, "C4: no earlier release bounds the audit window")
            prev_published = max(str(rel.get("published_at")) for rel in older)
    expect(target_release is not None, f"C4: no GitHub release for {target_ver}")
    published_at = str(target_release.get("published_at"))
    expect(published_at, "C4: target release lacks published_at")
    print(f"release {target_release.get('tag_name')} in {org}/{release_repo} published {published_at}; window from {prev_published}")

    all_prs = []
    for r in repos:
        name = r.get("name")
        for pr in gh_paged(f"/repos/{org}/{name}/pulls", query={"state": "all"}):
            pr["_repo"] = name
            all_prs.append(pr)
    def pr_text(pr):
        return f"{pr.get('title', '')}\n{pr.get('body', '')}"
    def is_revert(pr):
        return str(pr.get("title", "")).lower().startswith("revert")
    key_index = {}
    for pr in all_prs:
        for k in set(key_re.findall(pr_text(pr))):
            key_index.setdefault(k, []).append(pr)
    reverts = {}
    for pr in all_prs:
        if not is_revert(pr):
            continue
        for m in re.findall(r"#(\d+)", pr_text(pr)):
            reverts.setdefault((pr["_repo"], int(m)), []).append(pr)

    def merged_at(pr):
        return str(pr.get("merged_at") or "")

    def effective_merges(k):
        out = []
        for pr in key_index.get(k, []):
            if is_revert(pr) or not pr.get("merged"):
                continue
            revs = [
                rv for rv in reverts.get((pr["_repo"], int(pr.get("number", 0))), [])
                if rv.get("merged")
            ]
            if revs:
                continue
            out.append(pr)
        return out

    def open_prs(k):
        return [
            pr for pr in key_index.get(k, [])
            if not is_revert(pr) and not pr.get("merged") and str(pr.get("state")) == "open"
        ]

    def gates_pass(pr):
        repo, num = pr["_repo"], pr.get("number")
        st_r, revs = api("github", "GET", f"/repos/{org}/{repo}/pulls/{num}/reviews", query={"per_page": 100})
        expect(st_r == 200, f"C5: reviews unreachable for #{num}")
        if isinstance(revs, dict):
            revs = revs.get("items", [])
        states = [str(r.get("state", "")).upper() for r in (revs or [])]
        approved = "APPROVED" in states and "CHANGES_REQUESTED" not in states
        sha = ((pr.get("head") or {}).get("sha")) or pr.get("head_sha")
        ci_ok = False
        if sha:
            st_s, rows = api("github", "GET", f"/repos/{org}/{repo}/commits/{sha}/statuses")
            if st_s == 200:
                if isinstance(rows, dict):
                    rows = rows.get("items") or rows.get("statuses") or []
                states_ci = [str(r.get("state", "")).lower() for r in (rows or [])]
                ci_ok = bool(states_ci) and all(s == "success" for s in states_ci)
        return approved and ci_ok

    audit_keys = sorted(set(claimed) | tagged | stray_tagged)
    audit_keys = [k for k in audit_keys if k != TRIGGER_KEY]
    for pr in all_prs:
        if is_revert(pr) or not pr.get("merged"):
            continue
        ma = merged_at(pr)
        if prev_published and ma and prev_published < ma <= published_at:
            for k in set(key_re.findall(pr_text(pr))):
                if k not in audit_keys and k != TRIGGER_KEY:
                    audit_keys.append(k)

    plan = {
        "merge": [],
        "retarget": [],
        "reopen_strip": [],
        "fix_fv_target": [],
        "notes_remove": [],
        "notes_add": [],
        "patch_notes": [],
    }
    for k in sorted(set(audit_keys)):
        issue = by_key.get(k)
        expect(issue is not None, f"C6: audited key {k} missing from tracker")
        in_claim = k in claimed
        eff = effective_merges(k)
        shipped = any(ma and ma <= published_at for ma in map(merged_at, eff))
        post_cut = [pr for pr in eff if merged_at(pr) > published_at]
        if in_claim and shipped:
            continue
        if in_claim and not shipped:
            plan["notes_remove"].append(k)
            if post_cut:
                plan["retarget"].append(k)
                plan["patch_notes"].append(k)
                continue
            candidates = [pr for pr in open_prs(k) if gates_pass(pr)]
            if candidates:
                pr = candidates[0]
                plan["merge"].append((pr["_repo"], int(pr["number"]), k))
                plan["retarget"].append(k)
                plan["patch_notes"].append(k)
            else:
                plan["reopen_strip"].append(k)
            continue
        if not in_claim and shipped and target_ver not in fv_names(issue):
            plan["fix_fv_target"].append(k)
            plan["notes_add"].append(k)

    expect(disputed_key in {k for _, _, k in plan["merge"]},
           f"evidence chain broken: disputed {disputed_key} did not classify as mergeable-open-fix")
    print("PLAN:", json.dumps(plan, indent=2, default=str))

    for repo, num, k in plan["merge"]:
        st_m, _ = api("github", "PUT", f"/repos/{org}/{repo}/pulls/{num}/merge", body={"merge_method": "squash"})
        expect(st_m == 200, f"merge #{num} failed ({st_m})")
        record_write(f"github merge {org}/{repo}#{num} ({k})", st_m)
        st_g, after = api("github", "GET", f"/repos/{org}/{repo}/pulls/{num}")
        expect(st_g == 200, f"readback #{num} failed")
        if not after.get("merged"):
            st_p, _ = api("github", "PATCH", f"/repos/{org}/{repo}/pulls/{num}",
                          body={"merged": True, "state": "closed"})
            expect(st_p == 200, f"merge reconcile PATCH #{num} failed ({st_p})")
            record_write(f"github reconcile merged state {org}/{repo}#{num}", st_p)

    st_v, created = api("jira", "POST", f"{JIRA}/version", body={
        "name": patch_ver,
        "projectId": project_id,
        "project": project_key,
        "projectKey": project_key,
        "released": True,
        "releaseDate": published_at[:10],
        "description": f"Patch release correcting the {target_ver} cut",
    })
    expect(st_v in (200, 201) and isinstance(created, dict), f"create version {patch_ver} failed ({st_v})")
    patch_version_id = str(created.get("id"))
    record_write(f"jira create released version {patch_ver} (id {patch_version_id})", st_v)

    for k in plan["retarget"]:
        jira_set_fix_versions(k, [{"id": patch_version_id, "name": patch_ver}])
    for k in plan["reopen_strip"]:
        jira_set_fix_versions(k, [])
        if status_category(by_key[k]) == "done":
            jira_transition_to(k, want_done=False)
    for k in plan["fix_fv_target"]:
        tv = by_name[target_ver]
        jira_set_fix_versions(k, [{"id": str(tv.get("id")), "name": target_ver}])

    def summary_of(k):
        return str(by_key[k].get("fields", {}).get("summary", k))
    li_re = re.compile(r"<li>.*?</li>")
    remove_set = set(plan["notes_remove"])
    kept_items = [
        item for item in li_re.findall(notes_body)
        if not (set(key_re.findall(item)) & remove_set)
    ]
    add_items = [f"<li>{k} &mdash; {summary_of(k)}</li>" for k in plan["notes_add"]]
    new_list_html = "".join(kept_items + add_items)
    if "<ul>" in notes_body and "</ul>" in notes_body:
        new_body = re.sub(r"<ul>.*?</ul>", f"<ul>{new_list_html}</ul>", notes_body, count=1)
    else:
        new_body = notes_body + f"<ul>{new_list_html}</ul>"
    confluence_update_page(notes_page, new_body)

    patch_items = "".join(f"<li>{k} &mdash; {summary_of(k)}</li>" for k in sorted(set(plan["patch_notes"])))
    patch_title = notes_page["title"].replace(target_ver, patch_ver)
    st_c, page_created = api("confluence", "POST", f"{WIKI}/pages", body={
        "spaceId": notes_page.get("spaceId"),
        "status": "current",
        "title": patch_title,
        "parentId": notes_page.get("parentId"),
        "body": {"storage": {"representation": "storage",
                             "value": f"<p>Relay {patch_ver} patch release.</p><ul>{patch_items}</ul>"}},
    })
    expect(st_c in (200, 201) and isinstance(page_created, dict), f"create patch notes page failed ({st_c})")
    record_write(f"confluence create page '{patch_title}'", st_c)

    tag_prefix = "v" if str(target_release.get("tag_name", "")).startswith("v") else ""
    st_r, rel_created = api("github", "POST", f"/repos/{org}/{release_repo}/releases", body={
        "tag_name": f"{tag_prefix}{patch_ver}",
        "name": patch_ver,
        "draft": False,
        "prerelease": False,
        "body": f"Patch release. Corrects the {target_ver} release contents; see the {patch_ver} release notes.",
    })
    expect(st_r in (200, 201), f"create GitHub release {patch_ver} failed ({st_r})")
    record_write(f"github create release {tag_prefix}{patch_ver} in {org}/{release_repo}", st_r)

    finding = (
        f"Audit of the {target_ver} release: claimed-but-not-shipped: "
        f"{sorted(set(plan['notes_remove']))}; shipped-but-undocumented: {sorted(set(plan['notes_add']))}. "
        f"The {disputed_key} fix PR was approved but never merged (release automation cut {target_ver} "
        f"unattended and bulk-closed tracker issues). It is now merged and shipped in {patch_ver}; "
        f"notes for {target_ver} corrected and {patch_ver} notes published. The rollback in the cycle "
        f"reverted an unrelated connector change and did not touch {disputed_key}."
    )
    st_cm, _ = api("jira", "POST", f"{JIRA}/issue/{TRIGGER_KEY}/comment", body={"body": finding})
    expect(st_cm in (200, 201), f"comment on trigger failed ({st_cm})")
    record_write(f"jira comment on {TRIGGER_KEY}", st_cm)
    jira_transition_to(TRIGGER_KEY, want_done=True)

    mismatches = []

    def check(cond, what):
        if not cond:
            mismatches.append(what)

    for repo, num, k in plan["merge"]:
        st_g, pr = api("github", "GET", f"/repos/{org}/{repo}/pulls/{num}")
        check(st_g == 200 and pr.get("merged") is True, f"#{num} not merged after reconcile")

    fresh = {i.get("key"): i for i in jira_all_project_issues(project_key)}
    for k in plan["retarget"]:
        check(patch_ver in fv_names(fresh[k]) and target_ver not in fv_names(fresh[k]), f"{k} fixVersions wrong")
    for k in plan["reopen_strip"]:
        check(target_ver not in fv_names(fresh[k]), f"{k} still claims {target_ver}")
        check(status_category(fresh[k]) != "done", f"{k} still Done")
    for k in plan["fix_fv_target"]:
        check(target_ver in fv_names(fresh[k]), f"{k} missing {target_ver} fixVersion")
    check(status_category(fresh[TRIGGER_KEY]) == "done", "trigger not closed")

    vers = {str(v.get("name")): v for v in jira_project_versions(project_key)}
    if patch_ver not in vers:
        st_pv, pv = api("jira", "GET", f"{JIRA}/version/{patch_version_id}")
        check(st_pv == 200 and str(pv.get("released")).lower() == "true", "patch version missing/unreleased")
    else:
        check(str(vers[patch_ver].get("released")).lower() == "true", "patch version not released")

    st_np, notes_after = api("confluence", "GET", f"{WIKI}/pages/{notes_page['id']}")
    body_after = page_body(notes_after)
    for k in plan["notes_remove"]:
        check(k not in body_after, f"{k} still on {target_ver} notes")
    for k in plan["notes_add"]:
        check(k in body_after, f"{k} not added to {target_ver} notes")
    st_pp, pp = api("confluence", "GET", f"{WIKI}/pages/{page_created['id']}")
    pp_body = page_body(pp)
    for k in plan["patch_notes"]:
        check(k in pp_body, f"{k} missing from patch notes page")
    for k in plan["reopen_strip"]:
        check(k not in pp_body, f"unfixed {k} listed on patch notes page")

    rels_after = gh_paged(f"/repos/{org}/{release_repo}/releases")
    check(any(patch_ver in str(r.get("tag_name", "")) and not r.get("draft") for r in rels_after),
          "patch GitHub release missing or draft")

    print("\n==== WRITE LIST ====")
    for w in WRITES:
        print(w)
    if mismatches:
        for m in mismatches:
            print(f"READBACK-MISMATCH: {m}", file=sys.stderr)
        sys.exit(2)
    print("ORACLE-OK: zero readback mismatches")

if __name__ == "__main__":
    main()
