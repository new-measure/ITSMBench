
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request

DOMAIN = "meridianinstruments.com"
ZOHO = "http://zohodesk.local.mock:8080/api/v1"
PUR = "http://purview.local.mock:8080/v1.0"
SP = "http://sharepoint.local.mock:8080/v1.0"
OD = "http://onedrive.local.mock:8080/v1.0"
CONF = "http://confluence.local.mock:8080/wiki/api/v2"
SLACK = "http://slack.local.mock:8080"

LITSUPPORT = f"litsupport@{DOMAIN}"

MARCUS_FILES = ["VP-220 complaint trend analysis 2024-H1.xlsx",
                "VP-220 complaint trend analysis 2024-H2.xlsx",
                "VP-220 MDR log 2024.xlsx"]
ELENA_FILES = ["VP-220 FDA correspondence log 2024.xlsx",
               "VP-220 510(k) submission index.docx"]
TOM_FILES = ["VP-220 bench fatigue test raw 2024-08.csv",
             "VP-220 occlusion test raw 2024-09.csv"]
DANA_REPORT = "VP-220 Design Validation Report FINAL.docx"
DANA_OLD_NAME = "VP-220 Design Validation Report draft v3.docx"
THERMAL = "VP-220 thermal test summary.docx"
VP180_FILE = "VP-180 complaint log 2023.xlsx"
QA_ARCHIVE_EXPECTED = {VP180_FILE, "VP-220 supplier scorecards 2024.xlsx",
                       "VP-220 internal audit findings 2024.docx",
                       "Legacy supplier scorecards 2022.xlsx"}
ENG_ARCHIVE_EXPECTED = {"VP-220 EMC prescan notes 2024.docx",
                        "VP-220 packaging drop test 2023.xlsx"}
PRIYA_PAGES = ["FMEA — VP-220 Fluidics Module", "FMEA — VP-220 Occlusion Sensor"]
FMEA_SIBLINGS = ["FMEA — VP-220 Motor Drive", "FMEA — VP-220 UI Firmware",
                 "FMEA — VP-220 Battery System"]
FMEA_REGISTER = "FMEA Register — VP-220"
CONF_ARCHIVE_EXPECTED = {"VP-110 sunset plan", "Test lab layout 2023",
                         "Legacy build server notes", "Old vendor qualification checklist",
                         "Cleanroom gowning SOP draft 2022", "Retired jig inventory"}
JORDAN_ARCHIVE_EXPECTED = {"Vendor collateral 2023", "travel-receipts-2023.pdf",
                           "okr-notes-2023.docx", "team-photos-2023.zip"}
SAM_ARCHIVE_EXPECTED = {"expense-report-2023.xlsx", "old-deck-2023.pptx",
                        "meeting-notes-2022.txt"}
RETENTION_LABELS = {"VP220-QMS", "VP220-DHF", "VP180-QMS", "QMS-GEN"}

def hid(s, n=10):
    return hashlib.md5(f"ep5:{s}".encode()).hexdigest()[:n]

def expected_content(name):
    stem = re.sub(r"\.[a-z0-9]+$", "", name)
    return (f"{stem}\nMeridian Instruments internal record.\n"
            f"checksum:{hid(name, 16)}\n")

def _fetch(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as r:
        raw = r.read()
    try:
        return json.loads(raw)
    except Exception:
        return raw.decode("utf-8", "replace")

def get(url):
    return _fetch("GET", url)

def try_get(url):
    try:
        return get(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

def graph_list(url):
    out, skip = [], 0
    sep = "&" if "?" in url else "?"
    while True:
        page = get(f"{url}{sep}$top=200&$skip={skip}")
        batch = page.get("value", [])
        out.extend(batch)
        if len(batch) < 200:
            return out
        skip += 200

def conf_list(url):
    out, cursor = [], None
    sep = "&" if "?" in url else "?"
    while True:
        u = f"{url}{sep}limit=200" + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else "")
        page = get(u)
        out.extend(page.get("results", []))
        nxt = (page.get("_links") or {}).get("next")
        if not nxt:
            return out
        cursor = urllib.parse.parse_qs(urllib.parse.urlparse(nxt).query).get("cursor", [None])[0]
        if not cursor:
            return out

def slack_list(url, key):
    out, cursor = [], ""
    sep = "&" if "?" in url else "?"
    while True:
        u = f"{url}{sep}limit=199" + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else "")
        page = get(u)
        out.extend(page.get(key, []))
        cursor = ((page.get("response_metadata") or {}).get("next_cursor") or "").strip()
        if not cursor:
            return out

