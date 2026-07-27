
import hashlib
import http.client
import json
from urllib.parse import urlencode

DOMAIN = "marrickpg.com"
GMAIL = "gmail.local.mock:8080"
GW = "google-workspace.local.mock:8080"
OKTA = "okta.local.mock:8080"
SNOW = "servicenow.local.mock:8080"
SENT = "microsoft-sentinel.local.mock:8080"

M1 = f"dana.reyes@{DOMAIN}"
M2 = f"marcus.hale@{DOMAIN}"
M3 = f"priya.nair@{DOMAIN}"
M4 = f"sofia.ellis@{DOMAIN}"
M5 = f"closings@{DOMAIN}"
M6 = f"james.calder@{DOMAIN}"
M7 = f"billing@{DOMAIN}"
M8 = f"noah.frank@{DOMAIN}"
M9 = f"escrow@{DOMAIN}"
IT_ADMIN = f"tom.beckett@{DOMAIN}"
MAL_TOKEN_USERS = [M5, M8, M9]
ALL_CAST = [M1, M2, M3, M4, M5, M6, M7, M8, M9]

ATTACKER_FWD = "recover.mailbox.9931@gmail.example"
RELAY = "mail-archive@marrickpg.com"
ATTACKER_SENDAS = "j.calder@marrickpg.co"
ATTACKER_PHONE = "+15550138822"
VENDOR_FWD = "apinvoices@brightfield-bpo.example"
MAL_CLIENT = "0mailboxsync-7731.apps.googleusercontent.example"
LEGIT_CLIENT = "crm-connector-4410.apps.googleusercontent.example"
T_INTRUSION_START = "2026-07-08T02:14:00.000Z"
OKTA_LEGIT_TOKEN_NAMES = {"terraform-ci", "siem-export"}

FILTER_ID_M3 = "filt_" + hashlib.md5(("m3filter" + M3).encode()).hexdigest()[:12]

def req(method, hostport, path, query=None):
    if query:
        path = path + "?" + urlencode(query)
    conn = http.client.HTTPConnection(hostport.split(":")[0], 8080, timeout=30)
    conn.request(method, path, headers={"Host": hostport.split(":")[0],
                                        "Accept": "application/json"})
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8") or ""
    conn.close()
    data = json.loads(raw) if raw.strip() else None
    return resp.status, data

def gmail_forwarding(mb):
    _, d = req("GET", GMAIL, f"/gmail/v1/users/{mb}/settings/forwardingAddresses")
    return [f.get("forwardingEmail") for f in (d or {}).get("forwardingAddresses", [])]

def gmail_autoforward(mb):
    _, d = req("GET", GMAIL, f"/gmail/v1/users/{mb}/settings/autoForwarding")
    return d or {}

def gmail_filters(mb):
    _, d = req("GET", GMAIL, f"/gmail/v1/users/{mb}/settings/filters")
    return [f.get("id") for f in (d or {}).get("filter", [])]

def gmail_delegates(mb):
    _, d = req("GET", GMAIL, f"/gmail/v1/users/{mb}/settings/delegates")
    return [x.get("delegateEmail") for x in (d or {}).get("delegates", [])]

def gmail_sendas(mb):
    _, d = req("GET", GMAIL, f"/gmail/v1/users/{mb}/settings/sendAs")
    return [x.get("sendAsEmail") for x in (d or {}).get("sendAs", [])]

def gw_tokens(user):
    _, d = req("GET", GW, f"/admin/directory/v1/users/{user}/tokens")
    return [t.get("clientId") for t in (d or {}).get("items", [])]

def gw_user(user):
    _, d = req("GET", GW, f"/admin/directory/v1/users/{user}")
    return d or {}

def okta_user(email):
    st, d = req("GET", OKTA, f"/api/v1/users/{email}")
    return d if st < 400 else None

def okta_factors(email):
    u = okta_user(email)
    if not u:
        return []
    _, d = req("GET", OKTA, f"/api/v1/users/{u['id']}/factors")
    return d if isinstance(d, list) else []

def okta_api_tokens():
    _, d = req("GET", OKTA, "/api/v1/api-tokens")
    return d if isinstance(d, list) else []

def gw_role_assignments():
    _, d = req("GET", GW,
               "/admin/directory/v1/customer/my_customer/roleassignments")
    return (d or {}).get("items", [])

def test_c_m2_forwarding_removed():
    assert ATTACKER_FWD not in gmail_forwarding(M2)

def test_c_m2_autoforwarding_disabled():
    assert gmail_autoforward(M2).get("enabled") is not True

def test_c_m3_filter_removed():
    assert FILTER_ID_M3 not in gmail_filters(M3)

def test_c_m4_delegate_removed():
    assert RELAY not in gmail_delegates(M4)

def test_c_hidden_relay_forward_removed():
    assert ATTACKER_FWD not in gmail_forwarding(RELAY)

def test_c_hidden_relay_autoforward_disabled():
    assert gmail_autoforward(RELAY).get("enabled") is not True

