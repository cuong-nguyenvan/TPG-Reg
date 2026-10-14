"""Benchmark policy sets: HACS (hospital access control, 25 rules / 5
policies), FMS (file management, 30 rules / 3 policies), SIS (student
information, 20 rules / 4 policies), and a two-rule financial example.
Each set comes with its finite attribute domains (*_DOM)."""
from .policy_model import PolicySet, Policy, Rule, Pred, p, AND, OR, NOT, VAR

T = lambda a, op, v: Pred(a, op, v)

# ------------------------------------------------------------------- HACS
HACS_DOM = {
    "role": ["doctor", "nurse", "receptionist", "patient", "admin", "auditor"],
    "action": ["read", "write", "delete", "print"],
    "resource": ["ehr", "prescription", "lab", "billing", "schedule"],
    "dept": ["cardio", "onco", "er", "peds"],
    "same_dept": ["yes", "no"],
    "hour": list(range(24)),
    "emergency": [0, 1],
    "consent": [0, 1],
}


def hacs():
    work = AND(p("hour", "ge", 7), p("hour", "lt", 19))
    off = OR(p("hour", "lt", 6), p("hour", "ge", 22))
    P1 = Policy("H.P1", "FA", [T("resource", "eq", "ehr")], [
        Rule("H.R1", "Deny", [T("role", "eq", "patient")], OR(p("action", "eq", "write"), p("action", "eq", "delete"))),
        Rule("H.R2", "Permit", [T("role", "eq", "doctor"), T("same_dept", "eq", "yes")], p("action", "in", ("read", "write"))),
        Rule("H.R3", "Permit", [T("role", "eq", "doctor"), T("action", "eq", "read")], p("emergency", "eq", 1)),
        Rule("H.R4", "Permit", [T("role", "eq", "nurse"), T("action", "eq", "read")], AND(p("same_dept", "eq", "yes"), VAR("work"))),
        Rule("H.R5", "Permit", [T("role", "eq", "patient"), T("action", "eq", "read")], p("consent", "eq", 1)),
        Rule("H.R6", "Deny", [T("action", "eq", "delete")], None),
    ], {"work": work})
    P2 = Policy("H.P2", "DO", [T("resource", "eq", "prescription")], [
        Rule("H.R7", "Permit", [T("role", "eq", "doctor")], p("action", "in", ("read", "write"))),
        Rule("H.R8", "Permit", [T("role", "eq", "nurse"), T("action", "eq", "read")], None),
        Rule("H.R9", "Deny", [T("role", "eq", "nurse"), T("action", "eq", "write")], None),
        Rule("H.R10", "Deny", [T("action", "eq", "write")], AND(VAR("off"), p("emergency", "eq", 0))),
        Rule("H.R11", "Permit", [T("role", "eq", "patient"), T("action", "eq", "read")], p("consent", "eq", 1)),
    ], {"off": off})
    P3 = Policy("H.P3", "PO", [T("resource", "eq", "lab")], [
        Rule("H.R12", "Permit", [T("role", "in", ("doctor", "nurse")), T("action", "eq", "read")], None),
        Rule("H.R13", "Deny", [T("role", "eq", "nurse"), T("dept", "eq", "onco")], AND(p("action", "eq", "read"), p("same_dept", "eq", "no"))),
        Rule("H.R14", "Permit", [T("role", "eq", "doctor"), T("action", "eq", "write")], p("same_dept", "eq", "yes")),
        Rule("H.R15", "Deny", [], p("action", "in", ("write", "delete"))),
        Rule("H.R16", "Deny", [T("role", "eq", "receptionist")], None),
    ])
    P4 = Policy("H.P4", "DO", [T("resource", "eq", "billing")], [
        Rule("H.R17", "Permit", [T("role", "in", ("receptionist", "admin"))], p("action", "in", ("read", "write", "print"))),
        Rule("H.R18", "Deny", [T("role", "eq", "receptionist"), T("action", "eq", "write")], NOT(VAR("work"))),
        Rule("H.R19", "Permit", [T("role", "eq", "patient")], p("action", "in", ("read", "print"))),
        Rule("H.R20", "Deny", [T("action", "eq", "delete")], None),
        Rule("H.R21", "Permit", [T("role", "eq", "auditor"), T("action", "eq", "read")], None),
    ], {"work": work})
    P5 = Policy("H.P5", "FA", [T("resource", "eq", "schedule")], [
        Rule("H.R22", "Permit", [T("role", "in", ("receptionist", "admin"))], None),
        Rule("H.R23", "Permit", [T("role", "in", ("doctor", "nurse"))], p("action", "in", ("read", "print"))),
        Rule("H.R24", "Permit", [T("role", "eq", "patient"), T("action", "eq", "read")], None),
        Rule("H.R25", "Deny", [], None),
    ])
    return PolicySet("HACS", "DO", [], [P1, P2, P3, P4, P5])


