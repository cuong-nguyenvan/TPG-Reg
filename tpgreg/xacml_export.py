"""Export prototype policies and requests to standard XACML 2.0 XML so that an
independent PDP (ndg-xacml) can evaluate them.

Mapping: rule/policy targets -> <Target> with <Subjects>/<Resources>/<Actions>/
<Environments> and *Match elements (an 'in' predicate becomes alternative
<Subject>/<Resource>/... elements); 'ne' target predicates of rules are moved
into the rule condition (equivalent for rules); conditions -> <Condition> with
nested <Apply>; VariableReference is inlined (ndg-xacml does not implement it).
"""
from itertools import product
from xml.sax.saxutils import escape
from .policy_model import PolicySet, Pred

NS = "urn:oasis:names:tc:xacml:2.0:policy:schema:cd:04"
F = "urn:oasis:names:tc:xacml:1.0:function:"
ALG_R = {"DO": "urn:oasis:names:tc:xacml:1.0:rule-combining-algorithm:deny-overrides",
         "PO": "urn:oasis:names:tc:xacml:1.0:rule-combining-algorithm:permit-overrides",
         "FA": "urn:oasis:names:tc:xacml:1.0:rule-combining-algorithm:first-applicable"}
ALG_P = {k: v.replace("rule-combining", "policy-combining") for k, v in ALG_R.items()}
STR = "http://www.w3.org/2001/XMLSchema#string"
INT = "http://www.w3.org/2001/XMLSchema#integer"
CATS = {"Subject": "Subjects", "Resource": "Resources", "Action": "Actions", "Environment": "Environments"}
ENV_ATTRS = {"hour", "emergency", "week", "open", "loc", "mfa", "time"}
SUBJ_ATTRS = {"role", "own", "same_dept", "year"}


def category(attr):
    if attr in SUBJ_ATTRS:
        return "Subject"
    if attr == "action":
        return "Action"
    # ndg-xacml has no reader for Environment designators; the category is
    # irrelevant to the semantics, so environment attributes go to Resource.
    return "Resource"


def attr_id(a):
    return f"urn:tpgreg:attr:{a}"


