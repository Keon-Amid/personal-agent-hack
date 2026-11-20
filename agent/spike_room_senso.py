"""S1 spike (throwaway): does a per-room doc in Senso make a too-wide sofa come back "conflict"?

Loads a SPIKE room doc with the senso CLI, waits for processing, runs two kb_accuracy checks
(one should conflict, one should verify), prints verdicts and quotes, then deletes the doc.

Run: SENSO_API_KEY in env (or .env) then
  .venv/bin/python -m agent.spike_room_senso
Live only; not part of the unit tests.
"""
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

API = "https://apiv2.senso.ai/api/v1"
QUESTION = "Will this furniture fit in the demo living room?"

ROOM_TEXT = "SPIKE: Demo living room: longest wall 88 inches, doorway 30 inches wide and 80 inches tall"
# Runs 1-2 used the task's literal wording; Senso marked every claim about_brand=False and judged none
# (CLI and REST alike). Run 3 uses "Our ..." (first person, like scored runs) so claims get judged.
CLAIMS = {
    "task_literal": "The KIVIK Sofa, 89.75 inches wide, fits on the living room's longest wall.",
    "conflict_fit": "Our KIVIK Sofa - Grann/Bomstad black is 89.375 inches wide and fits on our demo living room's longest wall.",
    "conflict_room_number": "Our demo living room's longest wall is 96 inches.",
    "verify_room": "Our demo living room's longest wall is 88 inches and its doorway is 30 inches wide.",
}


def _env():
    env = dict(os.environ)
    if "SENSO_API_KEY" not in env:
        p = pathlib.Path(__file__).resolve().parent.parent / ".env"
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("SENSO_API_KEY="):
                    env["SENSO_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
    return env


def senso(*args):
    out = subprocess.run(["senso", "--output", "json", "--quiet", "--no-update-check", *args],
                         capture_output=True, text=True, env=_env(), timeout=180)
    if out.returncode != 0:
        print("senso", args[:2], "failed:", out.stderr.strip() or out.stdout.strip(), file=sys.stderr)
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return {"raw": out.stdout, "stderr": out.stderr, "rc": out.returncode}


def rest_eval(text):
    """POST /org/evals/text with author+question (the CLI path skipped non-brand claims)."""
    body = json.dumps({"text": text, "author": "ai_assistant", "question": QUESTION, "wait": True}).encode()
    req = urllib.request.Request(API + "/org/evals/text", data=body, method="POST", headers={
        "X-API-Key": _env()["SENSO_API_KEY"], "Content-Type": "application/json",
        "User-Agent": "room-furnisher-spike/0.1"})
    run = json.load(urllib.request.urlopen(req, timeout=120))
    for _ in range(30):
        if run.get("status") in ("completed", "failed"):
            break
        time.sleep(2)
        run = senso("evals", "get", run["eval_run_id"])
    return run


def show(name, text, run):
    print(f"\n== {name}: {text}\nrun={run.get('eval_run_id')} status={run.get('status')} accuracy_pct={run.get('accuracy_pct')}")
    for c in run.get("claims", []):
        print(" -", c.get("verdict"), "passed=", c.get("passed"), "about_brand=", c.get("about_brand"), "|",
              c.get("claim_text"), "| quote:", c.get("quote"), "| reason:", c.get("reason"))


def main():
    doc = senso("kb", "create-raw", "--data", json.dumps({"text": ROOM_TEXT, "title": "SPIKE demo living room"}))
    print("created:", json.dumps(doc)[:400])
    content_id = doc.get("id")
    node_id = doc.get("kb_node_id") or doc.get("node_id") or content_id
    status = None
    for _ in range(40):
        node = senso("kb", "get", node_id)
        status = (node.get("content") or {}).get("processing_status")
        if status in ("completed", "complete", "processed", "ready", "failed"):
            break
        time.sleep(3)
    print("processing_status:", status)
    results = {}
    try:
        for name, text in CLAIMS.items():
            rest = rest_eval(text)  # CLI gave identical results in runs 1-2
            show(name + " [REST]", text, rest)
            results[name] = rest
        dump = pathlib.Path(os.environ.get("SPIKE_DUMP", "/dev/null"))
        dump.write_text(json.dumps(results, indent=1))
    finally:
        print("\ndelete:", json.dumps(senso("kb", "delete", node_id))[:300])
    return results


if __name__ == "__main__":
    main()