# ------------------------------------------------------------------- FMS
FMS_DOM = {
    "role": ["owner", "editor", "viewer", "guest", "admin", "auditor"],
    "action": ["read", "write", "delete", "share", "download"],
    "cls": ["public", "internal", "confidential", "secret"],
    "loc": ["office", "vpn", "remote"],
    "size": list(range(10)),        # x 10 MB
    "hour": list(range(24)),
    "mfa": [0, 1],
}


def fms():
    biz = AND(p("hour", "ge", 8), p("hour", "lt", 18))
    P1 = Policy("F.P1", "DO", [], [
        Rule("F.R1", "Permit", [T("role", "eq", "owner")], None),
        Rule("F.R2", "Permit", [T("role", "eq", "editor")], p("action", "in", ("read", "write"))),
        Rule("F.R3", "Permit", [T("role", "eq", "viewer"), T("action", "eq", "read")], None),
        Rule("F.R4", "Permit", [T("role", "eq", "guest"), T("action", "eq", "read")], p("cls", "eq", "public")),
        Rule("F.R5", "Permit", [T("role", "eq", "admin")], p("action", "ne", "share")),
        Rule("F.R6", "Permit", [T("role", "eq", "auditor"), T("action", "eq", "read")], None),
        Rule("F.R7", "Deny", [T("action", "eq", "delete")], NOT(p("role", "in", ("owner", "admin")))),
        Rule("F.R8", "Deny", [T("loc", "eq", "remote")], AND(p("mfa", "eq", 0), p("cls", "ne", "public"))),
        Rule("F.R9", "Deny", [T("role", "eq", "guest")], p("action", "ne", "read")),
        Rule("F.R10", "Deny", [T("action", "eq", "write")], AND(NOT(VAR("biz")), p("role", "ne", "owner"))),
        Rule("F.R11", "Deny", [T("action", "eq", "download")], p("size", "ge", 8)),
        Rule("F.R12", "Permit", [T("role", "eq", "editor"), T("action", "eq", "delete")], p("cls", "in", ("public", "internal"))),
    ], {"biz": biz})
    P2 = Policy("F.P2", "FA", [T("cls", "in", ("confidential", "secret"))], [
        Rule("F.R13", "Deny", [T("role", "eq", "guest")], None),
        Rule("F.R14", "Deny", [T("cls", "eq", "secret")], p("mfa", "eq", 0)),
        Rule("F.R15", "Deny", [T("loc", "eq", "remote")], None),
        Rule("F.R16", "Permit", [T("role", "eq", "owner")], None),
        Rule("F.R17", "Deny", [T("cls", "eq", "secret"), T("role", "eq", "editor")], p("action", "eq", "delete")),
        Rule("F.R18", "Permit", [T("role", "eq", "editor")], AND(p("action", "in", ("read", "write")), VAR("biz"))),
        Rule("F.R19", "Permit", [T("role", "eq", "auditor"), T("action", "eq", "read")], p("loc", "eq", "office")),
        Rule("F.R20", "Permit", [T("role", "eq", "viewer"), T("action", "eq", "read")], p("cls", "eq", "confidential")),
        Rule("F.R21", "Permit", [T("role", "eq", "admin")], p("mfa", "eq", 1)),
        Rule("F.R22", "Deny", [], None),
    ], {"biz": biz})
    P3 = Policy("F.P3", "PO", [T("action", "in", ("share", "download"))], [
        Rule("F.R23", "Permit", [T("role", "eq", "owner")], None),
        Rule("F.R24", "Permit", [T("role", "in", ("editor", "viewer")), T("action", "eq", "download")], p("size", "le", 5)),
        Rule("F.R25", "Deny", [T("cls", "eq", "secret")], None),
        Rule("F.R26", "Deny", [T("action", "eq", "share")], p("cls", "in", ("confidential", "secret"))),
        Rule("F.R27", "Permit", [T("role", "eq", "editor"), T("action", "eq", "share")], p("cls", "eq", "internal")),
        Rule("F.R28", "Deny", [T("loc", "eq", "remote"), T("action", "eq", "download")], p("size", "gt", 3)),
        Rule("F.R29", "Permit", [T("role", "eq", "admin"), T("action", "eq", "download")], p("mfa", "eq", 1)),
        Rule("F.R30", "Deny", [T("role", "eq", "guest")], None),
    ])
    return PolicySet("FMS", "DO", [], [P1, P2, P3])


