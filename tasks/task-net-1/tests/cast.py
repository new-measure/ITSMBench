
import hashlib

TOOLS = ["servicenow", "device42", "infoblox-nios", "haproxy", "zscaler-zia", "aws-vpc"]

NOW = "2026-05-12T14:00:00Z"
ZONE = "meridianfoods.net"

OLD_SUBNET = "10.40.11"
NEW_SUBNET = "10.41.11"
OLD_CIDR = f"{OLD_SUBNET}.0/24"
NEW_CIDR = f"{NEW_SUBNET}.0/24"
LOOKALIKE_SUBNET = "10.40.12"

def hid(key: str) -> str:
    return hashlib.md5(f"task-net-1v2:{key}".encode()).hexdigest()

def serial_for(key: str) -> str:
    return "MFG" + hashlib.md5(f"task-net-1v2:serial:{key}".encode()).hexdigest()[:9].upper()

def device_id_for(name: str) -> int:
    return 1000 + int(hashlib.md5(f"task-net-1v2:dev:{name}".encode()).hexdigest()[:8], 16) % 900000

USERS_CAST = {
    "jchen": ("jchen", "Justin Chen", "Network Engineer III", "Network Engineering", "true"),
    "etorres": ("etorres", "Emily Torres", "Systems Engineer II", "Infrastructure", "true"),
    "praghavan": ("praghavan", "Priya Raghavan", "Manager, Network Engineering", "Network Engineering", "true"),
    "svc-netops-sync": ("svc-netops-sync", "NetOps Sync Automation", "Service Account", "Network Engineering", "true"),
    "abarnes": ("abarnes", "Aaron Barnes", "Store Operations Manager", "Store Ops", "true"),
}
NOISE_USERS = ["kpatel", "lnguyen", "mrossi", "tszabo", "gfischer", "ryamada", "solsen",
               "cdubois", "fmartin", "bkumar", "eherrera", "wclark", "npopov", "imendes"]

def user_sysid(user: str) -> str:
    return hid(f"sys_user:{user}")

T = {
    "wave0_audit": "2026-02-20T10:00:00Z",
    "wave1_night": "2026-03-24T22",
    "wave1_close": "2026-03-24 22:19:02",
    "wave2_night": "2026-03-31T22",
    "wave2_last_write": "2026-03-31T22:41:00Z",
    "wave2_close": "2026-03-31 22:47:11",
    "scalehub_handfix": "2026-04-03T09:25:00Z",
    "vlan_shutdown": "2026-05-11 22:31:44",
    "incident_opened": "2026-05-12 06:41:17",
}

HOSTS = {
    "srv-storefront-01":   (21, 1), "srv-storefront-02": (22, 1),
    "srv-wh-ctl-01":       (25, 1), "srv-print-01":      (40, 1),
    "srv-ad-dc-01":        (41, 1), "srv-ad-dc-02":      (42, 1),
    "srv-dhcp-01":         (43, 1), "srv-monitor-01":    (44, 1),
    "srv-backup-proxy-01": (45, 1), "srv-label-print-01": (46, 1),
    "srv-checkout-01":     (51, 2), "srv-checkout-02":   (52, 2),
    "srv-erp-app-01":      (23, 2), "srv-erp-db-01":     (24, 2),
    "srv-mq-relay-01":     (35, 2), "srv-bi-portal-01":  (26, 2),
    "srv-grocery-api-01":  (30, 2), "srv-grocery-api-02": (31, 2),
    "srv-voice-ivr-01":    (47, 2),
    "mfg-payrelay-01":     (61, 0), "mfg-scalehub-01":   (62, 0),
    "mfg-batchprint-01":   (63, 0), "mfg-coldvault-gw-01": (64, 0),
    "mfg-timeclock-01":    (65, 0),
}