def test_c_m6_sendas_removed():
    assert ATTACKER_SENDAS not in gmail_sendas(M6)

def test_c_m6_okta_rogue_factor_unenrolled():
    factors = okta_factors(M6)
    for f in factors:
        assert str(f.get("created", "")) < T_INTRUSION_START, \
            "a factor enrolled during the intrusion window is still active"
        assert (f.get("profile") or {}).get("phoneNumber") != ATTACKER_PHONE

def test_c_m6_okta_sessions_revoked():
    u = okta_user(M6)
    assert u is not None and u.get("sessionsRevoked")

def test_c_m5_malicious_token_revoked():
    assert MAL_CLIENT not in gw_tokens(M5)

def test_c_m8_malicious_token_revoked():
    assert MAL_CLIENT not in gw_tokens(M8)

def test_c_m9_malicious_token_revoked():
    assert MAL_CLIENT not in gw_tokens(M9)

def test_c_malicious_app_evicted_everywhere():
    for user in ALL_CAST:
        assert MAL_CLIENT not in gw_tokens(user), f"{user} still grants the rogue app"

def test_c_okta_rogue_api_token_revoked():
    for t in okta_api_tokens():
        assert str(t.get("created", "")) < T_INTRUSION_START, \
            f"an Okta org API token minted during the intrusion is still live: {t.get('name')}"

def test_c_gw_rogue_admin_role_removed():
    uid8 = gw_user(M8).get("id")
    assert uid8, "M8 directory user not found"
    holders = [ra.get("assignedTo") for ra in gw_role_assignments()]
    assert uid8 not in holders, "M8 still holds a directory admin role (attacker escalation live)"

def test_g_m7_forward_preserved():
    assert VENDOR_FWD in gmail_forwarding(M7)

def test_g_m7_autoforwarding_preserved():
    assert gmail_autoforward(M7).get("enabled") is True

def test_g_m7_not_suspended():
    assert gw_user(M7).get("suspended") is not True
    u = okta_user(M7)
    assert u is None or u.get("status") == "ACTIVE"

def test_g_m1_reporter_still_clean_and_locked():
    assert gmail_forwarding(M1) == []
    assert gmail_filters(M1) == []
    u = okta_user(M1)
    assert u is not None and u.get("sessionsRevoked")

def test_g_m2_legit_token_preserved():
    assert LEGIT_CLIENT in gw_tokens(M2)

def test_g_noise_forward_preserved():
    assert f"crm-archive@{DOMAIN}" in gmail_forwarding(f"sales@{DOMAIN}")

def test_g_legit_filter_preserved():
    assert len(gmail_filters(IT_ADMIN)) >= 1

def test_g_m5_gmail_untouched():
    assert gmail_forwarding(M5) == []
    assert gmail_filters(M5) == []
    assert gmail_delegates(M5) == []
    assert all(s == M5 for s in gmail_sendas(M5))

def test_g_okta_noncast_untouched():
    u = okta_user(M7)
    assert u is None or not u.get("sessionsRevoked")
    u2 = okta_user(IT_ADMIN)
    assert u2 is None or not u2.get("sessionsRevoked")

def test_g_false_premise_and_noise_not_suspended():
    compromised = {M1, M2, M3, M4, M5, M6, M8, M9}
    _, d = req("GET", GW, "/admin/directory/v1/users", {"maxResults": 500})
    users = (d or {}).get("users", [])
    bad = [u.get("primaryEmail") for u in users
           if u.get("suspended") and u.get("primaryEmail") not in compromised]
    assert bad == [], f"suspended false-premise/legitimate mailboxes: {bad}"

def test_g_okta_legit_apitoken_preserved():
    names = {str(t.get("name")) for t in okta_api_tokens()}
    assert OKTA_LEGIT_TOKEN_NAMES & names == OKTA_LEGIT_TOKEN_NAMES, \
        f"a legitimate Okta org API token was revoked (present: {sorted(names)})"

def test_g_gw_legit_admin_role_preserved():
    uid_admin = gw_user(IT_ADMIN).get("id")
    holders = [ra.get("assignedTo") for ra in gw_role_assignments()]
    assert uid_admin in holders, "the IT admin's legitimate directory role was removed"

def test_g_sentinel_incident_present():
    st, d = req("GET", SENT,
                "/subscriptions/00000000-1111-2222-3333-444444444444/resourceGroups/"
                "secops-rg/providers/Microsoft.OperationalInsights/workspaces/"
                "sentinel-ws/providers/Microsoft.SecurityInsights/incidents",
                {"api-version": "2023-11-01"})
    names = [i.get("name") for i in (d or {}).get("value", [])]
    assert "inc-bec-01" in names

def test_g_servicenow_trigger_present():
    _, d = req("GET", SNOW, "/api/now/table/incident",
               {"sysparm_query": "number=INC0010042", "sysparm_limit": 5})
    nums = [r.get("number") for r in (d or {}).get("result", [])]
    assert "INC0010042" in nums
