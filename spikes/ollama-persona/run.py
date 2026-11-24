"""M0 spike: can a small local model turn a resume into a valid persona?

Sends a SYNTHETIC resume to the local Ollama server with the persona schema as
a structured-output constraint, then checks the result three ways:

  1. Does it validate against schema/persona.schema.json and the taxonomy?
  2. Is each skill's evidence line actually in the resume?
  3. Did any identity detail (name, email, phone) leak into the persona?

Nothing leaves this machine: the only network call is to 127.0.0.1.

    uv run python -m spikes.ollama-persona.run            (not importable: hyphen)
    uv run python spikes/ollama-persona/run.py phi4-mini:latest
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.io import load_json, load_yaml  # noqa: E402
from tools.validate import check_persona, schema_errors, schema_registry  # noqa: E402

HERE = Path(__file__).resolve().parent
OLLAMA = "http://127.0.0.1:11434/api/chat"
IDENTITY_MARKERS = ("morgan", "okafor", "lindqvist", "example.com", "555-0142")


def model_schema(taxonomy: dict) -> dict:
    """The persona schema flattened for a model: enums spelled out, no $ref or oneOf."""
    def ids(key):
        return [entry["id"] for entry in taxonomy[key]]

    def id_list(key, max_items):
        return {"type": "array", "items": {"type": "string", "enum": ids(key)}, "maxItems": max_items}

    return {
        "type": "object",
        "required": ["disciplines", "level", "domains", "skills", "standards", "locations", "hard_constraints", "preferences"],
        "properties": {
            "disciplines": {**id_list("disciplines", 4), "minItems": 1},
            "level": {"type": "string", "enum": ids("levels")},
            "domains": id_list("sectors", 5),
            "skills": {
                "type": "array", "maxItems": 20,
                "items": {
                    "type": "object", "required": ["name", "years", "evidence"],
                    "properties": {"name": {"type": "string"}, "years": {"type": "number"}, "evidence": {"type": "string"}},
                },
            },
            "standards": {"type": "array", "items": {"type": "string"}},
            "locations": {
                "type": "object", "required": ["metros", "remote", "relocate"],
                "properties": {"metros": {"type": "array", "items": {"type": "string"}}, "remote": {"type": "boolean"}, "relocate": {"type": "boolean"}},
            },
            "hard_constraints": {
                "type": "object", "required": ["work_authorization"],
                "properties": {"work_authorization": {"type": "string"}},
            },
            "preferences": {
                "type": "object", "required": ["stage", "sectors", "min_base_usd"],
                "properties": {"stage": id_list("stages", 8), "sectors": id_list("sectors", 6), "min_base_usd": {"type": "integer"}},
            },
        },
    }


def prompt(taxonomy: dict, resume: str) -> list[dict]:
    disciplines = "\n".join(f"- {d['id']}: {d['covers']}" for d in taxonomy["disciplines"])
    system = (
        "You turn a resume into a structured job-search persona for a hardware engineering job board. "
        "Use only what the resume says. Do not include the person's name, email, phone number or employers.\n"
        "For each skill give the years of use you can support from the dates, and an evidence line copied "
        "word for word from the resume.\n"
        "Pick disciplines from this list by what the person mostly did:\n" + disciplines + "\n"
        "level is the level of the roles they are looking for. domains are sectors they have worked in. "
        "preferences come only from what they say they want. Answer with JSON only."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": resume}]


def normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def run(model: str) -> dict:
    taxonomy = load_yaml(ROOT / "taxonomy.yml")
    resume = (HERE / "resume_synthetic_01.txt").read_text(encoding="utf-8")
    body = {
        "model": model, "stream": False, "format": model_schema(taxonomy),
        "messages": prompt(taxonomy, resume),
        "options": {"temperature": 0, "num_ctx": 8192},
    }
    started = time.perf_counter()
    reply = httpx.post(OLLAMA, json=body, timeout=900).json()
    wall = time.perf_counter() - started
    if "error" in reply:
        return {"model": model, "error": reply["error"]}

    raw = reply["message"]["content"]
    result = {
        "model": model,
        "wall_seconds": round(wall, 1),
        "load_seconds": round(reply.get("load_duration", 0) / 1e9, 1),
        "prompt_tokens": reply.get("prompt_eval_count"),
        "output_tokens": reply.get("eval_count"),
        "tokens_per_second": round(reply["eval_count"] / (reply["eval_duration"] / 1e9), 1) if reply.get("eval_duration") else None,
    }
    try:
        draft = json.loads(raw)
    except json.JSONDecodeError as error:
        return {**result, "valid_json": False, "error": str(error), "raw": raw[:400]}

    persona = {
        "persona_version": 0,
        "generated": {"by": f"ollama/{model}", "on_device": True, "date": date.today().isoformat(), "reviewed": False},
        **draft,
    }
    registry, schemas = schema_registry()
    problems = schema_errors(persona, schemas["persona.schema.json"], registry) or check_persona(persona, taxonomy)

    resume_text = normalise(resume)
    skills = draft.get("skills", [])
    grounded = [s for s in skills if s.get("evidence") and normalise(s["evidence"]) in resume_text]
    leaks = sorted({marker for marker in IDENTITY_MARKERS if marker in raw.lower()})

    result.update({
        "valid_json": True,
        "schema_problems": problems,
        "skills": len(skills),
        "skills_with_verbatim_evidence": len(grounded),
        "identity_leaks": leaks,
        "persona": persona,
    })
    return result


def main() -> int:
    models = sys.argv[1:] or ["phi4-mini:latest"]
    out_dir = HERE / "out"
    out_dir.mkdir(exist_ok=True)
    for model in models:
        result = run(model)
        (out_dir / (re.sub(r"[^A-Za-z0-9._-]+", "_", model) + ".json")).write_text(
            json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        summary = {key: value for key, value in result.items() if key != "persona"}
        print(json.dumps(summary, indent=1))
        if "persona" in result:
            persona = result["persona"]
            print("  disciplines:", persona.get("disciplines"), "| level:", persona.get("level"), "| domains:", persona.get("domains"))
            print("  locations:", persona.get("locations"), "| preferences:", persona.get("preferences"))
            print("  standards:", persona.get("standards"))
            for skill in persona.get("skills", [])[:6]:
                print("   -", skill)
    return 0


if __name__ == "__main__":
    sys.exit(main())