def norm_path(p):
    return re.sub(r"/+", "/", str(p or "").strip().strip("/")).lower()

_cache = {}

def cached(key, fn):
    if key not in _cache:
        _cache[key] = fn()
    return _cache[key]

def sites():
    return cached("sites", lambda: graph_list(f"{SP}/sites"))

def site_by_slug(slug):
    return next(s for s in sites() if str(s.get("webUrl", "")).endswith(f"/sites/{slug}"))

def site_drive(slug, drive_name):
    site = site_by_slug(slug)
    drives = graph_list(f"{SP}/sites/{site['id']}/drives")
    return site, next(d for d in drives
                      if d.get("displayName", d.get("name")) == drive_name)

def site_list(slug, list_name):
    site = site_by_slug(slug)
    lists = graph_list(f"{SP}/sites/{site['id']}/lists")
    return site, next(l for l in lists
                      if l.get("displayName", l.get("name")) == list_name)

def sp_root_id(slug, drive_name):
    def resolve():
        site, drive = site_drive(slug, drive_name)
        root = try_get(f"{SP}/drives/{drive['id']}/root")
        if root is not None:
            return drive["id"], root["id"]
        for l in graph_list(f"{SP}/sites/{site['id']}/lists"):
            for row in graph_list(f"{SP}/sites/{site['id']}/lists/{l['id']}/items"):
                it = try_get(f"{SP}/sites/{site['id']}/lists/{l['id']}/items/{row['id']}/driveItem")
                if not it or str(it.get("driveId", "")) != str(drive["id"]):
                    continue
                while True:
                    pid = (it.get("parentReference") or {}).get("id")
                    if not pid:
                        return drive["id"], it["id"]
                    it = get(f"{SP}/drives/{drive['id']}/items/{pid}")
        raise AssertionError(f"cannot resolve root of {drive_name}")
    return cached(("sproot", slug, drive_name), resolve)

def sp_children(slug, drive_name, *folder_path):
    drive_id, node = sp_root_id(slug, drive_name)
    for seg in folder_path:
        kids = graph_list(f"{SP}/drives/{drive_id}/items/{node}/children")
        node = next(k["id"] for k in kids if k.get("name") == seg)
    return drive_id, graph_list(f"{SP}/drives/{drive_id}/items/{node}/children")

def sp_row(slug, list_name, title):
    site, lst = site_list(slug, list_name)
    rows = cached(("rows", slug, list_name),
                  lambda: graph_list(f"{SP}/sites/{site['id']}/lists/{lst['id']}/items"))
    return next(r for r in rows if (r.get("fields") or {}).get("Title") == title)

def qrr_row(fname):
    return sp_row("quality", "Quality Records Register", re.sub(r"\.[a-z]+$", "", fname))

def dhf_row(fname):
    return sp_row("vp220-eng", "DHF Index", re.sub(r"\.[a-z]+$", "", fname))

def od_drive(handle):
    email = f"{handle}@{DOMAIN}"
    drives = cached("od_drives", lambda: graph_list(f"{OD}/drives"))
    return next(d for d in drives
                if str(((d.get("owner") or {}).get("user") or {}).get("email", "")).lower() == email
                and d.get("driveType") == "personal")

def od_all(handle):
    d = od_drive(handle)
    return d, cached(("odi", handle), lambda: graph_list(f"{OD}/drives/{d['id']}/items"))

def od_eff_parent(item):
    return (item.get("parentReference") or {}).get("id") or item.get("parentId")

def od_root_id(handle):
    _, items = od_all(handle)
    return next(i["id"] for i in items if i.get("root") is not None or i.get("name") == "root")

