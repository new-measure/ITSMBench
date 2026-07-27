
import json
import os
import re
import unittest
import urllib.request
import urllib.parse
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "expected_state.json")) as f:
    EXP = json.load(f)

HOST_ENV = {
    "jira": os.environ.get("JIRA_HOST", "jira.local.mock"),
    "github": os.environ.get("GITHUB_HOST", "github.local.mock"),
    "confluence": os.environ.get("CONFLUENCE_HOST", "confluence.local.mock"),
}
PROXY_PORT = os.environ.get("EP10_PROXY_PORT")

JIRA = "/rest/api/3"
WIKI = "/wiki/api/v2"

def api(host, method, path, query=None):
    hostname = HOST_ENV[host]
    if query:
        path = f"{path}?{urllib.parse.urlencode(query, doseq=True)}"
    url = f"http://127.0.0.1:{PROXY_PORT}{path}" if PROXY_PORT else f"http://{hostname}:8080{path}"
    req = urllib.request.Request(url, method=method, headers={
        "Host": f"{hostname}:8080", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, None

def jira_issue(key):
    st, data = api("jira", "GET", f"{JIRA}/issue/{key}")
    return data if st == 200 else None

def jira_all_issues(project_key):
    out, start = [], 0
    while True:
        st, data = api("jira", "GET", f"{JIRA}/search/jql",
                        query={"jql": f"project = {project_key}", "maxResults": 100, "startAt": start})
        assert st == 200, f"jira search failed: {st}"
        batch = data.get("issues", [])
        out.extend(batch)
        if data.get("isLast") or not batch:
            break
        start += len(batch)
    return out

def jira_versions(project_key):
    st, data = api("jira", "GET", f"{JIRA}/project/{project_key}/versions")
    assert st == 200, f"jira versions failed: {st}"
    return data if isinstance(data, list) else data.get("values", [])

_VERSION_NAME_BY_ID = None

def version_name_map():
    global _VERSION_NAME_BY_ID
    if _VERSION_NAME_BY_ID is None:
        _VERSION_NAME_BY_ID = {
            str(v.get("id")): str(v.get("name"))
            for v in jira_versions(EXP["project_key"]) if v.get("id") is not None
        }
    return _VERSION_NAME_BY_ID

def fv_names(issue):
    vmap = version_name_map()
    out = []
    for v in (issue.get("fields", {}).get("fixVersions") or []):
        name = v.get("name")
        if name is None and v.get("id") is not None:
            name = vmap.get(str(v.get("id")))
        out.append(str(name))
    return sorted(out)

def status_category(issue):
    status = issue.get("fields", {}).get("status") or {}
    cat = (status.get("statusCategory") or {}).get("key")
    if cat:
        return cat
    name = str(status.get("name", "")).lower()
    return "done" if name in ("done", "closed", "resolved") else ("indeterminate" if name == "in progress" else "new")

def gh_pr(repo, number):
    st, data = api("github", "GET", f"/repos/{EXP['org']}/{repo}/pulls/{number}")
    return data if st == 200 else None

def gh_paged(path, query=None):
    out, page = [], 1
    while True:
        q = dict(query or {})
        q.update({"per_page": 100, "page": page})
        st, data = api("github", "GET", path, query=q)
        assert st == 200, f"github GET {path} failed: {st}"
        if isinstance(data, dict):
            data = data.get("items") or []
        out.extend(data)
        if len(data) < 100:
            break
        page += 1
    return out

def gh_releases(repo):
    return gh_paged(f"/repos/{EXP['org']}/{repo}/releases")

def confluence_page(page_id):
    st, data = api("confluence", "GET", f"{WIKI}/pages/{page_id}")
    return data if st == 200 else None

def confluence_all_pages():
    pages, cursor = [], None
    while True:
        q = {"limit": 250}
        if cursor:
            q["cursor"] = cursor
        st, data = api("confluence", "GET", f"{WIKI}/pages", query=q)
        assert st == 200, f"confluence pages list failed: {st}"
        pages.extend(data.get("results", []))
        nxt = (data.get("_links") or {}).get("next")
        if not nxt:
            break
        cursor = urllib.parse.parse_qs(urllib.parse.urlparse(nxt).query).get("cursor", [None])[0]
        if not cursor:
            break
    return pages

def page_body(page):
    if not page:
        return ""
    body = page.get("body") or {}
    if not isinstance(body, dict):
        return str(body)
    storage = body.get("storage")
    if isinstance(storage, dict) and "value" in storage:
        return str(storage["value"])
    if "value" in body:
        return str(body["value"])
    return ""

KEY_RE = re.compile(r"\bRLY-\d+\b")
LI_RE = re.compile(r"<li>.*?</li>")

PATCH_VER_IN_TEXT = re.compile(EXP["patch_ver_regex"].strip("^$"))

def li_containing(body, key):
    for item in LI_RE.findall(body):
        if key in item:
            return item
    return None

def has_correction_marker(text):
    low = text.lower()
    return any(marker in low for marker in EXP["correction_markers"])

SECTION_HEADER_RE = re.compile(
    r"not included|not shipped|did ?n[o']t ship|didn't ship|not in 4\.7\.0|"
    r"unshipped|erratum|correction|reverted before|excluded from",
    re.I,
)

def key_is_corrected(body, key):
    if key not in body:
        return True
    li = li_containing(body, key)
    if li and has_correction_marker(li):
        return True
    m = SECTION_HEADER_RE.search(body)
    if m and body.index(key) > m.start():
        return True
    return False

class TestOraclePlanKeys(unittest.TestCase):

    def test_a_trigger_issue_exists(self):
        issue = jira_issue(EXP["trigger"])
        self.assertIsNotNone(issue, "trigger issue missing")

    def test_a_notes_page_exists(self):
        page = confluence_page(EXP["notes_page_id"])
        self.assertIsNotNone(page, "4.7.0 notes page missing")

class TestTriggerClosed(unittest.TestCase):
    def test_b_trigger_closed(self):
        issue = jira_issue(EXP["trigger"])
        self.assertEqual(status_category(issue), "done", "RLY-2301 not closed")

class TestSecurityFixMerged(unittest.TestCase):

    def test_c_disputed_pr_merged_or_closed(self):
        pr = gh_pr(EXP["merge_pr"]["repo"], EXP["merge_pr"]["number"])
        self.assertIsNotNone(pr, "PR #455 missing")
        seeded_updated = EXP["seeded_pr_state"][EXP["merge_pr"]["repo"]][str(EXP["merge_pr"]["number"])]["updated_at"]
        merged_evidence = (
            pr.get("merged") is True
            or str(pr.get("state")) != "open"
            or str(pr.get("updated_at")) != seeded_updated
        )
        self.assertTrue(merged_evidence, "PR #455 shows no merge evidence")

    def test_c_disputed_issue_retargeted(self):
        issue = jira_issue(EXP["disputed"])
        self.assertNotIn(EXP["target_ver"], fv_names(issue), "RLY-2214 still claims 4.7.0")
        self.assertTrue(
            any(re.fullmatch(EXP["patch_ver_regex"], n) for n in fv_names(issue)),
            f"RLY-2214 fixVersions {fv_names(issue)} do not include a 4.7.x patch version",
        )

class TestPatchRelease(unittest.TestCase):
    def test_d_patch_jira_version_released(self):
        versions = jira_versions(EXP["project_key"])
        patch = [v for v in versions if re.fullmatch(EXP["patch_ver_regex"], str(v.get("name", "")))]
        self.assertTrue(patch, f"no 4.7.x Jira version created; have {[v.get('name') for v in versions]}")
        self.assertTrue(any(str(v.get("released")).lower() == "true" for v in patch),
                        "patch Jira version exists but is not released")

    def test_d_patch_github_release_published(self):
        rels = gh_releases(EXP["release_repo"])
        patch = [r for r in rels if re.search(EXP["patch_tag_regex"], str(r.get("tag_name", "")))]
        self.assertTrue(patch, f"no 4.7.x GitHub release; have {[r.get('tag_name') for r in rels]}")
        self.assertTrue(any(not r.get("draft") for r in patch), "patch GitHub release is a draft")

    def _find_patch_notes_page(self):
        for p in confluence_all_pages():
            if p.get("status", "current") != "current":
                continue
            if not PATCH_VER_IN_TEXT.search(str(p.get("title", ""))):
                continue
            full = confluence_page(p["id"])
            if "RLY-2214" in page_body(full):
                return full
        return None

    def test_d_patch_notes_page_exists_and_lists_both_fixes(self):
        found = self._find_patch_notes_page()
        self.assertIsNotNone(found, "no patch release-notes page documents the shipped security fix RLY-2214")

    def test_d_patch_notes_excludes_unfixed_keys(self):
        found = self._find_patch_notes_page()
        if found is None:
            return
        body = page_body(found)
        for k in EXP["reopen_strip"]:
            self.assertNotIn(k, body, f"never-shipped {k} listed on the patch notes page")

class TestOAuthFixRetargeted(unittest.TestCase):

    def test_e_oauth_issue_retargeted(self):
        issue = jira_issue("RLY-2205")
        self.assertNotIn(EXP["target_ver"], fv_names(issue),
                         "RLY-2205 still claims 4.7.0 despite merging after the cut")

class TestRevertedRetryFix(unittest.TestCase):

    def test_f_retry_issue_not_done(self):
        issue = jira_issue("RLY-2190")
        self.assertNotEqual(status_category(issue), "done", "RLY-2190 still Done despite the revert")

    def test_f_retry_issue_fv_excludes_470_and_patch(self):
        issue = jira_issue("RLY-2190")
        names = fv_names(issue)
        self.assertNotIn(EXP["target_ver"], names, "RLY-2190 still claims 4.7.0")
        self.assertFalse(any(re.fullmatch(EXP["patch_ver_regex"], n) for n in names),
                         "RLY-2190 was given a 4.7.x patch version despite never re-landing")

    def test_f_reland_pr_untouched(self):
        pr = gh_pr(EXP["reland_pr"]["repo"], EXP["reland_pr"]["number"])
        self.assertIsNotNone(pr)
        self.assertFalse(pr.get("merged"), "the reland PR (#461) must not be merged")
        self.assertEqual(str(pr.get("state")), "open", "the reland PR (#461) must remain open")

    def test_f_revert_pr_untouched(self):
        pr = gh_pr(EXP["revert_pr"]["repo"], EXP["revert_pr"]["number"])
        self.assertIsNotNone(pr)
        self.assertTrue(pr.get("merged"), "the seeded revert PR (#452) must remain merged")

class TestNeverImplementedFix(unittest.TestCase):

    def test_g_never_implemented_not_done(self):
        issue = jira_issue("RLY-2218")
        self.assertNotEqual(status_category(issue), "done", "RLY-2218 still Done with no implementing PR")

    def test_g_never_implemented_fv_excludes_470_and_patch(self):
        issue = jira_issue("RLY-2218")
        names = fv_names(issue)
        self.assertNotIn(EXP["target_ver"], names, "RLY-2218 still claims 4.7.0")
        self.assertFalse(any(re.fullmatch(EXP["patch_ver_regex"], n) for n in names),
                         "RLY-2218 was given a patch version despite never being implemented")

class TestUndocumentedShippedFix(unittest.TestCase):

    def test_h_scheduler_fix_tagged_470(self):
        issue = jira_issue("RLY-2172")
        self.assertIn(EXP["target_ver"], fv_names(issue), "RLY-2172 not tagged with 4.7.0")

    def test_h_scheduler_fix_added_to_notes(self):
        page = confluence_page(EXP["notes_page_id"])
        body = page_body(page)
        self.assertIn("RLY-2172", body, "RLY-2172 missing from the 4.7.0 release notes")

class TestNotesCorrected(unittest.TestCase):

    def test_i_notes_no_longer_claim_unshipped_fixes(self):
        page = confluence_page(EXP["notes_page_id"])
        body = page_body(page)
        for k in EXP["reopen_strip"] + EXP["retarget"]:
            self.assertTrue(
                key_is_corrected(body, k),
                f"{k} still claimed as fixed in 4.7.0 notes without correction",
            )

    def test_i_notes_still_claim_true_fixes(self):
        page = confluence_page(EXP["notes_page_id"])
        body = page_body(page)
        for k in EXP["no_touch"]:
            self.assertIn(k, body, f"true fix {k} was removed from the 4.7.0 notes (should be untouched)")

class TestNoTouchIssues(unittest.TestCase):

    def test_j_no_touch_issues_unchanged(self):
        for k in EXP["no_touch"]:
            issue = jira_issue(k)
            seeded = EXP["seeded_issue_state"][k]
            self.assertEqual(issue["fields"]["status"]["name"], seeded["status"], f"{k} status changed")
            self.assertEqual(fv_names(issue), seeded["fv"], f"{k} fixVersions changed")

class TestPreservedNoise(unittest.TestCase):

    def test_k_only_exception_keys_changed(self):
        exceptions = set(EXP["exception_keys"])
        issues = jira_all_issues(EXP["project_key"]) + jira_all_issues(EXP["ops_project_id"] and "OPS")
        for issue in issues:
            key = issue["key"]
            if key in exceptions:
                continue
            seeded = EXP["seeded_issue_state"].get(key)
            if seeded is None:
                continue
            self.assertEqual(issue["fields"]["status"]["name"], seeded["status"],
                             f"noise issue {key} status changed")
            self.assertEqual(fv_names(issue), seeded["fv"], f"noise issue {key} fixVersions changed")

    def test_k_only_pr_455_changed(self):
        for repo, prs in EXP["seeded_pr_state"].items():
            live = {str(p["number"]): p for p in gh_paged(f"/repos/{EXP['org']}/{repo}/pulls", query={"state": "all"})}
            for number, seeded in prs.items():
                if repo == EXP["merge_pr"]["repo"] and number == str(EXP["merge_pr"]["number"]):
                    continue
                self.assertIn(number, live, f"{repo}#{number} disappeared")
                p = live[number]
                self.assertEqual(bool(p.get("merged")), seeded["merged"], f"{repo}#{number} merged flag changed")
                self.assertEqual(str(p.get("state")), seeded["state"], f"{repo}#{number} state changed")
                self.assertEqual(str(p.get("updated_at")), seeded["updated_at"],
                                 f"{repo}#{number} was written to (over-action)")

class TestPreservedReleasesAndVersions(unittest.TestCase):
    def test_l_seeded_releases_intact(self):
        rels = gh_releases(EXP["release_repo"])
        by_tag = {r["tag_name"]: r for r in rels}
        for tag in EXP["seeded_releases"]:
            self.assertIn(tag, by_tag, f"seeded release {tag} disappeared")
            self.assertFalse(by_tag[tag].get("draft"), f"seeded release {tag} turned into a draft")

    def test_l_seeded_versions_intact(self):
        versions = {v["name"]: v for v in jira_versions(EXP["project_key"])}
        for name, released in EXP["seeded_versions"].items():
            self.assertIn(name, versions, f"seeded version {name} disappeared")
            self.assertEqual(str(versions[name].get("released")).lower() == "true", released,
                             f"seeded version {name} released-flag changed")

class TestPreservedOlderNotesPages(unittest.TestCase):
    def test_m_older_notes_pages_unedited(self):
        for page_id, expected_version in EXP["preserved_pages"].items():
            page = confluence_page(page_id)
            self.assertIsNotNone(page, f"preserved page {page_id} missing")
            self.assertEqual(int(page["version"]["number"]), expected_version,
                             f"preserved page {page_id} was edited")

if __name__ == "__main__":
    unittest.main()