# ------------------------------------------------------------------- SIS
SIS_DOM = {
    "role": ["student", "lecturer", "advisor", "registrar", "admin"],
    "action": ["view", "edit", "approve", "export"],
    "resource": ["grades", "transcript", "profile", "course"],
    "own": [0, 1],
    "open": [0, 1],          # semester open for changes
    "week": list(range(1, 17)),
    "year": [1, 2, 3, 4],
}


def sis():
    P1 = Policy("S.P1", "FA", [], [
        Rule("S.R1", "Deny", [T("action", "eq", "edit")], AND(p("open", "eq", 0), p("role", "ne", "registrar"))),
        Rule("S.R2", "Permit", [T("role", "eq", "admin")], p("action", "ne", "approve")),
        Rule("S.R3", "Deny", [T("role", "eq", "student"), T("action", "eq", "export")], None),
    ])
    P2 = Policy("S.P2", "DO", [T("resource", "eq", "grades")], [
        Rule("S.R4", "Permit", [T("role", "eq", "student"), T("action", "eq", "view")], p("own", "eq", 1)),
        Rule("S.R5", "Permit", [T("role", "eq", "lecturer")], p("action", "in", ("view", "edit"))),
        Rule("S.R6", "Deny", [T("role", "eq", "lecturer"), T("action", "eq", "edit")], VAR("late")),
        Rule("S.R7", "Permit", [T("role", "eq", "registrar")], p("action", "in", ("view", "approve", "export"))),
        Rule("S.R8", "Deny", [T("role", "eq", "student")], p("own", "eq", 0)),
        Rule("S.R9", "Permit", [T("role", "eq", "advisor"), T("action", "eq", "view")], None),
    ], {"late": p("week", "gt", 14)})
    P3 = Policy("S.P3", "PO", [T("resource", "in", ("transcript", "profile"))], [
        Rule("S.R10", "Permit", [T("own", "eq", 1)], p("action", "in", ("view", "export"))),
        Rule("S.R11", "Permit", [T("role", "eq", "registrar")], None),
        Rule("S.R12", "Deny", [T("action", "eq", "edit"), T("resource", "eq", "transcript")], None),
        Rule("S.R13", "Permit", [T("role", "eq", "advisor"), T("action", "eq", "view")], p("year", "ge", 2)),
        Rule("S.R14", "Deny", [T("role", "eq", "student")], p("own", "eq", 0)),
        Rule("S.R15", "Permit", [T("resource", "eq", "profile"), T("own", "eq", 1)], p("action", "eq", "edit")),
    ])
    P4 = Policy("S.P4", "FA", [T("resource", "eq", "course")], [
        Rule("S.R16", "Deny", [T("action", "eq", "edit")], AND(p("open", "eq", 1), p("week", "gt", 2), p("role", "eq", "student"))),
        Rule("S.R17", "Permit", [T("role", "eq", "student")], p("action", "in", ("view", "edit"))),
        Rule("S.R18", "Permit", [T("role", "in", ("lecturer", "advisor"))], p("action", "ne", "export")),
        Rule("S.R19", "Permit", [T("role", "eq", "registrar")], None),
        Rule("S.R20", "Deny", [], None),
    ])
    return PolicySet("SIS", "FA", [], [P1, P2, P3, P4])


# ------------------------------------------------------- financial example (two rules)
FIN_DOM = {
    "role": ["FinancialOfficer", "Clerk"],
    "action": ["Transfer", "View"],
    "amount": list(range(0, 21)),   # in thousands
}


def fin(alg="DO", r2_threshold=5):
    pol = Policy("M.P1", alg, [], [
        Rule("M.R1", "Permit", [T("role", "eq", "FinancialOfficer"), T("action", "eq", "Transfer")], p("amount", "lt", 10)),
        Rule("M.R2", "Deny", [T("role", "eq", "FinancialOfficer"), T("action", "eq", "Transfer")], p("amount", "gt", r2_threshold)),
    ])
    return PolicySet("FIN", "DO", [], [pol])


DATASETS = {"HACS": (hacs, HACS_DOM), "FMS": (fms, FMS_DOM), "SIS": (sis, SIS_DOM)}