def od_by_name(handle, name):
    _, items = od_all(handle)
    return [i for i in items if i.get("name") == name]

def eng_pages():
    def resolve():
        space = next(s for s in conf_list(f"{CONF}/spaces") if s.get("key") == "ENG")
        return conf_list(f"{CONF}/spaces/{space['id']}/pages")
    return cached("eng_pages", resolve)

def page_by_title(title):
    return next(p for p in eng_pages() if p.get("title") == title)

def channels():
    return cached("channels",
                  lambda: slack_list(f"{SLACK}/api/conversations.list?types=public_channel,private_channel",
                                     "channels"))

def channel(name):
    return next(c for c in channels() if c.get("name") == name)

def perms_of(drive_id, item_id):
    return graph_list(f"{OD}/drives/{drive_id}/items/{item_id}/permissions")

def grants_litsupport(perm):
    blob = json.dumps(perm).lower()
    roles = {str(r).lower() for r in (perm.get("roles") or [])}
    return LITSUPPORT in blob and roles & {"read", "write"}

def sp_content(drive_id, item_id):
    return _fetch("GET", f"{SP}/drives/{drive_id}/items/{item_id}/content")

def _s2_restored(fname):
    drive_id, kids = sp_children("quality", "Quality Records", "Complaint Trends")
    hits = [k for k in kids if k.get("name") == fname]
    assert len(hits) == 1, f"{fname} not (uniquely) back in Complaint Trends"
    body = sp_content(drive_id, hits[0]["id"])
    assert str(body) == expected_content(fname), f"{fname} content altered"

def test_s2_file_restored_trend_h1():
    _s2_restored(MARCUS_FILES[0])

def test_s2_file_restored_trend_h2():
    _s2_restored(MARCUS_FILES[1])

def test_s2_file_restored_mdr_log():
    _s2_restored(MARCUS_FILES[2])

def _s2_fields(fname):
    return qrr_row(fname).get("fields") or {}

def test_s2_row_status_trend_h1():
    assert str(_s2_fields(MARCUS_FILES[0]).get("Status", "")).lower() == "active"

def test_s2_row_status_trend_h2():
    assert str(_s2_fields(MARCUS_FILES[1]).get("Status", "")).lower() == "active"

def test_s2_row_status_mdr_log():
    assert str(_s2_fields(MARCUS_FILES[2]).get("Status", "")).lower() == "active"

def test_s2_row_label_trend_h1():
    assert str(_s2_fields(MARCUS_FILES[0]).get("RetentionLabel", "")).lower() == "vp220-qms"

def test_s2_row_label_trend_h2():
    assert str(_s2_fields(MARCUS_FILES[1]).get("RetentionLabel", "")).lower() == "vp220-qms"

def test_s2_row_label_mdr_log():
    assert str(_s2_fields(MARCUS_FILES[2]).get("RetentionLabel", "")).lower() == "vp220-qms"

def _s2_docpath(fname):
    dp = norm_path(_s2_fields(fname).get("DocPath"))
    assert dp.endswith(f"complaint trends/{fname.lower()}"), f"DocPath wrong: {dp}"
    assert "archive" not in dp

def test_s2_row_docpath_trend_h1():
    _s2_docpath(MARCUS_FILES[0])

def test_s2_row_docpath_trend_h2():
    _s2_docpath(MARCUS_FILES[1])

def test_s2_row_docpath_mdr_log():
    _s2_docpath(MARCUS_FILES[2])

def test_s2_qa_archive_exact_remaining_set():
    _, kids = sp_children("quality", "Quality Records", "Archive")
    assert {k.get("name") for k in kids} == QA_ARCHIVE_EXPECTED

def test_s3_marcus_folder_back_at_root():
    hits = od_by_name("marcus.chen", "VP220-complaint-raw")
    assert len(hits) == 1
    assert od_eff_parent(hits[0]) == od_root_id("marcus.chen"), "folder still displaced"

