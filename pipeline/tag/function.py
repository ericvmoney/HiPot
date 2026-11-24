"""Function: the kind of work a role is, one id from taxonomy.yml `functions`.

Decided in this order, and the first answer wins:

  1. The title. `TITLE_RULES` is read top to bottom. Corporate and support
     work comes first, then project and product roles, then the role nouns
     (trades, technician, scientist, engineer), then quality, field
     operations and production words.
  2. A title that names only a technical field ("Director, Power Conversion",
     "Manager, Seats and Restraints") is engineering.
  3. The department, through `DEPARTMENT_RULES`.
  4. The posting text, through a few phrases about required degrees.
  5. Otherwise engineering, marked low confidence.

Every role gets a function; none is dropped. Which functions reach the
board is `listed:` in taxonomy.yml, applied at the publish step.

Inputs are normalised (lower case, dashes as " - ") by `rules.normalise`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class FunctionDecision:
    function: str
    evidence: str                    # title | department | text | default
    confidence: str                  # high | medium | low
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Rule:
    function: str
    pattern: re.Pattern
    unless: re.Pattern | None
    corporate: bool                  # an engineer whose title names a field first is not moved here
    role_noun: bool                  # read from the head of the title first (see decide_function)
    note: str | None
    confidence: str


def _f(function: str, pattern: str, unless: str | None = None, corporate: bool = False,
       note: str | None = None, confidence: str = "high", role_noun: bool = False) -> _Rule:
    return _Rule(function, re.compile(pattern), re.compile(unless) if unless else None, corporate, role_noun, note,
                 confidence)


# Words that mark someone who does the technical work themselves.
HANDS_ON = re.compile(r"\b(engineers?|engineering|technicians?|scientists?|electricians?|physicists?)\b")

TITLE_RULES = [
    # Not a role but a pool of applicants. Kept, and not listed.
    _f("people-admin",
       r"general (application|interest|consideration|submission)|future (opportunit\w+|openings?|roles?)"
       r"|open application|talent (community|network|pool)|don'?t see|join (our|the) team|expression of interest"
       r"|speculative|drop your resume",
       note="general-application"),

    # Sales and applications engineers are engineers (taxonomy: sales-bd covers).
    _f("engineering", r"sales engineer\w*|solutions (engineer\w*|architect)|applications? engineer\w*"
                      r"|forward deployed engineer"),

    # Environment, health and safety.
    _f("ehs",
       r"\behs\b|\bhse\b|\behs&s\b|\besh\b|environment(al)?,? health|health (and|&) safety|occupational"
       r"|industrial hygien\w+|safety (manager|specialist|coordinator|officer|director|professional|lead)"
       r"|environmental (engineer|scientist|specialist|manager|compliance|planner|analyst|coordinator)"
       r"|sustainability|\besg\b|stewardship|wastewater"),

    # People and administration.
    _f("people-admin", r"recruit\w+|talent (acquisition|attraction|partner|sourc\w+|scout)|\bsourcer\b", corporate=True),
    _f("people-admin",
       r"human resources|\bhr\b|\bhrbp\b|\bhris\b|\bpeople (ops|operations|partner|team|business|experience|analytics"
       r"|manager|programs?|lead|coordinator|generalist|systems|&|and)\b"
       r"|(head|chief|vp|vice president|director),? (of )?people\b|chief people|learning (and|&) development|\bl&d\b"
       r"|compensation|\bbenefits\b|payroll|total rewards|employee (relations|experience|engagement|operations|care)"
       r"|workplace (experience|manager|coordinator|operations)|immigration|global mobility|diversity|\bdei\b"
       r"|talent (management|development)|labor advisor",
       corporate=True),
    _f("people-admin",
       r"executive assistant|administrative|\badmin\b|receptionist|office (manager|coordinator|administrator|assistant)"
       r"|front desk|chief of staff|personal assistant|travel (coordinator|manager)",
       corporate=True),
    _f("people-admin", r"\btrainer\b|\btraining\b|instructional design\w*|curriculum",
       unless=r"technician|engineer|member experience", corporate=True, confidence="medium"),
    _f("it", r"executive protection|security (guard|officer|agent|specialist)|head of security", corporate=True),

    # Finance, legal and strategy. Legal before policy, so a regulatory counsel is legal.
    _f("finance-legal",
       r"financ\w+|accountant|accounting|accounts (payable|receivable)|\bfp&a\b|treasury|\btax\b|bookkeep\w+"
       r"|billing|revenue|investor relations|\bcfo\b|(internal|financial|it) audit\w*|credit (analyst|manager)"
       r"|collections|capital markets|underwrit\w+|insurance|actuar\w+|equity (admin\w*|analyst|manager)"
       r"|controlling\b|cost (analyst|accountant)",
       corporate=True),
    _f("finance-legal", r"\bcontroller\b",
       unless=r"engineer|firmware|hardware|design|motor|charge|power plant|laser|optic|technician", corporate=True),
    _f("finance-legal",
       r"\blegal\b|counsel|attorney|paralegal|lawyer|contracts? (manager|administrator|specialist|analyst)"
       r"|commercial contracts|patent (agent|attorney|counsel)|compliance (counsel|officer)"
       r"|(trade|export|legal|tax|financial|sox|privacy|ethics|corporate|hr) compliance|\bprivacy\b",
       corporate=True),
    _f("finance-legal",
       r"project develop\w+|(real estate|land|site) (development|acquisition)|land (agent|manager|portfolio)"
       r"|\blandman\b|real estate|permitting|permit (coordinator|manager|specialist)|\bsiting\b"
       r"|(powered )?land development",
       corporate=True),

    # Quality-side regulatory work, before the policy rule takes "regulatory affairs".
    _f("quality-compliance", r"licensing|regulatory affairs", corporate=True, confidence="medium"),

    # Marketing and communications, including policy advocacy.
    _f("marketing",
       r"marketing|public relations|\bpr\b|\bbrand\w*|copywrit\w+|social media|graphic design\w*|creative"
       r"|events? (manager|coordinator|lead|specialist)|videograph\w+|photograph\w+|\bseo\b|demand gen\w*"
       r"|\bcontent\b|storytell\w+|\beditor\w*|\bproducer\b|growth (product|marketing|lead|manager|analyst|analytics"
       r"|operations|intern)|lifecycle growth|^growth\b|web design\w*|(visual|interaction|brand|motion) design\w*"
       r"|animator|motion graphics",
       corporate=True),
    _f("marketing", r"\bcommunications?\b",
       unless=r"engineer|systems|hardware|protocol|technician|firmware|network", corporate=True),
    _f("marketing",
       r"\bpolicy\b|government (affairs|relations)|public (affairs|policy)|legislative|lobby\w+"
       r"|external affairs|community (relations|engagement|affairs|manager)|market (design|policy)",
       corporate=True),

    # Sales, business development and customer success.
    _f("sales-bd",
       r"\bsales\b|account (executive|manager|director|rep\w*)|business development|\bbdr\b|\bsdr\b"
       r"|channel (manager|partner)|partner(ship)?s? (manager|lead|director|development)|partnerships"
       r"|commercial (manager|director|lead|strategy|development|analyst|associate)"
       r"|originat\w+|deal (desk|structur\w+)|\bpricing\b|\bproposals?\b|bid (manager|coordinator)|\brfp\b"
       r"|go[- ]to[- ]market|\bgtm\b|dealer|\bretail\b|merchandis\w+|estimat(or|ion|ing)"
       r"|customer (success|experience|service|care|operations|relations|advocate|support\b(?! engineer))"
       r"|client (success|services|partner)|call cent(er|re)|member experience|inside delivery",
       unless=r"sales engineer|solutions engineer|(project|program) manager", corporate=True),

    # Supply chain, including warehouse work and delivery driving.
    _f("supply-chain",
       r"supply chain|procurement|purchas\w+|\bbuyer\b|sourcing|commodity|supply (manager|management|planning|planner)"
       r"|global supply|materials? (manager|planner|planning|management|coordinator|handler|analyst|associate"
       r"|clerk|supervisor)|\bplanner\b|planning (manager|analyst)|(production|master|materials?) scheduler"
       r"|logistics|warehous\w+|inventory|shipping|receiving|fulfillment|distribution (cent(er|re)|manager)"
       r"|ordering|customs|category manager|vendor manag\w+|supplier (manager|management|relationship|operations)"
       r"|stockroom|expedit\w+|demand plann\w+|\bs&op\b|order (management|fulfillment)|freight|\bspares\b"
       r"|forklift|\bdrivers?\b|\bcdl\b|cost engineer\w*",
       unless=r"supplier (quality|industriali[sz]ation|development) engineer|supplier quality|tooling engineer"
              r"|gate driver|motor driver|driver (engineer|design|development|board)",
       corporate=True),

    # Corporate IT and enterprise systems.
    _f("it",
       r"\bit\b|information (technology|systems|security)|help ?desk|incident response|digital transformation"
       r"|desktop support|sys(tems?)? ?admin\w*|network (administrator|operations|security|engineer|architect)"
       r"|cyber ?security|security (engineer|analyst|architect|operations|manager)|\berp\b|netsuite"
       r"|salesforce|\bsap\b|business (systems|applications|intelligence)|enterprise (applications|systems|architect)"
       r"|systems analyst|\bplm\b|teamcenter|microsoft 365|\bazure\b|telecommunications engineer",
       corporate=True),

    # Strategy and corporate development, after the specific corporate rules.
    _f("finance-legal",
       r"\bstrategy\b|strategist|strategic (partnerships|finance|initiatives|planning)|corporate development"
       r"|business (operations|analyst|manager|planning|continuity|transformation)|\bbizops\b"
       r"|chief (executive|operating|commercial|revenue|marketing|financial|people|legal|administrative|business"
       r"|strategy) officer|\bceo\b|\bcoo\b|\bcmo\b|\bcro\b|founder|general manager|venture|investment|investor"
       r"|economist|(business|financial|market|commercial|strategy|investment|operations|sales) analyst"
       r"|market (research|intelligence|development|analyst)|asset manag\w+|energy (markets?|trad\w+)|\btrader\b"
       r"|power marketing|\bofftake\b|power procurement|energy and utilities",
       corporate=True, confidence="medium"),

    # Product and design.
    _f("product",
       r"product (manager|management|owner|line manager|lead)|(head|director|vp|vice president),? (of )?product\b"
       r"|\bux\b|user (experience|interface|research\w*)|product design(er)?\b(?! engineer)|industrial design\w*"
       r"|color,? material|\bcmf\b|^product,"),
    _f("product", r"technical writer|technical (illustrator|publications?)|documentation (specialist|manager|lead)",
       note="technical-writer", confidence="medium"),

    # Projects and programs.
    _f("project-program",
       r"(program|project|construction|deployment) (manager|management|lead|director|coordinator|controls?|scheduler"
       r"|delivery|steering)|project engineer\w*|projects? (controls?|manager)|specialist, construction|\btpm\b|\bpmo\b|technical program"
       r"|technical project|\bscheduler\b|planning (and|&) controls|\bpp&c\b|superintendent|programs? director"
       r"|director,? (of )?programs?\b|program lead|projektmanager|(project|production|program) steering"
       r"|cross cutting integration|\bprograms? (and|&) systems engineering"),

    # The role nouns: who does the work.
    _f("science", r"research scientist|scientist/engineer", role_noun=True),
    _f("trades",
       r"electrician|wireman|journeyman|lineman|line ?worker|\binstallers?\b|welder|machinist|pipefitter|plumber"
       r"|carpenter|millwright|ironworker|\bmechanic\b|hvac technician|\ba&p\b|fabricator|rigger\b", role_noun=True),
    _f("technician", r"technicians?\b|techician|\btech\b|technologist", role_noun=True),
    _f("science",
       r"scientist|researcher|physicist|chemist\b|postdoc\w*|post-?doctoral|research (associate|fellow|assistant)"
       r"|\bmodeler\b|seismologist|geologist|geophysicist|geochemist|\bphysics\b|materials science|experimental",
       unless=r"data scientist|applied scientist|machine learning|engineer", role_noun=True),
    _f("engineering",
       r"engineer\w*|\barchitect\b|developer|programmer|drafter|\bdesigner\b|\bdre\b|\bcad\b"
       r"|technical (lead|specialist)|tech lead|\bcto\b|chief technology|chief engineer|\bmsl\b|main system",
       role_noun=True),

    # Quality, certification and compliance (quality engineers were taken above).
    _f("quality-compliance",
       r"quality|inspector|inspection|auditor|certification|compliance|homologation|regulatory|document controls?"
       r"|conformity|\bqc\b|\bmrb\b|meisterbock|cubing"),

    # Operations of deployed assets.
    _f("field-operations",
       r"field (service|operations|installation|performance|quality)|\bfield\b|\bo&m\b|operations (and|&) maintenance"
       r"|site operations|fleet operations|deployment|service (manager|operations|delivery)|commissioning"
       r"|asset operations|operations support|upgrades|returns (and|&) repair|incident|network operat\w+"),

    # Production and plant operations.
    _f("production",
       r"production|manufacturing|\boperators?\b|assembler|\bassembly\b|\bshift\b|plant (manager|operations|operator"
       r"|lead)|facilit(y|ies)|maintenance|machine shop|fabrication|press shop|paint shop|\bline (lead|supervisor)"
       r"|team member|laborer|\bhelper\b|\bcleaner\b|janitor\w*|custodi\w+|groundskeep\w+|pre[- ]series"
       r"|prototype|\bbuild\b|container management|launch (management|cost)"),
]

# The department, read when the title decides nothing. The most specific
# part is tried first ("Growth / Member Experience").
_D = re.compile

DEPARTMENT_RULES = [
    ("people-admin", _D(r"general applications|talent community|no department")),
    ("ehs", _D(r"\behs\b|eh&s|environmental health|health (and|&) safety")),
    ("people-admin", _D(r"talent|recruit|human resources|\bhr\b|\bpeople\b|workplace and real estate")),
    ("finance-legal", _D(r"\blegal\b|financ|accounting|capital markets|corporate development|investor|\bland\b"
                         r"|permitting|real estate|\bg ?& ?a\b|business (and |& )?operations|corporate functions"
                         r"|executive")),
    ("sales-bd", _D(r"member experience$|\bsales\b|business development|commercial markets|^commercial$")),
    ("marketing", _D(r"marketing|\bbrand\b|communications|\bgrowth\b")),
    ("it", _D(r"information technology|\bit\b|business systems|enterprise (systems|technology)|digital transformation"
              r"|\bsecurity\b")),
    ("supply-chain", _D(r"supply chain|procurement|purchasing|logistics|warehouse")),
    ("quality-compliance", _D(r"quality|certification")),
    ("trades", _D(r"installers")),
    ("field-operations", _D(r"\bo&m\b|operations (and|&) maintenance|deployments?|\bfield\b|service|site operations"
                            r"|upgrades|overwatch|network operations|monitoring")),
    ("product", _D(r"^design$|^design advanced|industrial design")),
    ("project-program", _D(r"\bepc\b|project delivery|\bdelivery\b|program management|construction")),
    ("production", _D(r"manufacturing|production|plant operations|fabrication|facilities")),
    ("science", _D(r"\bscience\b")),
    ("engineering", _D(r"engineer|\br ?& ?d\b|research|hardware|product development|technology|technical|prototype"
                       r"|vehicle|air vehicle|airframe|propeller|thrust|software|firmware|test|heat to power"
                       r"|powerblock|pulser|target|science|design")),
    ("product", _D(r"\bproducts?\b")),
]

# Corporate departments that overrule a title naming only software, data or a
# broad field ("Senior Application Engineer, PLM" in Business Systems).
_IT_DEPARTMENT = re.compile(r"information technology|\bit\b|business systems|enterprise (systems|technology)"
                            r"|digital transformation")
_SOFT_ONLY = frozenset({"software", "data", "systems", "field"})

_TEXT_RULES = [
    ("engineering", re.compile(r"(bachelor'?s|b\.?s\.?|master'?s|degree)[^.]{0,40}\bin [a-z ,/&]{0,60}engineering")),
    ("science", re.compile(r"ph\.?d\.?[^.]{0,30}\bin [a-z ,/&]{0,40}(physics|chemistry|materials|geoscience)")),
]

_HEAD_END = re.compile(r",| - |\(|\)|:|\||;| @ | / ")
_SUPERVISOR = re.compile(r"\bsupervisor\b|\bforem[ae]n\b|crew lead")


def _department_function(department: str) -> str | None:
    # The most specific part of the department first ("Operations / People / HR").
    for part in (department.split(" / ")[-1], department):
        for function, pattern in DEPARTMENT_RULES:
            if pattern.search(part):
                return function
    return None


def _it_department(function: str, department: str, disciplines: list[str]) -> bool:
    """Software, data or broad engineering in a corporate IT department is IT."""
    return function == "engineering" and bool(_IT_DEPARTMENT.search(department)) and set(disciplines) <= _SOFT_ONLY


def _role_noun(title: str) -> _Rule | None:
    """Who does the work, read from the head of the title first: "Senior
    Software Engineer, Frontend (Technician Hub)" is an engineer."""
    head = _HEAD_END.split(title, maxsplit=1)[0]
    for text in (head, title):
        for rule in ROLE_RULES:
            if rule.pattern.search(text) and not (rule.unless and rule.unless.search(text)):
                return rule
    return None


