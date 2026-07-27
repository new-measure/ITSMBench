#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

ENTRA = "http://entra-id-governance.local.mock:8080/v1.0"
OKTA = "http://okta.local.mock:8080/api/v1"
SN = "http://servicenow.local.mock:8080/api/now/table"
INCIDENT_NUMBER = "INC0030001"
BROAD_SCOPES = {"allMemberUsers", "allDirectoryUsers", "allExternalUsers",
                "allConfiguredConnectedOrganizationUsers", "allDirectoryServicePrincipals",
                "allDirectoryAgentIdentities"}
MISMATCHES = []

def call(method, url, body=None, form=False):
    data, headers = None, {"Accept": "application/json"}
    if form:
        data = urllib.parse.urlencode(body or {}).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
        return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:200]}

def get(url):
    return call("GET", url)

def values(d):
    return d.get("value", []) if isinstance(d, dict) else (d if isinstance(d, list) else [])

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

incidents = get(SN + "/incident")
incidents = incidents.get("result", []) if isinstance(incidents, dict) else []
cur = next((i for i in incidents if str(i.get("number")) == INCIDENT_NUMBER), None)
assert cur, "incident not found"
inc_sys = str(cur["sys_id"])
choices = get(SN + "/sys_choice")
choices = choices.get("result", []) if isinstance(choices, dict) else []
closed = [str(c.get("value")) for c in choices if str(c.get("name")) == "incident"
          and str(c.get("element")) == "state" and str(c.get("label", "")).lower() in ("resolved", "closed")]
CLOSED = closed[-1] if closed else "7"
print("incident %s sys_id=%s -> close state %s" % (INCIDENT_NUMBER, inc_sys, CLOSED))

defs = values(get(ENTRA + "/identityGovernance/accessReviews/definitions"))
okta_users = values(get(OKTA + "/users"))
okta_groups = values(get(OKTA + "/groups"))
okta_apps = values(get(OKTA + "/apps"))
group_by_name = {str(g.get("profile", {}).get("name", "")).lower(): g for g in okta_groups}
app_by_label = {str(a.get("label", "")).lower(): a for a in okta_apps}
policies = values(get(ENTRA + "/identityGovernance/entitlementManagement/assignmentPolicies"))

applied_instances = []
tightened_policies = []
revoked = {"role": [], "group": [], "app": []}

for d in defs:
    insts = values(get(ENTRA + "/identityGovernance/accessReviews/definitions/%s/instances" % d["id"]))
    for inst in insts:
        decs = values(get(ENTRA + "/identityGovernance/accessReviews/definitions/%s/instances/%s/decisions"
                          % (d["id"], inst["id"])))
        denies = [x for x in decs if str(x.get("decision")) == "Deny"]
        instance_had_live_gap = False
        for dec in denies:
            principal = str((dec.get("principal") or {}).get("id"))
            resource = dec.get("resource") or {}
            rtype = str(resource.get("type", "")).lower()
            rname = str(resource.get("displayName", ""))
            rid = str(resource.get("id", ""))

            if rtype in ("directoryrole", "role") or rid in {"SUPER_ADMIN", "ORG_ADMIN", "APP_ADMIN", "USER_ADMIN", "REPORT_ADMIN", "GROUP_MEMBERSHIP_ADMIN"}:
                roles = values(get(OKTA + "/users/%s/roles" % principal))
                for r in roles:
                    if str(r.get("label", "")).lower() == rname.lower() or str(r.get("type", "")) == rid:
                        call("DELETE", OKTA + "/users/%s/roles/%s" % (principal, r["id"]))
                        revoked["role"].append((principal, r.get("type")))
                        instance_had_live_gap = True

            elif rtype == "group":
                g = group_by_name.get(rname.lower())
                if g:
                    members = {str(u.get("id")) for u in values(get(OKTA + "/groups/%s/users" % g["id"]))}
                    if principal in members:
                        call("DELETE", OKTA + "/groups/%s/users/%s" % (g["id"], principal))
                        revoked["group"].append((principal, g["id"]))
                        instance_had_live_gap = True

            elif rtype in ("serviceprincipal", "application", "app"):
                a = app_by_label.get(rname.lower())
                if a:
                    assigned = {str(u.get("id")) for u in values(get(OKTA + "/apps/%s/users" % a["id"]))}
                    if principal in assigned:
                        call("DELETE", OKTA + "/apps/%s/users/%s" % (a["id"], principal))
                        revoked["app"].append((principal, a["id"]))
                        instance_had_live_gap = True

            elif rtype == "accesspackage":
                for p in policies:
                    if str((p.get("accessPackage") or {}).get("id")) == rid:
                        if str(p.get("allowedTargetScope")) in BROAD_SCOPES:
                            call("PUT", ENTRA + "/identityGovernance/entitlementManagement/assignmentPolicies/%s" % p["id"],
                                 body={"allowedTargetScope": "specificDirectoryUsers",
                                       "requestApprovalSettings": {"isApprovalRequiredForAdd": True}})
                            tightened_policies.append(p["id"])
                            instance_had_live_gap = True

        if instance_had_live_gap and str(inst.get("status")) != "Completed":
            call("POST", ENTRA + "/identityGovernance/accessReviews/definitions/%s/instances/%s/applyDecisions"
                 % (d["id"], inst["id"]))
            applied_instances.append(inst["id"])