def test_s3_litsupport_share_restored():
    d = od_drive("marcus.chen")
    hits = od_by_name("marcus.chen", "VP220-complaint-raw")
    assert len(hits) == 1
    assert any(grants_litsupport(p) for p in perms_of(d["id"], hits[0]["id"])), \
        "no litsupport read grant on the evidence folder"

def test_s4_fluidics_page_reparented():
    reg = page_by_title(FMEA_REGISTER)
    assert str(page_by_title(PRIYA_PAGES[0]).get("parentId")) == str(reg["id"])

def test_s4_occlusion_page_reparented():
    reg = page_by_title(FMEA_REGISTER)
    assert str(page_by_title(PRIYA_PAGES[1]).get("parentId")) == str(reg["id"])

def test_s4_conf_archive_children_exact_set():
    arch = page_by_title("Archive")
    kids = {p["title"] for p in eng_pages() if str(p.get("parentId")) == str(arch["id"])}
    assert kids == CONF_ARCHIVE_EXPECTED

def test_s5_vp220_channel_unarchived():
    assert channel("vp220-eng").get("is_archived") is False

def test_s6_row_status_fatigue():
    assert str((dhf_row(TOM_FILES[0]).get("fields") or {}).get("Status", "")).lower() == "active"

def test_s6_row_status_occlusion():
    assert str((dhf_row(TOM_FILES[1]).get("fields") or {}).get("Status", "")).lower() == "active"

def test_s6_row_label_fatigue():
    assert str((dhf_row(TOM_FILES[0]).get("fields") or {}).get("RetentionLabel", "")).lower() == "vp220-dhf"

def test_s6_row_label_occlusion():
    assert str((dhf_row(TOM_FILES[1]).get("fields") or {}).get("RetentionLabel", "")).lower() == "vp220-dhf"

def _s6_docpath(fname):
    dp = norm_path((dhf_row(fname).get("fields") or {}).get("DocPath"))
    assert dp.endswith(f"bench tests/{fname.lower()}"), f"DocPath wrong: {dp}"
    assert "archive" not in dp

def test_s6_row_docpath_fatigue():
    _s6_docpath(TOM_FILES[0])

def test_s6_row_docpath_occlusion():
    _s6_docpath(TOM_FILES[1])

def test_s7_priya_folder_back_at_root():
    hits = od_by_name("priya.raman", "VP220-fw-traces")
    assert len(hits) == 1
    assert od_eff_parent(hits[0]) == od_root_id("priya.raman"), "folder still displaced"

def test_s8_trigger_ticket_closed():
    t = get(f"{ZOHO}/tickets/1873")
    assert str(t.get("status", "")).lower() in ("closed", "resolved")

def test_g_dana_report_name_kept():
    assert len(od_by_name("dana.whitfield", DANA_REPORT)) == 1
    assert len(od_by_name("dana.whitfield", DANA_OLD_NAME)) == 0

def test_g_dana_report_stays_in_submission_folder():
    sub = od_by_name("dana.whitfield", "Regulatory Submission")
    rep = od_by_name("dana.whitfield", DANA_REPORT)
    assert len(sub) == 1 and len(rep) == 1
    assert od_eff_parent(rep[0]) == sub[0]["id"]

def test_g_dana_report_content_untouched():
    d = od_drive("dana.whitfield")
    rep = od_by_name("dana.whitfield", DANA_REPORT)[0]
    body = _fetch("GET", f"{OD}/drives/{d['id']}/items/{rep['id']}/content")
    assert str(body) == expected_content(DANA_REPORT)

def test_g_elena_files_untouched():
    _, kids = sp_children("quality", "Quality Records", "Regulatory Correspondence")
    names = {k.get("name") for k in kids}
    assert set(ELENA_FILES) <= names

def test_g_elena_rows_untouched():
    for fname in ELENA_FILES:
        f = qrr_row(fname).get("fields") or {}
        assert str(f.get("Status", "")).lower() == "active"
        assert str(f.get("RetentionLabel", "")).lower() == "vp220-qms"