ROLE_RULES = [rule for rule in TITLE_RULES if rule.role_noun]


def decide_function(title: str, department: str, text: str, disciplines: list[str], weak_only: bool,
                    strong_starts: list[int]) -> FunctionDecision:
    """The function for one posting. `strong_starts` are the positions in the
    title where a discipline phrase begins (from the discipline rules)."""
    roles_read = False
    for rule in TITLE_RULES:
        if rule.role_noun:
            if roles_read:
                continue
            roles_read = True
            found = _role_noun(title)
            if found is None:
                continue
            rule = found
        else:
            match = rule.pattern.search(title)
            if not match or (rule.unless and rule.unless.search(title)):
                continue
            # "Controls Engineer - Warehouse Automation" is still an engineer.
            if rule.corporate and HANDS_ON.search(title) and any(start < match.start() for start in strong_starts):
                continue
        notes = [rule.note] if rule.note else []
        if _it_department(rule.function, department, disciplines):
            return FunctionDecision("it", "department", "medium", notes + ["it-department"])
        return FunctionDecision(rule.function, "title", rule.confidence, notes)

    # A supervisor's function is the team's ("Electrical Supervisor" in Electrical Installers).
    if _SUPERVISOR.search(title):
        team = _department_function(department) if department else None
        function = team if team and team != "engineering" else "production"
        return FunctionDecision(function, "department" if team else "title", "medium", ["supervisor"])

    if disciplines and not weak_only:
        if _it_department("engineering", department, disciplines):
            return FunctionDecision("it", "department", "medium", ["it-department"])
        return FunctionDecision("engineering", "title", "medium", ["function-from-discipline"])

    if department and (function := _department_function(department)):
        return FunctionDecision(function, "department", "medium", [])

    for function, pattern in _TEXT_RULES:
        if text and pattern.search(text):
            return FunctionDecision(function, "text", "low", [])

    return FunctionDecision("engineering", "default", "low", ["function-default"])