RENUMBER_MAP = {}
for _i, _name in enumerate(sorted(HOSTS)):
    RENUMBER_MAP[_name] = (f"{OLD_SUBNET}.{HOSTS[_name][0]}", f"{NEW_SUBNET}.{10 + _i}")

def old_ip(host):
    return RENUMBER_MAP[host][0]

def new_ip(host):
    return RENUMBER_MAP[host][1]

SKIPPED = sorted(h for h, (_, w) in HOSTS.items() if w == 0)
WAVE1 = sorted(h for h, (_, w) in HOSTS.items() if w == 1)
WAVE2 = sorted(h for h, (_, w) in HOSTS.items() if w == 2)

TRIGGER_INCIDENT = "INC0052841"
BLAMED_CHANGE = "CHG0041580"
PROGRAM_CR = "CHG0041500"
WAVE_CRS = {"wave1": "CHG0041521", "wave2": "CHG0041534"}

RESIDUAL_DNS = {f"{h}.{ZONE}": h for h in ["mfg-payrelay-01", "mfg-batchprint-01", "mfg-timeclock-01"]}
HANDFIXED_DNS = f"mfg-scalehub-01.{ZONE}"
GUARD_CNAME = (f"clock.{ZONE}", f"mfg-timeclock-01.{ZONE}")
NO_DNS_HOST = "mfg-coldvault-gw-01"

LB_BACKENDS = {
    "be_checkout":     [("checkout-01", "srv-checkout-01", 8443), ("checkout-02", "srv-checkout-02", 8443)],
    "be_erp_app":      [("erp-app-01", "srv-erp-app-01", 8009)],
    "be_bi_portal":    [("bi-portal-01", "srv-bi-portal-01", 8080)],
    "be_grocery_api":  [("grocery-api-01", "srv-grocery-api-01", 8443), ("grocery-api-02", "srv-grocery-api-02", 8443)],
    "be_storefront_web": [("storefront-01", "srv-storefront-01", 8080), ("storefront-02", "srv-storefront-02", 8080)],
    "be_wh_ctl_api":   [("wh-ctl-01", "srv-wh-ctl-01", 9443)],
    "be_label_api":    [("label-print-01", "srv-label-print-01", 9100)],
    "be_payrelay":     [("payrelay-01", "mfg-payrelay-01", 8443)],
}
STALE_CONFIG_SERVERS = {"checkout-02", "erp-app-01", "payrelay-01"}
STALE_RUNTIME_BACKENDS = ["be_checkout", "be_erp_app", "be_bi_portal", "be_grocery_api", "be_payrelay"]

ZIA_RULE_COUNT = 118
ZIA_SCALEHUB_RULE = ("allow-scalehub-metrics", 107, "mfg-scalehub-01")
ZIA_COLDVAULT_RULE = ("allow-coldvault-telemetry", 113, "mfg-coldvault-gw-01")
ZIA_HALL1_GROUP = ("grp-dcw-hall1", 13)
ZIA_LOOKALIKE_GROUP = ("grp-dcw-h1-ot", 18)

SG_RESIDUALS = [
    ("sg-0d41e7f2a83c5b901", "sg-dw-etl", 5439, "srv-mq-relay-01"),
    ("sg-0e52f8a3b94d6c012", "sg-payments-svc", 8443, "mfg-payrelay-01"),
    ("sg-0f63a9b4c05e7d123", "sg-coldchain-ingest", 9443, "mfg-coldvault-gw-01"),
]
SG_WAVE1_DONE = ("sg-0a30b5c6d17f8e234", "sg-backup-vault", 8200, "srv-backup-proxy-01")

VPC_ID = "vpc-0a48c2e97b3d11f60"
ALB_SG = "sg-02b7e6f4a91c3d508"

def incident_sysid(number: str) -> str:
    return hid(f"incident:{number}")

def cr_sysid(number: str) -> str:
    return hid(f"change_request:{number}")

def ctask_sysid(number: str) -> str:
    return hid(f"change_task:{number}")