print("revoked roles=%d groups=%d apps=%d | tightened policies=%s | applied instances=%s"
      % (len(revoked["role"]), len(revoked["group"]), len(revoked["app"]), tightened_policies, applied_instances))

call("PATCH", SN + "/incident/%s" % inc_sys,
     body={"state": CLOSED, "close_code": "Solved (Permanently)",
           "close_notes": "Reconciled every Q3 certification decision to the live access it governed: revoked the "
                          "certified-for-removal admin roles, group memberships and application assignments still "
                          "active in the identity provider, applied the open review instance, and restricted the "
                          "over-broad entitlement-package assignment policies the campaign flagged. Approved access "
                          "and out-of-scope reviews were left unchanged."})

print("\n--- readback ---")

def role_types(uid):
    return {str(r.get("type")) for r in values(get(OKTA + "/users/%s/roles" % uid))}

def member_ids(gid):
    return {str(u.get("id")) for u in values(get(OKTA + "/groups/%s/users" % gid))}

def app_ids(aid):
    return {str(u.get("id")) for u in values(get(OKTA + "/apps/%s/users" % aid))}

for d in defs:
    for inst in values(get(ENTRA + "/identityGovernance/accessReviews/definitions/%s/instances" % d["id"])):
        for dec in values(get(ENTRA + "/identityGovernance/accessReviews/definitions/%s/instances/%s/decisions" % (d["id"], inst["id"]))):
            if str(dec.get("decision")) != "Deny":
                continue
            principal = str((dec.get("principal") or {}).get("id"))
            resource = dec.get("resource") or {}
            rtype = str(resource.get("type", "")).lower()
            rname = str(resource.get("displayName", ""))
            rid = str(resource.get("id", ""))
            if rtype in ("directoryrole", "role"):
                check("denied role gone for %s (%s)" % (principal, rid), rid not in role_types(principal))
            elif rtype == "group":
                g = group_by_name.get(rname.lower())
                if g:
                    check("denied group membership gone %s in %s" % (principal, g["id"]), principal not in member_ids(g["id"]))
            elif rtype in ("serviceprincipal", "application", "app"):
                a = app_by_label.get(rname.lower())
                if a:
                    check("denied app assignment gone %s in %s" % (principal, a["id"]), principal not in app_ids(a["id"]))
            elif rtype == "accesspackage":
                p = next((x for x in values(get(ENTRA + "/identityGovernance/entitlementManagement/assignmentPolicies"))
                          if str((x.get("accessPackage") or {}).get("id")) == rid), None)
                if p:
                    check("over-grant policy for %s tightened" % rid, str(p.get("allowedTargetScope")) not in BROAD_SCOPES)

for d in defs:
    for inst in values(get(ENTRA + "/identityGovernance/accessReviews/definitions/%s/instances" % d["id"])):
        decs = values(get(ENTRA + "/identityGovernance/accessReviews/definitions/%s/instances/%s/decisions" % (d["id"], inst["id"])))
        if any(str(x.get("decision")) == "Deny" and str(x.get("resource", {}).get("type", "")).lower() in ("directoryrole", "role") for x in decs):
            check("review instance %s applied (Completed)" % inst["id"], str(inst.get("status")) == "Completed")

inc2 = (get(SN + "/incident/%s" % inc_sys) or {}).get("result", {})
check("incident closed", str(inc2.get("state")) == CLOSED)

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