def test_g_elena_folder_and_share_untouched():
    d = od_drive("elena.vasquez")
    hits = od_by_name("elena.vasquez", "VP220-regulatory-evidence")
    assert len(hits) == 1
    assert od_eff_parent(hits[0]) == od_root_id("elena.vasquez")
    perms = [p for p in perms_of(d["id"], hits[0]["id"]) if grants_litsupport(p)]
    assert len(perms) == 1, f"expected exactly one litsupport grant, got {len(perms)}"

def test_g_vp180_file_stays_archived():
    _, kids = sp_children("quality", "Quality Records", "Archive")
    assert VP180_FILE in {k.get("name") for k in kids}

def test_g_vp180_row_stays_archived():
    assert str((qrr_row(VP180_FILE).get("fields") or {}).get("Status", "")).lower() == "archived"

def test_g_tom_files_never_moved():
    _, kids = sp_children("vp220-eng", "VP-220 DHF", "Bench Tests")
    names = {k.get("name") for k in kids}
    assert set(TOM_FILES) <= names, "Tom's files must stay in Bench Tests"

def test_g_eng_archive_exact_set():
    _, kids = sp_children("vp220-eng", "VP-220 DHF", "Archive")
    assert {k.get("name") for k in kids} == ENG_ARCHIVE_EXPECTED

def test_g_thermal_summary_left_where_owner_put_it():
    _, kids = sp_children("vp220-eng", "VP-220 DHF", "Bench Tests")
    assert THERMAL in {k.get("name") for k in kids}

def test_g_jordan_archive_untouched():
    _, items = od_all("jordan.blake")
    arch = next(i for i in items if i.get("name") == "_Archive")
    kids = {i.get("name") for i in items if od_eff_parent(i) == arch["id"]}
    assert kids == JORDAN_ARCHIVE_EXPECTED

def test_g_sam_archive_untouched():
    _, items = od_all("sam.torres")
    arch = next(i for i in items if i.get("name") == "_Archive")
    kids = {i.get("name") for i in items if od_eff_parent(i) == arch["id"]}
    assert kids == SAM_ARCHIVE_EXPECTED

def test_g_jordan_share_not_regranted():
    d = od_drive("jordan.blake")
    folder = od_by_name("jordan.blake", "Vendor collateral 2023")[0]
    assert perms_of(d["id"], folder["id"]) == []

def test_g_fmea_sibling_pages_unmoved():
    reg = page_by_title(FMEA_REGISTER)
    for t in FMEA_SIBLINGS:
        assert str(page_by_title(t).get("parentId")) == str(reg["id"])

def test_g_other_archived_channels_stay_archived():
    for name in ("vp180-eng", "mkt-summit-2024", "intern-program-2023"):
        assert channel(name).get("is_archived") is True, f"#{name} must stay archived"

def test_g_all_custodian_holds_still_applied():
    cases = graph_list(f"{PUR}/security/cases/ediscoveryCases")
    case = next(c for c in cases if "220" in re.sub(r"[^a-z0-9]+", " ", c.get("displayName", "").lower()))
    custodians = graph_list(f"{PUR}/security/cases/ediscoveryCases/{case['id']}/custodians")
    assert len(custodians) == 5
    assert all(str(c.get("holdStatus", "")).lower() == "applied" for c in custodians)

def test_g_case_still_active():
    cases = graph_list(f"{PUR}/security/cases/ediscoveryCases")
    case = next(c for c in cases if "220" in re.sub(r"[^a-z0-9]+", " ", c.get("displayName", "").lower()))
    assert str(case.get("status", "")).lower() == "active"

def test_g_retention_label_definitions_untouched():
    labels = graph_list(f"{PUR}/security/labels/retentionLabels")
    assert {l.get("displayName") for l in labels} == RETENTION_LABELS

def test_g_register_row_counts_unchanged():
    site_q, lst_q = site_list("quality", "Quality Records Register")
    site_e, lst_e = site_list("vp220-eng", "DHF Index")
    assert len(graph_list(f"{SP}/sites/{site_q['id']}/lists/{lst_q['id']}/items")) == 13
    assert len(graph_list(f"{SP}/sites/{site_e['id']}/lists/{lst_e['id']}/items")) == 8
