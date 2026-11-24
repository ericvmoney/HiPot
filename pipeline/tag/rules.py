"""Discipline and scope rules.

`classify(title, department, text)` decides, in this order:

  1. Is the title a function the board does not list (sales, recruiting,
     finance, legal, ...)? Then the role is left out, with the reason.
  2. Which disciplines does the title name? Phrases are tried from the most
     specific to the most general, and each match is blanked so a general
     word cannot re-read it ("power electronics" is not also "electronics").
  3. If the title names none, the department is read the same way.
  4. If that also names none and the title is an engineering title, the
     posting text is scored against a short list of phrases per discipline.

Every decision carries a confidence and notes, so the evaluation sheet and
the run report can show which roles the rules were least sure of.

Discipline ids come from taxonomy.yml. Nothing here invents an id.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_DISCIPLINES = 3

# Disciplines that, named beside a generic software title, show the software
# is tied to the product's hardware.
HARD_DISCIPLINES = frozenset({
    "electrical", "power-electronics", "battery", "power-systems", "mechanical", "thermal",
    "controls", "firmware", "test", "manufacturing", "chemical-process", "materials", "field",
})

# Placeholders resolved after matching.
PROCESS = "?process"      # "process engineer": manufacturing or chemical-process
SOFTWARE = "?software"    # generic software title: in scope only with a hardware tie


@dataclass
class Decision:
    in_scope: bool
    disciplines: list[str] = field(default_factory=list)
    reason: str | None = None        # why a role was left out
    confidence: str = "high"         # high | medium | low
    evidence: str = "title"          # title | department | text | none
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Hit:
    discipline: str
    start: int
    end: int
    weak: bool
    note: str | None


# --------------------------------------------------------------------------
# Titles the board does not list. Checked before the discipline rules.
# `unless` names title words that cancel the rule.
# --------------------------------------------------------------------------

def _out(reason: str, pattern: str, unless: str | None = None):
    return reason, re.compile(pattern), re.compile(unless) if unless else None


OUT_RULES = [
    _out("general-application",
         r"general (application|interest|consideration)|future (opportunit\w+|openings?|roles?)|open application"
         r"|talent (community|network|pool)|don'?t see|join (our|the) team|expression of interest|speculative"),
    _out("recruiting", r"recruit\w+|talent (acquisition|partner|sourc\w+|scout)|\bsourcer\b"),
    _out("people-hr",
         r"human resources|\bhr\b|\bhrbp\b|\bhris\b|\bpeople (ops|operations|partner|team|business|experience|analytics"
         r"|manager|programs?|lead|coordinator|generalist|systems|&|and)\b|(head|chief|vp|vice president|director),? (of )?people\b"
         r"|chief people|learning (and|&) development|\bl&d\b|compensation|benefits|payroll|total rewards"
         r"|employee (relations|experience|engagement)|workplace (experience|manager|coordinator|operations)"
         r"|immigration|diversity|\bdei\b|talent (management|development)"),
    _out("finance-accounting",
         r"financ\w+|accountant|accounting|accounts (payable|receivable)|\bfp&a\b|treasury|\btax\b|bookkeep\w+"
         r"|billing|revenue|investor relations|\bcfo\b|(internal|financial|it) audit\w*|credit (analyst|manager)"
         r"|collections|capital markets|underwrit\w+|insurance|actuar\w+|equity (admin\w*|analyst)"),
    _out("finance-accounting", r"\bcontroller\b",
         unless=r"engineer|firmware|hardware|design|motor|charge|power plant|\bplant controller (engineer|software)"),
    _out("legal",
         r"\blegal\b|counsel|attorney|paralegal|lawyer|contracts? (manager|administrator|specialist|analyst)"
         r"|patent (agent|attorney|counsel)|compliance (counsel|officer)"
         r"|(trade|export|legal|tax|financial|sox|privacy|ethics|corporate|hr) compliance|\bprivacy\b"),
    _out("policy",
         r"\bpolicy\b|government (affairs|relations)|public (affairs|policy)|regulatory affairs|legislative"
         r"|lobby\w+|external affairs|community (relations|engagement|affairs|manager)|market (design|policy)"),
    _out("marketing-communications",
         r"marketing|public relations|\bpr\b|brand\w*|copywrit\w+|social media|graphic design\w*|creative"
         r"|events? (manager|coordinator|lead|specialist)|videograph\w+|photograph\w+|\bseo\b|demand gen\w*"
         r"|\bcontent\b|storytell\w+|\beditor\w*|growth (product|marketing|lead|manager|analyst|analytics|operations)"
         r"|member experience"),
    _out("marketing-communications", r"\bcommunications?\b",
         unless=r"engineer|systems|hardware|protocol|technician|firmware|network"),
    _out("sales",
         r"\bsales\b|account (executive|manager|director|rep\w*)|business development|\bbdr\b|\bsdr\b"
         r"|channel (manager|partner)|partner(ship)?s? (manager|lead|director|development)|partnerships"
         r"|commercial (manager|director|lead|operations|strategy|development|analyst|associate)"
         r"|originat\w+|deal (desk|structur\w+)|\bpricing\b|\bproposals?\b|bid (manager|coordinator)|\brfp\b"
         r"|go[- ]to[- ]market|\bgtm\b|dealer|\bretail\b|merchandis\w+|estimat(or|ion|ing)",
         unless=r"sales engineer|solutions engineer"),
    _out("customer-success",
         r"customer (success|experience|service|care|operations|relations|advocate)|client (success|services|partner)"
         r"|customer support\b(?! engineer)|call cent(er|re)"),
    _out("supply-chain",
         r"supply chain|procurement|purchas\w+|\bbuyer\b|sourcing|commodity|supply (manager|management|planning|planner)"
         r"|global supply|materials? (manager|planner|planning|management|coordinator|handler|analyst)"
         r"|materials? (associate|clerk|supervisor)|\bplanner\b|planning (manager|analyst)"
         r"|(production|master|materials?) scheduler|logistics|warehous\w+"
         r"|inventory|shipping|receiving|fulfillment|distribution (cent(er|re)|manager)|customs|category manager"
         r"|vendor manag\w+|supplier (manager|management|relationship|operations)|stockroom|expedit\w+|demand plann\w+"
         r"|\bs&op\b|order (management|fulfillment)|freight",
         unless=r"supplier (quality|industriali[sz]ation|development) engineer|supplier quality|tooling engineer"),
    _out("it",
         r"\bit\b|information (technology|systems|security)|help ?desk|incident response"
         r"|desktop support|sys(tems?)? ?admin\w*|network (administrator|operations|security|engineer|architect)"
         r"|cyber ?security|security (engineer|analyst|architect|operations|manager)|\berp\b|netsuite"
         r"|salesforce|\bsap\b|business (systems|applications|intelligence)|enterprise (applications|systems|architect)"
         r"|systems analyst|\bplm\b|teamcenter"),
    _out("admin",
         r"executive assistant|administrative|\badmin\b|receptionist|office (manager|coordinator|administrator|assistant)"
         r"|front desk|chief of staff|personal assistant|travel (coordinator|manager)"),
    _out("business",
         r"\bstrategy\b|strategic|corporate development|business (operations|analyst|manager|planning)|\bbizops\b"
         r"|digital transformation"
         r"|chief (executive|operating|commercial|revenue|marketing|financial|people|legal|administrative|business|strategy)"
         r"|\bceo\b|\bcoo\b|\bcmo\b|\bcro\b|founder|general manager|venture|investment|investor|economist"
         r"|(business|financial|market|commercial|strategy|investment|operations|sales) analyst"
         r"|market (research|intelligence|development)|asset manag\w+|energy (markets?|trad\w+)|\btrader\b"
         r"|power marketing|\bofftake\b"),
    _out("project-development",
         r"project develop\w+|(real estate|land|site) (development|acquisition)|land (agent|manager)|\blandman\b"
         r"|real estate|permitting|permit (coordinator|manager|specialist)|\bsiting\b"),
    _out("facilities-ehs",
         r"facilit(y|ies)|\behs\b|\bhse\b|\behs&s\b|\besh\b|environment(al)?,? health|health (and|&) safety"
         r"|occupational|industrial hygien\w+|janitor\w*|custodi\w+|security (guard|officer)|groundskeep\w+"
         r"|safety (manager|specialist|coordinator|officer|director|technician|professional)"
         r"|environmental (engineer|scientist|specialist|manager|compliance|planner|analyst|coordinator)"
         r"|sustainability|\besg\b"),
    _out("operator-production",
         r"\boperators?\b|assembler|(production|manufacturing) (associate|worker|team member|specialist)"
         r"|material handler|forklift|\bpicker\b|\bpacker\b|laborer|\bhelper\b|\bdriver\b(?! (engineer|design|ic))"
         r"|\bcleaner\b|team member",
         unless=r"gate driver|motor driver|driver (engineer|design|development|board)"),
    _out("documentation-training",
         r"technical writer|technical (illustrator|publications?)|documentation (specialist|manager|lead)"
         r"|document controls?\b|\btrainer\b|\btraining\b|instructional design\w*|curriculum"),
    _out("design-ux",
         r"\bux\b|user (experience|interface|research\w*)|product design(er)?\b(?! engineer)"
         r"|(visual|interaction|content|brand|web|graphic) design\w*|creative director"),
]

# Out-of-scope functions as a department names them. Used only when the title
# names no discipline.
DEPARTMENT_OUT = re.compile(
    r"\bsales\b|marketing|\bpeople\b|human resources|\bhr\b|talent|recruit|financ|accounting|\blegal\b|g&a"
    r"|general (and|&) admin|administrat|\bit\b|information technology|business development|policy|government"
    r"|communications|customer success|\bcorporate\b|strategy|real estate|workplace|supply chain|procurement"
    r"|purchasing|logistics|commercial|partnerships|\bgrowth\b|business systems"
    r"|enterprise (systems|technology|applications)"
)
DEPARTMENT_OUT_REASON = [
    ("sales", r"\bsales\b|business development|commercial|partnerships|\bgrowth\b"),
    ("marketing-communications", r"marketing|communications"),
    ("recruiting", r"talent|recruit"),
    ("people-hr", r"\bpeople\b|human resources|\bhr\b|workplace"),
    ("finance-accounting", r"financ|accounting"),
    ("legal", r"\blegal\b"),
    ("policy", r"policy|government"),
    ("it", r"\bit\b|information technology|business systems|enterprise (systems|technology|applications)"),
    ("supply-chain", r"supply chain|procurement|purchasing|logistics"),
    ("customer-success", r"customer success"),
    ("project-development", r"real estate"),
    ("business", r"."),
]

# Departments that overrule a title naming only a broad discipline.
DEPARTMENT_VETO = re.compile(
    r"information technology|\bit\b|business systems|enterprise (systems|technology|applications)|\blegal\b|policy"
    r"|government|\bgrowth\b|marketing|\bpeople\b|human resources|\bhr\b|financ|accounting|talent"
)
BROAD_DISCIPLINES = frozenset({"quality", "field", "product", "program", "systems"})
# Role nouns that are usually coordination or support, not engineering.
SUPPORT_NOUN = re.compile(r"\b(associate|coordinator|specialist|analyst|administrator|clerk|agent)\b")

# Left out by a judgement the owner may want to reverse, so the evaluation
# sheet samples them as unsure.
JUDGEMENT_REASONS = frozenset({"facilities-ehs", "operator-production", "project-development", "policy"})

# A department whose untitled roles are still engineering work.
ENGINEERING_DEPARTMENT = re.compile(
    r"engineer|\br ?& ?d\b|research|\bscience\b|hardware|product development|air vehicle|powertrain|airframe"
)

# A role noun that marks hands-on trade or technician work. Kept by default.
TECHNICIAN = re.compile(
    r"\btechnicians?\b|\btech\b|machinist|welder|electrician|\bmechanic\b|fabricator|\binspector\b|installer|lineman"
)

# Titles that are engineering work even when no discipline word is present.
ENGINEERING_TITLE = re.compile(
    r"engineer|scientist|technician|technologist|designer|architect|researcher|physicist|chemist|machinist"
    r"|electrician|welder|\bmechanic\b|\bintern(ship)?\b|\bco-?op\b|\bcto\b|chief technology|r&d|\bhardware\b"
)

# --------------------------------------------------------------------------
# Discipline phrases, most specific first. Each match is blanked afterwards.
# --------------------------------------------------------------------------

def _rule(pattern: str, *disciplines: str, weak: bool = False, note: str | None = None):
    return re.compile(pattern), disciplines, weak, note


RULES = [
    # Phrases that would mislead the general words below.
    _rule(r"member of (the )?technical staff|chief of staff"),
    _rule(r"fuel cells?|solar cells?|photovoltaic cells?|work ?cells?|cell (phone|culture|tower)"),
    _rule(r"(change|configuration|inventory|cost|export|internal|financial|access|production|materials?|traffic) controls?"),
    _rule(r"control (room|tower|cent(er|re))"),
    _rule(r"data quality|safety[- ]critical|safety software|production forecast\w*|\breserves\b"),
    _rule(r"quality controls?|quality assurance", "quality"),
    _rule(r"projects? controls?|planning (and|&) controls?|\bpp&c\b|(project|production|program) steering( (and|&) controls?)?",
          "program"),
    _rule(r"crash( (and |& )?safety)?", "mechanical"),
    _rule(r"power quality", "power-systems"),
    _rule(r"control panels?", "electrical"),

    # Software written for hardware, named outright.
    _rule(r"software (qa|quality)|qa automation|\bsdet\b|software development engineer in test|software test\w*"
          r"|test automation|automat(ed|ion) test\w*|qa\)? automation", "software", "test"),
    _rule(r"\bscada\b", "software"),
    _rule(r"\bems\b|energy management (systems?|software)|\bderms?\b|\bvpp\b|virtual power plant", "software"),
    _rule(r"data acquisition|\bdaq\b", "test", "software"),

    # Embedded software is firmware, not generic software.
    _rule(r"embedded (software|sw|linux|firmware)|embedded|firmware|\bfw\b|\brtos\b|bootloader|device drivers?"
          r"|\bbsp\b|autosar|microcontrollers?|\bmcu\b", "firmware"),

    # Generic software titles: resolved later, in scope only with a hardware tie.
    _rule(r"software automation|automation software|site reliability|forward deployed|software|\bdevelopers?\b|programmer|back[- ]?end|front[- ]?end|full[- ]?stack|dev ?ops|\bsre\b|\bcloud\b"
          r"|platform engineer\w*|infrastructure engineer\w*|data (engineer\w*|scien\w+|analy\w+|platform|architect)"
          r"|machine learning|\bml\b|\bai\b|artificial intelligence|deep learning|computer vision|perception"
          r"|\bweb\b|mobile (engineer|developer|app\w*)|\bios\b|android|\bqa\b|applied scientist|analytics engineer"
          r"|database|\bui\b|\bdigital\b", SOFTWARE),

    # Power electronics before electrical.
    _rule(r"(\bev\b|evse|charger|charging) (service |field )?(technician|installer)", "field"),
    _rule(r"power electronics?|power conver(sion|ters?)|inverters?|converters?|\bdc[-/ ]?dc\b|\bac[-/ ]?dc\b|magnetics"
          r"|gate driv\w+|motor drives?|power stage|power suppl(y|ies)|power modules?|power devices?"
          r"|power semiconductors?|\bpcs\b|\bups\b|rectifiers?|chargers?\b|power hardware|\bsic\b|\bgan\b"
          r"|wide[- ]bandgap", "power-electronics"),
    _rule(r"pulsed power", "power-electronics", weak=True, note="pulsed-power"),

    # Power systems and grid.
    _rule(r"power plant controllers?|\bppc\b", "controls", "power-systems"),
    _rule(r"protection (and|&) controls?|protection engineer\w*|\brelays?\b", "power-systems"),
    _rule(r"power systems? engineer\w*", "power-systems"),
    _rule(r"power systems?", "power-systems", note="power-systems-phrase"),
    _rule(r"interconnection|substations?|switchgear|medium[- ]voltage|\bmv\b|microgrids?|\bgrid\b|\bt&d\b"
          r"|transmission (planning|lines?|(and|&) distribution|interconnection)|load flow|power flow"
          r"|utility[- ]scale|plant electrical|electrical studies|power delivery", "power-systems"),

    # Battery and cell.
    _rule(r"anode|cathode|electrolyte|electrode|separator", "battery", "materials"),
    _rule(r"(hv|lv|high[- ]voltage|low[- ]voltage) batter(y|ies)|batter(y|ies)|\bbms\b|\bbess\b|\bcells?\b|\bpack\b", "battery"),

    # Thermal and fluids.
    _rule(r"thermo[- ]?mechanical", "thermal", "mechanical"),
    _rule(r"\bthermal|\bthermo\w*|heat (transfer|exchangers?|pumps?|rejection)|\bfluids?\b|\bhvac\b|air handling|refrigera\w+|cooling"
          r"|cryogen\w*|\bcryo\b|\bcfd\b|combustion|aerodynamic\w*|aero[- ]?thermal|hydraulics?|pneumatics?|\bvacuum\b",
          "thermal"),

    # Controls. Factory flavour is decided afterwards.
    _rule(r"electrical,? (and |& )?instrumentation,? (and|&) controls?|instrumentation (and|&) controls?"
          r"|\bi ?& ?c\b|\bic&s\b|\be ?& ?i\b|\bei&c\b", "controls", "electrical"),
    _rule(r"(industrial|process|plc) controls?|\bplcs?\b", "controls", note="plc"),
    _rule(r"vehicle dynamics", "mechanical", "controls"),
    _rule(r"\bcontrols?\b|\bgnc\b|guidance,? navigation|simulink|model[- ]based design|state estimation"
          r"|model(l)?ing (and|&|,) simulation|simulation (and|&) model(l)?ing|model(l)?ing (and|&) controls?"
          r"|flight dynamics", "controls"),
    _rule(r"model(l)?ing|simulation|algorithms?", "controls", weak=True, note="modelling-generic"),

    # Test and validation.
    _rule(r"\bemc\b|\bemi\b", "electrical"),
    _rule(r"test (equipment|fixtures?|stands?|infrastructure)( design)?|design verification|\bdvt?\b|\bv ?& ?v\b|validation|verification|hardware[- ]in[- ]the[- ]loop"
          r"|hardware in loop|\bhil\b|reliability|durability|\bate\b|\btest\w*|qualification|failure analysis"
          r"|calibration", "test"),
    _rule(r"instrumentation", "test", "electrical", note="instrumentation-generic"),
    _rule(r"\blab(oratory)?\b", "test", weak=True, note="lab-generic"),

    # Quality, safety and compliance.
    _rule(r"functional safety|systems? safety", "systems", "quality"),
    _rule(r"process safety", "chemical-process", "quality"),
    _rule(r"quality|\bsqe\b|\bqms\b|\bqc\b|compliance|conformity|certification|homologation|\bsafety\b|\bfmea\b"
          r"|regulatory|inspect\w+|metrology|\bcmm\b|\bnrtl\b|auditor", "quality"),
    _rule(r"licensing", "quality", weak=True, note="licensing"),

    # Manufacturing; "process engineer" is resolved afterwards.
    _rule(r"supplier (industriali[sz]ation|development)", "manufacturing", "quality"),
    _rule(r"process (engineer\w*|technician|integration|development)", PROCESS),
    _rule(r"process (design|systems?|scale[- ]?up|model(l)?ing|simulation)|chemical (engineer\w*|process\w*|technician)"
          r"|pilot plant|scale[- ]?up|hydrometallurg\w+|pyrolysis|unit operations", "chemical-process"),
    _rule(r"manufactur\w+|\bmfg\b|\bnpi\b|new product introduction|industrial engineer\w*|industriali[sz]ation"
          r"|\bproduction\b|\bfactory\b|tooling|equipment (engineer\w*|design|development|maintenance|technician)"
          r"|\bassembly\b|\bweld\w*|machinist|machining|machine shop|\bcnc\b|fabricat\w+|\blean\b"
          r"|continuous improvement|six sigma|\bmes\b|plant (engineer\w*|manager)", "manufacturing"),
    _rule(r"automation", "manufacturing", note="automation-word"),
    _rule(r"\bo&m\b|operations (and|&) maintenance", "field"),
    _rule(r"maintenance", "manufacturing", note="maintenance"),
    _rule(r"sustaining|operations engineer\w*", "manufacturing", weak=True, note="sustaining"),

    # Materials and R&D.
    _rule(r"materials? (engineer\w*|scien\w+|characteri[sz]ation|development|research|testing|synthesis|processing)"
          r"|\bmaterials\b|electrochem\w+|\bchemist\w*|metallurg\w+|polymers?|ceramics?|coatings?|synthesis"
          r"|postdoc\w*|post[- ]doctoral|thin[- ]film", "materials"),
    _rule(r"scientist|research (engineer|associate|scientist|fellow|technician|assistant)|researcher", "materials",
          note="research-word"),
    _rule(r"physicist|physics|plasma|nuclear|neutronics|superconduct\w+|\bmagnets?\b", "materials",
          weak=True, note="taxonomy-gap:physics-nuclear"),
    _rule(r"optic\w*|photonics?|\blasers?\b", "materials", weak=True, note="taxonomy-gap:optics"),
    _rule(r"epitax\w+", "materials"),
    _rule(r"reservoir|geolog\w+|geoscien\w+|geophysic\w+|geochem\w+|seismolog\w+|subsurface", "materials",
          weak=True, note="taxonomy-gap:subsurface"),
    _rule(r"drilling|completions?|\bwells?\b|wellsite", "mechanical", weak=True, note="taxonomy-gap:subsurface"),
    _rule(r"\br ?& ?d\b|research (and|&) development", "materials", weak=True, note="r-and-d-generic"),

    # Field and applications.
    _rule(r"sales engineer\w*|solutions (engineer\w*|architect)", "field", note="sales-engineering"),
    _rule(r"\bfield\b|commissioning|applications? engineer\w*|service (engineer\w*|technician|manager|operations"
          r"|delivery|specialist|systems)|technical support|customer support engineer\w*|product support"
          r"|\binstall\w+|\bsite (engineer|manager|supervisor|technician|lead|superintendent|operations"
          r"|integration)|superintendent|start-?up (engineer|technician|manager)|lineman", "field"),
    _rule(r"deployments?", "field", note="deployment-word"),
    _rule(r"construction|\bcivil\b|geotechnical", "field", weak=True, note="taxonomy-gap:civil-construction"),
    _rule(r"\bepc\b", "field", weak=True, note="epc"),

    # Product and program.
    _rule(r"product (manager|management|owner|line manager)|(head|director|vp|vice president),? (of )?product\b"
          r"|product lead", "product"),
    _rule(r"(program|project) (manager|management|lead|director|engineer\w*|coordinator|scheduler|delivery)"
          r"|\bscheduler\b|\bpmo\b|\btpm\b"
          r"|technical program|program chief|programs? (and|&)|director,? (of )?programs?\b", "program"),
    _rule(r"chief engineer", "systems", weak=True, note="chief-engineer"),

    # Mechanical.
    _rule(r"electro-?mechanical|mechatronics?", "mechanical", "electrical"),
    _rule(r"product design engineer\w*", "mechanical"),
    _rule(r"mechanical|mechanisms?|structur(es|al)|enclosures?|packaging|opto-?mechanic\w*|\bstress\b|\bfea\b"
          r"|finite element|\bcad\b|solidworks|catia|gd&t|dimensional|\bchassis|\bclosures|\binteriors?\b"
          r"|\bexteriors?\b|\bsuspension|\bbrakes?\b|\bsteering ?(gear|column|systems?)|\bsteering engineer\w*"
          r"|drivetrain|driveline|gearbox|\bpiping|pressure vessels?|rotating equipment|turbomachinery"
          r"|\bcompressors?|\bpumps?\b|\bturbines?|\bactuators?|\bbearings?\b|\bseal(s|ing)\b|\bplastics"
          r"|\bcastings?\b|sheet metal|\bcomposites?\b|\brigging|ground support|machine design"
          r"|drafter|drafting|\bnvh\b|mass properties|\bseats?\b|restraints|body (systems?|metals|structures?|exteriors?"
          r"|interiors?)|airframe|loads (and|&) dynamics", "mechanical"),
    _rule(r"\bcae\b", "mechanical", weak=True, note="cae-generic"),
    _rule(r"design(er)? engineer\w*|\bdesigner\b|industrial design\w*|powertrain|propulsion", "mechanical",
          weak=True, note="design-engineer-generic"),

    # Electrical.
    _rule(r"\bfpga\b|\basic\b|digital design", "electrical", "firmware"),
    _rule(r"electrical|electronics?|\bpcba?\b|board design|circuits?|\banalog\b|mixed[- ]signal|\brf\b|antennas?"
          r"|harness\w*|\bwir(e|ing)\b|\bcabl(e|es|ing)\b|\bewis\b|high[- ]voltage|low[- ]voltage|\bhv\b|\blv\b"
          r"|avionics|schematics?|electric (machines?|motors?|drives?|powertrain)|\bmotors?\b|e-?motor|electrician",
          "electrical"),
    _rule(r"hardware (design )?engineer\w*|hardware (design|development)", "electrical", note="hardware-generic"),
    _rule(r"\bhardware\b|\bsensors?\b", "electrical", weak=True, note="hardware-generic"),
]

# "systems engineer" and its relatives. Read from the unmasked title, because
# the word before "systems" decides whether it is a systems role at all.
SYSTEMS = re.compile(
    r"\bsystems?[ -](engineer(s|ing)?|architect(s|ure)?|integration|design|development)\b"
    r"|\brequirements\b|\bmbse\b|vehicle integration|(product|platform) integration|integration engineer\w*"
    r"|vehicle (architect\w*|systems)"
)
SYSTEMS_WEAK = re.compile(r"\bintegration\b")
# "control systems engineer" is controls, not systems; and so on.
NOT_SYSTEMS_AFTER = frozenset({
    "control", "controls", "power", "embedded", "thermal", "fluid", "fluids", "vacuum", "cryogenic", "cooling",
    "hvac", "information", "business", "it", "erp", "hr", "finance", "financial", "people", "enterprise",
    "process", "management", "security", "handling",
})

SEPARATORS = re.compile(r",| - |\(|\)|:|\||;| @ ")

# Signs that a controls title means factory automation.
FACTORY_TITLE = re.compile(r"manufactur|\bfactory\b|production|equipment|automation|\bmfg\b")
FACTORY_DEPARTMENT = re.compile(r"manufactur|production|factory|automation|equipment")
FACTORY_TEXT = [
    r"factory automation", r"production lines?", r"manufacturing equipment", r"\bmes\b", r"conveyor",
    r"robot(ic)? cells?", r"automated (assembly|equipment|manufacturing)", r"machine builders?",
    r"equipment vendors?", r"ladder logic", r"\boee\b",
]
PRODUCT_CONTROL_TEXT = [
    r"control algorithms?", r"plant models?", r"simulink", r"state estimation", r"control (law|strategy|strategies)",
    r"model[- ]based", r"closed[- ]loop", r"control software for (our|the) (product|system)", r"power plant controller",
    r"dispatch",
]

CHEMICAL_TEXT = [
    r"chemical engineer\w*", r"p&ids?", r"\bpfds?\b", r"aspen", r"hazop", r"mass (and energy )?balances?",
    r"heat and material", r"\breactors?\b", r"distillation", r"unit operations?", r"pilot plant", r"electrolyz\w+",
    r"refin(ing|ery)", r"scale[- ]up", r"process safety", r"process design", r"process flow diagrams?",
]
MANUFACTURING_TEXT = [
    r"manufacturing (process\w*|engineer\w*|line)", r"production lines?", r"\byield\b", r"\bspc\b",
    r"work instructions?", r"\blean\b", r"six sigma", r"\bnpi\b", r"throughput", r"\boee\b", r"pfmea",
    r"cycle time", r"high[- ]volume", r"statistical process control", r"operators",
]

# Words that tie a generic software title to hardware.
TIE_TITLE = re.compile(
    r"fleet|telemetry|\bdevices?\b|\biot\b|robot\w*|vehicle|charging|charger|\bgrid\b|energy|hardware|simulation"
    r"|(engineering|hardware|test|manufacturing|lab) tools?|factory|manufacturing|\bplant\b|\bedge\b|real[- ]time"
    r"|autonomy|drone|aircraft|flight|sensors?|physics|model(l)?ing|optimi[sz]ation|forecasting|dispatch|\bder\b"
    r"|solar|storage|battery|thermal|\bpower\b|infotainment|avionics|\bbms\b|\bplc\b|operational technology"
)
TIE_TEXT = [
    r"firmware", r"embedded", r"telemetry", r"\bscada\b", r"\bplcs?\b", r"modbus", r"can ?bus|\bcanopen\b|j1939",
    r"\bhil\b|hardware[- ]in[- ]the[- ]loop", r"test automation", r"labview", r"\bsensors?\b", r"real[- ]time",
    r"\brtos\b", r"edge devices?", r"\biot\b", r"\bocpp\b", r"data acquisition", r"control systems?",
    r"\bfleet\b", r"manufacturing execution|\bmes\b", r"hardware (teams?|engineers?)", r"physical (systems?|devices?|assets?)",
    r"test (stands?|equipment|benches)", r"energy management system", r"\bderms?\b", r"device (software|drivers?)",
]
TIE_TEXT_NEEDED = 2

# Phrases in the posting text, per discipline. Used only when the title and
# the department name nothing, and only for engineering titles.
TEXT_CUES = {
    "electrical": [r"schematics?", r"\bpcba?s?\b", r"altium", r"circuits?", r"\banalog\b", r"harness\w*", r"wiring",
                   r"oscilloscopes?", r"connectors?", r"high[- ]voltage", r"low[- ]voltage", r"electrical design",
                   r"\bemc\b|\bemi\b", r"orcad|cadence"],
    "power-electronics": [r"inverters?", r"converters?", r"dc[-/]dc", r"power electronics", r"gate driv\w+",
                          r"magnetics", r"mosfets?", r"igbts?", r"\bsic\b", r"\bgan\b", r"topolog(y|ies)",
                          r"power stage"],
    "battery": [r"batter(y|ies)", r"\bcells?\b", r"\bbms\b", r"battery packs?", r"lithium", r"cathode", r"anode",
                r"state of charge", r"cycling", r"electrochemical"],
    "power-systems": [r"interconnection", r"substations?", r"protection", r"relays?", r"pscad", r"pss/?e",
                      r"load flow", r"short circuit", r"transformers?", r"switchgear", r"grid code",
                      r"ieee 1547", r"medium[- ]voltage"],
    "mechanical": [r"solidworks", r"\bcad\b", r"gd&t", r"mechanical design", r"\bfea\b", r"ansys", r"tolerance\w*",
                   r"sheet metal", r"machining", r"drawings", r"structural", r"\bcreo\b", r"catia", r"weldments?",
                   r"fasteners?"],
    "thermal": [r"thermal", r"heat transfer", r"\bcfd\b", r"heat exchangers?", r"fluids?", r"\bhvac\b",
                r"refrigerant", r"cooling", r"thermodynamic\w*", r"compressors?"],
    "controls": [r"control algorithms?", r"simulink", r"matlab", r"state machines?", r"\bpid\b", r"control systems?",
                 r"plant models?", r"model(l)?ing and simulation", r"feedback", r"estimation", r"controller design"],
    "firmware": [r"firmware", r"embedded", r"\brtos\b", r"microcontrollers?", r"c/c\+\+", r"embedded c\b",
                 r"bootloader", r"device drivers?", r"can ?bus|j1939", r"\bspi\b", r"\bi2c\b", r"\buart\b",
                 r"stm32", r"arm cortex"],
    "test": [r"test plans?", r"test fixtures?", r"\bhil\b|hardware[- ]in[- ]the[- ]loop", r"validation",
             r"verification", r"\bdvt\b", r"labview", r"data acquisition", r"test stands?", r"test equipment",
             r"reliability", r"\bhalt\b", r"test procedures?", r"test reports?"],
    "manufacturing": [r"manufacturing (process\w*|engineer\w*)", r"production lines?", r"\bnpi\b",
                      r"work instructions?", r"\blean\b", r"six sigma", r"\byield\b", r"\bspc\b", r"pfmea",
                      r"tooling", r"throughput", r"\bmes\b", r"\bplcs?\b", r"cycle time"],
    "chemical-process": CHEMICAL_TEXT,
    "materials": [r"materials science", r"characteri[sz]ation", r"\bsem\b", r"\bxrd\b", r"synthesis",
                  r"electrochemistry", r"publications?", r"laborator(y|ies)", r"experiments?", r"microscopy",
                  r"spectroscopy", r"metallurg\w+"],
    "quality": [r"quality (systems?|management|engineer\w*)", r"iso ?9001", r"\bcapa\b", r"root cause", r"audits?",
                r"\bncrs?\b", r"\b8d\b", r"supplier quality", r"inspection", r"\bqms\b", r"certification",
                r"\bnrtl\b"],
    "field": [r"commissioning", r"field service", r"customer sites?", r"installation", r"troubleshoot\w*",
              r"on[- ]site support", r"start-?up", r"\bo&m\b", r"warranty"],
    "systems": [r"requirements", r"system architecture", r"interface control", r"\bicds?\b",
                r"verification and validation", r"trade stud(y|ies)", r"\bmbse\b", r"sysml", r"\bfmea\b",
                r"hazard analysis", r"\bdoors\b", r"\bjama\b", r"conops"],
    "product": [r"roadmaps?", r"product requirements", r"\bprds?\b", r"customer discovery", r"product strategy"],
    "program": [r"milestones", r"risk registers?", r"program management", r"gantt", r"\bpmp\b",
                r"project schedules?"],
}
TEXT_CUES_NEEDED = 3
TEXT_CUES_KEPT = 2

_COMPILED: dict[str, re.Pattern] = {}


def _count(patterns: list[str], text: str) -> int:
    """How many of the patterns appear at least once in the text."""
    total = 0
    for pattern in patterns:
        compiled = _COMPILED.get(pattern)
        if compiled is None:
            compiled = _COMPILED[pattern] = re.compile(pattern)
        if compiled.search(text):
            total += 1
    return total


def normalise(value: str | None) -> str:
    """Lower-case, with every kind of dash (and the damaged dashes in the seed
    data) turned into ' - ' so separators are found."""
    text = (value or "").lower()
    text = re.sub(r"\s*[–—‒―�]\s*", " - ", text)
    text = text.replace("‑", "-").replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()


def _segment_of(position: int, breaks: list[int]) -> int:
    return sum(1 for b in breaks if b <= position)


def _hits(text: str) -> list[Hit]:
    """Every discipline phrase in the text, most specific rules first."""
    masked = text
    hits: list[Hit] = []
    for pattern, disciplines, weak, note in RULES:
        spans = [match.span() for match in pattern.finditer(masked)]
        if not spans:
            continue
        for start, end in spans:
            hits += [Hit(discipline, start, end, weak, note) for discipline in disciplines]
            masked = masked[:start] + " " * (end - start) + masked[end:]
    for match in SYSTEMS.finditer(text):
        before = text[:match.start()].split()
        if match.group(0).startswith("system") and before and before[-1].strip("/&") in NOT_SYSTEMS_AFTER:
            continue
        hits.append(Hit("systems", match.start(), match.start() + len("systems"), False, None))
    if not any(hit.discipline == "systems" for hit in hits):
        for match in SYSTEMS_WEAK.finditer(text):
            hits.append(Hit("systems", match.start(), match.end(), True, "integration-generic"))
    return hits


def _ordered(hits: list[Hit], text: str) -> list[str]:
    """Order the disciplines: the part of the title that names the role comes
    first, and inside it the word nearest the role noun leads ("Mechanical
    Test Engineer" is a test role). Later parts follow in reading order."""
    if not hits:
        return []
    breaks = [match.start() for match in SEPARATORS.finditer(text)]
    by_segment: dict[int, list[Hit]] = {}
    for hit in hits:
        by_segment.setdefault(_segment_of(hit.start, breaks), []).append(hit)
    first = min(by_segment)
    order: list[str] = []
    lead = sorted(by_segment[first], key=lambda h: (-h.end, h.start))
    lead_ids = list(dict.fromkeys(hit.discipline for hit in lead))
    # "Electrical Systems Engineer" is an electrical role working at system
    # level, so a discipline named just before "systems" goes ahead of it.
    if len(lead_ids) > 1 and lead_ids[0] == "systems":
        lead_ids[0], lead_ids[1] = lead_ids[1], lead_ids[0]
    order += lead_ids
    for segment in sorted(by_segment):
        if segment == first:
            continue
        for hit in sorted(by_segment[segment], key=lambda h: h.start):
            if hit.discipline not in order:
                order.append(hit.discipline)
    return order


def _read(text: str) -> tuple[list[str], list[str], bool]:
    """Disciplines named in a title or department, the notes of the rules
    that fired, and whether only weak rules fired."""
    hits = _hits(text)
    strong = [hit for hit in hits if not hit.weak]
    # "Mechanical Engineer, Hardware Design" is mechanical: the word
    # "hardware" only means electronics when nothing mechanical is named.
    if any(hit.discipline in ("mechanical", "thermal") for hit in strong):
        strong = [hit for hit in strong if hit.note != "hardware-generic"] or strong
    # Beside a software title, "automation", "deployment" and "research" are
    # software words: test automation, software deployment, AI research.
    if any(hit.discipline in (SOFTWARE, "software") for hit in strong):
        software_words = ("automation-word", "deployment-word", "research-word")
        strong = [hit for hit in strong if hit.note not in software_words]
    used = strong
    if not strong:
        # Among weak readings, a specific word ("laser", "reservoir") beats
        # a generic one ("simulation", "integration").
        generic = ("modelling-generic", "integration-generic")
        used = [hit for hit in hits if hit.note not in generic] or hits
    quiet = ("automation-word", "deployment-word", "research-word")
    notes = list(dict.fromkeys(hit.note for hit in used if hit.note and hit.note not in quiet))
    return _cap(_ordered(used, text)), notes, bool(hits) and not strong


def _cap(disciplines: list[str]) -> list[str]:
    """At most three. When a title names more, the broad ones go first:
    "Battery Software & Controls Integration Engineer" keeps battery,
    software and controls, and loses systems."""
    kept = list(disciplines)
    for broad in ("systems", "program"):
        if len(kept) > MAX_DISCIPLINES and broad in kept:
            kept.remove(broad)
    return kept[:MAX_DISCIPLINES]


def _resolve_process(title: str, department: str, text: str) -> tuple[str, bool]:
    """'Process engineer' is manufacturing at a factory and chemical-process
    at a plant. Returns the discipline and whether the choice was a default."""
    context = f"{title} {department}"
    chemical = _count(CHEMICAL_TEXT, text) + 2 * bool(re.search(r"chemical|electrolyz|refin|pilot plant|plant process", context))
    factory = _count(MANUFACTURING_TEXT, text) + 2 * bool(re.search(r"manufactur|production|factory|\bnpi\b|assembly", context))
    if chemical > factory:
        return "chemical-process", False
    if factory > chemical:
        return "manufacturing", False
    return "manufacturing", True


def _has_tie(title: str, department: str, text: str, others: list[str]) -> tuple[bool, str, str]:
    """Is a generic software title tied to hardware? Returns (tied, evidence, confidence)."""
    if any(discipline in HARD_DISCIPLINES for discipline in others):
        return True, "title", "high"
    if TIE_TITLE.search(title):
        return True, "title", "medium"
    if department:
        named, _, _ = _read(department)
        if any(discipline in HARD_DISCIPLINES for discipline in named) or TIE_TITLE.search(department):
            return True, "department", "medium"
    if _count(TIE_TEXT, text) >= TIE_TEXT_NEEDED:
        return True, "text", "low"
    return False, "none", "medium"


def _from_text(text: str) -> list[str]:
    scores = {discipline: _count(patterns, text) for discipline, patterns in TEXT_CUES.items()}
    ranked = sorted((d for d, score in scores.items() if score >= TEXT_CUES_NEEDED), key=lambda d: (-scores[d], d))
    return ranked[:TEXT_CUES_KEPT]


def _lower(confidence: str, to: str) -> str:
    order = ["high", "medium", "low"]
    return order[max(order.index(confidence), order.index(to))]


def classify(title: str, department: str | None = None, text: str | None = None,
             keep_technicians: bool = True) -> Decision:
    """Scope and disciplines for one posting."""
    title_n = normalise(title)
    department_n = normalise(department)
    text_n = normalise(text)

    disciplines, notes, weak_only = _read(title_n)

    # 1. Functions the board does not list. An engineer or technician whose
    #    title names a discipline before the off-list word stays in
    #    ("Controls Engineer - Warehouse Automation").
    for reason, pattern, unless in OUT_RULES:
        match = pattern.search(title_n)
        if not match or (unless and unless.search(title_n)):
            continue
        hands_on = re.search(r"\b(engineers?|technicians?|scientists?)\b", title_n)
        named_first = [hit for hit in _hits(title_n)
                       if not hit.weak and hit.discipline != SOFTWARE and hit.start < match.start()]
        if hands_on and named_first:
            notes.append(f"out-word-in-title:{reason}")
            break
        return Decision(False, reason=reason, evidence="title",
                        confidence="medium" if reason in JUDGEMENT_REASONS else "high")

    if not keep_technicians and TECHNICIAN.search(title_n):
        return Decision(False, reason="technician", evidence="title")

    confidence, evidence = "high", "title"
    if weak_only:
        confidence = "low"

    # 2. Placeholders.
    if PROCESS in disciplines:
        resolved, defaulted = _resolve_process(title_n, department_n, text_n)
        disciplines = [resolved if d == PROCESS else d for d in disciplines]
        if defaulted:
            notes.append("process-engineer-default")
            confidence = _lower(confidence, "medium")

    if SOFTWARE in disciplines:
        others = [d for d in disciplines if d != SOFTWARE]
        tied, tie_evidence, tie_confidence = _has_tie(title_n, department_n, text_n, others)
        if not tied:
            return Decision(False, reason="software-no-hardware-tie", evidence="title", confidence="medium",
                            notes=["no-tie-found"] if not text_n else [])
        disciplines = ["software" if d == SOFTWARE else d for d in disciplines]
        confidence = _lower(confidence, tie_confidence)
        if tie_evidence != "title":
            notes.append(f"software-tie-from-{tie_evidence}")
    disciplines = list(dict.fromkeys(disciplines))

    # 3. Controls at a factory is manufacturing work.
    if "controls" in disciplines and "manufacturing" not in disciplines:
        factory = bool(FACTORY_TITLE.search(title_n)) or bool(FACTORY_DEPARTMENT.search(department_n))
        if not factory and text_n:
            factory_score, product_score = _count(FACTORY_TEXT, text_n), _count(PRODUCT_CONTROL_TEXT, text_n)
            if factory_score >= 2 and factory_score > product_score:
                factory = True
                notes.append("controls-factory-from-text")
                confidence = _lower(confidence, "medium")
        if factory:
            disciplines.insert(disciplines.index("controls"), "manufacturing")
        elif "plc" in notes:
            confidence = _lower(confidence, "medium")
    if "plc" in notes and "manufacturing" in disciplines:
        notes.remove("plc")

    for note in notes:
        if note in ("power-systems-phrase", "hardware-generic", "instrumentation-generic", "maintenance",
                    "sales-engineering") or note.startswith("out-word-in-title"):
            confidence = _lower(confidence, "medium")
        if note.startswith("taxonomy-gap") or note == "sales-engineering":
            confidence = _lower(confidence, "low")

    # A title that names a discipline outright is settled. The department is
    # not added on top: department names are too loose ("Operations and
    # Maintenance", "Flight Test and Operational Safety") to tag from.
    if disciplines and not weak_only:
        # One exception: a title that names only a broad discipline, in a
        # department that is plainly not hardware ("Compliance Director" in
        # Legal, "Applications Engineer" in Business Systems), is left out.
        if set(disciplines) <= BROAD_DISCIPLINES and DEPARTMENT_VETO.search(department_n):
            reason = next(name for name, pattern in DEPARTMENT_OUT_REASON if re.search(pattern, department_n))
            return Decision(False, reason=reason, evidence="department", confidence="medium",
                            notes=["department-veto"])
        if SUPPORT_NOUN.search(title_n) and not re.search(r"engineer|technician|scientist|electrician", title_n):
            notes.append("support-role-noun")
            confidence = _lower(confidence, "medium")
        return Decision(True, disciplines[:MAX_DISCIPLINES], confidence=confidence, evidence=evidence, notes=notes)

    # 4. The department decides when the title names nothing, or names only
    #    a generic word.
    department_named: list[str] = []
    if department_n:
        department_named, _, department_weak = _read(department_n)
        department_named = [d for d in department_named if d not in (SOFTWARE, PROCESS)]
        if department_weak:
            department_named = []

    hands_on = bool(re.search(r"engineer|technician|scientist|\bintern(ship)?\b|\bco-?op\b|physicist|designer", title_n))
    engineering = bool(ENGINEERING_TITLE.search(title_n)) or bool(ENGINEERING_DEPARTMENT.search(department_n))

    if department_named and (engineering or weak_only or re.search(
            r"manager|lead|supervisor|director|head|specialist|coordinator|vp|vice president|chief", title_n)):
        merged = list(dict.fromkeys(department_named + disciplines))[:MAX_DISCIPLINES]
        return Decision(True, merged, confidence="medium" if hands_on else "low", evidence="department",
                        notes=notes + ["from-department"])

    if department_n and DEPARTMENT_OUT.search(department_n) and not (disciplines and hands_on):
        reason = next(name for name, pattern in DEPARTMENT_OUT_REASON if re.search(pattern, department_n))
        return Decision(False, reason=reason, evidence="department", confidence="medium")

    # 5. The posting text, for engineering titles and engineering
    #    departments. Not for the physics, optics and subsurface titles the
    #    taxonomy has no discipline for: the text scores would only add noise.
    gap = any(note.startswith("taxonomy-gap") for note in notes)
    if engineering and text_n and not gap:
        from_text = _from_text(text_n)
        if from_text:
            merged = list(dict.fromkeys(from_text + disciplines))[:MAX_DISCIPLINES]
            return Decision(True, merged, confidence="low", evidence="text", notes=notes + ["from-text"])

    if disciplines:   # weak title rules only
        return Decision(True, disciplines[:MAX_DISCIPLINES], confidence="low", evidence="title", notes=notes)

    if engineering:
        return Decision(False, reason="unplaced-engineering-title", evidence="none", confidence="low",
                        notes=["no-rule-matched"])
    return Decision(False, reason="no-hardware-discipline", evidence="none", confidence="medium")
