"""Discipline rules, and the entry point that tags one posting.

`classify(title, department, text)` returns the role's function (see
function.py) and up to three disciplines, decided in this order:

  1. Which disciplines does the title name? Phrases are tried from the most
     specific to the most general, and each match is blanked so a general
     word cannot re-read it ("power electronics" is not also "electronics").
  2. For engineering and science roles whose title names none, the
     department is read the same way, then the posting text is scored
     against a short list of phrases per discipline.
  3. Technician, trades and other roles keep at most one discipline, and
     only one the title names ("electrical technician" is electrical).

Every decision carries a confidence and notes, so the evaluation sheet and
the run report can show which roles the rules were least sure of.

Discipline and function ids come from taxonomy.yml. Nothing here invents an id.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from pipeline.tag.function import decide_function

MAX_DISCIPLINES = 3
# Functions that carry one to three disciplines; every other function carries at most one.
TECHNICAL_FUNCTIONS = frozenset({"engineering", "science"})

# Placeholder resolved after matching.
PROCESS = "?process"      # "process engineer": manufacturing or chemical-process


@dataclass
class Decision:
    function: str
    disciplines: list[str] = field(default_factory=list)
    function_evidence: str = "title"     # title | department | text | default
    function_confidence: str = "high"    # high | medium | low
    confidence: str = "high"             # of the disciplines: high | medium | low
    evidence: str = "title"              # what decided the disciplines: title | department | text | none
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Hit:
    discipline: str
    start: int
    end: int
    weak: bool
    note: str | None


# Business functions whose roles carry no discipline.
CORPORATE_FUNCTIONS = frozenset({"sales-bd", "marketing", "finance-legal", "people-admin", "it"})

# --------------------------------------------------------------------------
# Discipline phrases, most specific first. Each match is blanked afterwards.
# --------------------------------------------------------------------------

def _rule(pattern: str, *disciplines: str, weak: bool = False, note: str | None = None):
    return re.compile(pattern), disciplines, weak, note


RULES = [
    # Phrases that would mislead the general words below.
    _rule(r"member of (the )?technical staff|chief of staff"),
    _rule(r"fuel cells?|solar cells?|photovoltaic cells?|work ?cells?|cell (phone|culture|tower)"),
    _rule(r"(change|configuration|document|inventory|cost|export|internal|financial|access|production|materials?|traffic) controls?"),
    _rule(r"control (room|tower|cent(er|re))"),
    _rule(r"data quality|safety[- ]critical|safety software|production forecast\w*|\breserves\b"),
    _rule(r"quality controls?|quality assurance", "quality"),
    _rule(r"projects? controls?|planning (and|&) controls?|\bpp&c\b|(project|production|program) steering( (and|&) controls?)?"),

    # Aerospace before software, controls, test and electrical take its words.
    _rule(r"flight controls?", "aerospace", "controls"),
    _rule(r"flight test\w*", "aerospace", "test"),
    _rule(r"flight software", "software", "aerospace"),
    _rule(r"avionics", "electrical", "aerospace"),
    _rule(r"airframe", "aerospace", "mechanical"),
    _rule(r"aerodynamic\w*|airworthiness|flight (dynamics|sciences|physics|performance)|\bevtol\b|aircraft"
          r"|propellers?|air vehicle", "aerospace"),
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

    # Data and machine learning, then software of every kind.
    _rule(r"data (engineer\w*|scien\w+|analy\w+|platform|architect\w*|ops)|\bdataops\b|machine learning|\bml\b|\bai\b"
          r"|artificial intelligence|deep learning|computer vision|perception|applied scientist|analytics", "data"),
    _rule(r"software automation|automation software|site reliability|forward deployed|software|\bdevelopers?\b"
          r"|programmer|back[- ]?end|front[- ]?end|full[- ]?stack|dev ?ops|\bsre\b|\bcloud\b|platform engineer\w*"
          r"|infrastructure engineer\w*|\bweb\b|mobile (engineer|developer|app\w*)|\bios\b|android|\bqa\b"
          r"|database|\bui\b|\bdigital\b|\bhpc\b|\bsw\b", "software"),

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
          r"|cryogen\w*|\bcryo\b|\bcfd\b|combustion|aero[- ]?thermal|hydraulics?|pneumatics?|\bvacuum\b",
          "thermal"),

    # Controls. Factory flavour is decided afterwards.
    _rule(r"electrical,? (and |& )?instrumentation,? (and|&) controls?|instrumentation (and|&) controls?"
          r"|\bi ?& ?c\b|\bic&s\b|\be ?& ?i\b|\bei&c\b", "controls", "electrical"),
    _rule(r"(industrial|process|plc) controls?|\bplcs?\b", "controls", note="plc"),
    _rule(r"vehicle dynamics", "mechanical", "controls"),
    _rule(r"\bcontrols?\b|\bgnc\b|guidance,? navigation|simulink|model[- ]based design|state estimation"
          r"|model(l)?ing (and|&|,) simulation|simulation (and|&) model(l)?ing|model(l)?ing (and|&) controls?"
          , "controls"),
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
    _rule(r"plasma|nuclear|neutronics|fusion (energy|power|systems?|engineer\w*|program)|fission|\bife\b"
          r"|inertial fusion|implosion|radiation|shielding|tritium|target (design|area|diagnostics)|molten salt",
          "nuclear-plasma"),
    _rule(r"electro-?optic\w*|optic\w*|photonics?|\blasers?\b|stray light|\bdiode\b", "optics"),
    _rule(r"physicist|physics|superconduct\w+|\bmagnets?\b", "materials", note="physics-generic"),
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
    _rule(r"\bcivil\b|geotechnical|foundations?|steel structures?|(epc|site|construction)\b.{0,25}structur\w*"
          r"|structur\w*.{0,25}\b(epc|civil)\b", "civil-structural"),
    _rule(r"construction"),
    _rule(r"\bepc\b", "field", weak=True, note="epc"),

    # Product and program words are functions, not disciplines (taxonomy v1).
    # They are blanked so the words inside them are not read as disciplines.
    _rule(r"product (manager|management|owner|line manager)|(head|director|vp|vice president),? (of )?product\b"
          r"|product lead"),
    _rule(r"(program|project) (manager|management|lead|director|engineer\w*|coordinator|scheduler|delivery)"
          r"|\bscheduler\b|\bpmo\b|\btpm\b|technical program|programs? (and|&)|director,? (of )?programs?\b"),
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
          r"|schematics?|electric (machines?|motors?|drives?|powertrain)|\bmotors?\b|e-?motor|electrician",
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
    # No "product" or "program" cues: since taxonomy v1 those are functions, not
    # disciplines, and a cue here would emit an id the taxonomy does not have.
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
    if any(hit.discipline in ("software", "data") for hit in strong):
        software_words = ("automation-word", "deployment-word", "research-word")
        strong = [hit for hit in strong if hit.note not in software_words]
    # "Laser Physicist" is optics; generic physics adds materials only when
    # nothing more specific is named.
    if any(hit.discipline in ("optics", "nuclear-plasma") for hit in strong):
        strong = [hit for hit in strong if hit.note != "physics-generic"]
    used = strong
    if not strong:
        # Among weak readings, a specific word ("laser", "reservoir") beats
        # a generic one ("simulation", "integration").
        generic = ("modelling-generic", "integration-generic")
        used = [hit for hit in hits if hit.note not in generic] or hits
    quiet = ("automation-word", "deployment-word", "research-word", "physics-generic")
    notes = list(dict.fromkeys(hit.note for hit in used if hit.note and hit.note not in quiet))
    return _cap(_ordered(used, text)), notes, bool(hits) and not strong


def _cap(disciplines: list[str]) -> list[str]:
    """At most three. When a title names more, the broad ones go first:
    "Battery Software & Controls Integration Engineer" keeps battery,
    software and controls, and loses systems."""
    kept = list(disciplines)
    for broad in ("systems",):
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


def _from_text(text: str) -> list[str]:
    scores = {discipline: _count(patterns, text) for discipline, patterns in TEXT_CUES.items()}
    ranked = sorted((d for d, score in scores.items() if score >= TEXT_CUES_NEEDED), key=lambda d: (-scores[d], d))
    return ranked[:TEXT_CUES_KEPT]


def _lower(confidence: str, to: str) -> str:
    order = ["high", "medium", "low"]
    return order[max(order.index(confidence), order.index(to))]




def classify(title: str, department: str | None = None, text: str | None = None) -> Decision:
    """Function and disciplines for one posting."""
    title_n = normalise(title)
    department_n = normalise(department)
    text_n = normalise(text)

    disciplines, notes, weak_only = _read(title_n)
    strong_starts = [hit.start for hit in _hits(title_n) if not hit.weak]
    role = decide_function(title_n, department_n, text_n, disciplines, weak_only, strong_starts)
    notes = notes + role.notes
    confidence = "low" if weak_only else "high"
    evidence = "title" if disciplines else "none"

    # "Process engineer" is manufacturing at a factory and chemical-process at a plant.
    if PROCESS in disciplines:
        resolved, defaulted = _resolve_process(title_n, department_n, text_n)
        disciplines = [resolved if d == PROCESS else d for d in disciplines]
        if defaulted:
            notes.append("process-engineer-default")
            confidence = _lower(confidence, "medium")
    disciplines = list(dict.fromkeys(disciplines))

    # Controls at a factory is manufacturing work.
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
        if note in ("power-systems-phrase", "hardware-generic", "instrumentation-generic", "maintenance"):
            confidence = _lower(confidence, "medium")
        if note.startswith("taxonomy-gap"):
            confidence = _lower(confidence, "low")

    technical = role.function in TECHNICAL_FUNCTIONS
    if technical and (not disciplines or weak_only):
        # The department, then the posting text, for an engineering or science
        # role whose title names no field outright.
        department_named: list[str] = []
        if department_n:
            department_named, _, department_weak = _read(department_n)
            department_named = [d for d in department_named if d != PROCESS]
            if department_weak:
                department_named = []
        gap = any(note.startswith("taxonomy-gap") for note in notes)
        if department_named:
            disciplines = list(dict.fromkeys(department_named + disciplines))
            confidence, evidence = "medium", "department"
            notes.append("from-department")
        elif text_n and not gap and (from_text := _from_text(text_n)):
            disciplines = list(dict.fromkeys(from_text + disciplines))
            confidence, evidence = "low", "text"
            notes.append("from-text")

    if technical:
        disciplines = _cap(disciplines)
        if not disciplines:
            notes.append("no-discipline")
    else:
        # Other functions carry at most one discipline, and only one the
        # title names outright ("Electrical Technician", "Global Supply
        # Manager - Electronics").
        # Corporate functions carry none: "Project Developer" is not software,
        # and "Senior Analyst, Manufacturing Finance" is not manufacturing.
        keep = disciplines and not weak_only and role.function not in CORPORATE_FUNCTIONS
        disciplines = disciplines[:1] if keep else []
    if not disciplines:
        evidence, confidence = "none", "high" if not technical else "low"

    return Decision(role.function, disciplines, role.evidence, role.confidence, confidence, evidence,
                    list(dict.fromkeys(notes)))