class Exporter:
    def __init__(self, domains):
        self.dom = domains
        # ndg-xacml cannot parse integer AttributeValues from XML; since all
        # comparisons are encoded as equalities over the finite domain, every
        # attribute is exported with the string data type.
        self.isint = {a: False for a in domains}

    def dtype(self, a):
        return INT if self.isint[a] else STR

    def desig(self, a):
        c = category(a)
        return f'<{c}AttributeDesignator AttributeId="{attr_id(a)}" DataType="{self.dtype(a)}"/>'

    def val(self, a, v):
        return f'<AttributeValue DataType="{self.dtype(a)}">{escape(str(v))}</AttributeValue>'

    # ---------------------------------------------------------- conditions
    def num_set(self, a, op, v):
        """Values of the finite domain satisfying `a op v` (comparison
        functions are not implemented in ndg-xacml, so they are encoded as
        disjunctions of equalities)."""
        f = {"lt": lambda x: x < v, "le": lambda x: x <= v,
             "gt": lambda x: x > v, "ge": lambda x: x >= v}[op]
        return tuple(x for x in self.dom[a] if f(x))

    def OR(self, parts):
        """or(x1..xn) = not(and(not x1 .. not xn)); ndg-xacml has no 'or'."""
        if len(parts) == 1:
            return parts[0]
        inner = "".join(f'<Apply FunctionId="{F}not">{x}</Apply>' for x in parts)
        return f'<Apply FunctionId="{F}not"><Apply FunctionId="{F}and">{inner}</Apply></Apply>'

    def atom(self, a, op, v):
        t = "integer" if self.isint[a] else "string"
        if op in ("lt", "le", "gt", "ge"):
            vs = self.num_set(a, op, v)
            if not vs:
                return f'<Apply FunctionId="{F}not">{self.atom(a, "in", self.dom[a])}</Apply>'
            return self.atom(a, "in", vs)
        x = f'<Apply FunctionId="{F}{t}-one-and-only">{self.desig(a)}</Apply>'
        if op == "in":
            return self.OR([self.atom(a, "eq", w) for w in v])
        if op == "eq":
            return f'<Apply FunctionId="{F}{t}-equal">{x}{self.val(a, v)}</Apply>'
        if op == "ne":
            return f'<Apply FunctionId="{F}not">{self.atom(a, "eq", v)}</Apply>'
        fn = {"lt": "integer-less-than", "le": "integer-less-than-or-equal",
              "gt": "integer-greater-than", "ge": "integer-greater-than-or-equal"}[op]
        return f'<Apply FunctionId="{F}{fn}">{x}{self.val(a, v)}</Apply>'

    def expr(self, e, vars_):
        k = e[0]
        if k == "p":
            pr = e[1]
            return self.atom(pr.attr, pr.op, pr.val)
        if k == "and":
            return f'<Apply FunctionId="{F}and">' + "".join(self.expr(x, vars_) for x in e[1]) + "</Apply>"
        if k == "or":
            return self.OR([self.expr(x, vars_) for x in e[1]])
        if k == "not":
            return f'<Apply FunctionId="{F}not">{self.expr(e[1], vars_)}</Apply>'
        if k == "var":
            return self.expr(vars_[e[1]], vars_)
        raise ValueError(e)

    # ---------------------------------------------------------- targets
    def match(self, pr, v=None):
        a, op = pr.attr, pr.op
        v = pr.val if v is None else v
        if self.isint[a]:
            fn = {"eq": "integer-equal", "in": "integer-equal", "ge": "integer-less-than-or-equal",
                  "gt": "integer-less-than", "le": "integer-greater-than-or-equal",
                  "lt": "integer-greater-than"}[op]
        else:
            fn = "string-equal"
        c = category(a)
        return f'<{c}Match MatchId="{F}{fn}">{self.val(a, v)}{self.desig(a)}</{c}Match>'

    def target(self, preds):
        bycat = {}
        preds = [Pred(pr.attr, "in", self.num_set(pr.attr, pr.op, pr.val))
                 if pr.op in ("lt", "le", "gt", "ge") else pr for pr in preds]
        for pr in preds:
            assert pr.op != "ne"
            assert pr.op != "in" or len(pr.val) > 0
            bycat.setdefault(category(pr.attr), []).append(pr)
        out = "<Target>"
        for c in ("Subject", "Resource", "Action", "Environment"):
            if c not in bycat:
                continue
            alts = [[(pr, w) for w in pr.val] if pr.op == "in" else [(pr, None)] for pr in bycat[c]]
            out += f"<{CATS[c]}>"
            for combo in product(*alts):
                out += f"<{c}>" + "".join(self.match(pr, w) for pr, w in combo) + f"</{c}>"
            out += f"</{CATS[c]}>"
        return out + "</Target>"

    # ---------------------------------------------------------- policies
    def rule(self, r, vars_):
        tpreds = [x for x in r.target if x.op != "ne"]
        cparts = [("p", x) for x in r.target if x.op == "ne"]
        if r.cond is not None:
            cparts.append(r.cond)
        s = f'<Rule RuleId="{r.id}" Effect="{r.effect}">{self.target(tpreds)}'
        if cparts:
            e = cparts[0] if len(cparts) == 1 else ("and", tuple(cparts))
            s += f"<Condition>{self.expr(e, vars_)}</Condition>"
        return s + "</Rule>"

    def policyset(self, ps: PolicySet):
        s = (f'<?xml version="1.0" encoding="UTF-8"?>\n<PolicySet xmlns="{NS}" PolicySetId="{ps.id}" '
             f'PolicyCombiningAlgId="{ALG_P[ps.alg]}">{self.target(ps.target)}')
        for pol in ps.policies:
            s += (f'<Policy PolicyId="{pol.id}" RuleCombiningAlgId="{ALG_R[pol.alg]}">'
                  f'{self.target(pol.target)}')
            for r in pol.rules:
                s += self.rule(r, pol.vars)
            s += "</Policy>"
        return s + "</PolicySet>"
