"""Run eval/tasks.json against a local or cloud OpenAI-compatible model and score it. Stdlib only.

  python eval/run_eval.py --target local            # Ollama on localhost
  python eval/run_eval.py --target cloud            # needs CLOUD_BASE_URL, CLOUD_API_KEY, CLOUD_MODEL
                                                    # optional CLOUD_PRICE_IN / CLOUD_PRICE_OUT (USD per 1M tokens)
"""
import argparse
import csv
import json
import os
import re
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent


def target_config(name):
    if name == "local":
        return {"base_url": os.getenv("LOCAL_BASE_URL", "http://localhost:11434/v1"),
                "api_key": "ollama", "model": os.getenv("LOCAL_MODEL", "gemma4:e4b"),
                "price_in": 0.0, "price_out": 0.0}
    missing = [k for k in ("CLOUD_BASE_URL", "CLOUD_API_KEY", "CLOUD_MODEL") if not os.getenv(k)]
    if missing:
        raise SystemExit(f"Set {', '.join(missing)} to run the cloud target.")
    return {"base_url": os.environ["CLOUD_BASE_URL"], "api_key": os.environ["CLOUD_API_KEY"],
            "model": os.environ["CLOUD_MODEL"],
            "price_in": float(os.getenv("CLOUD_PRICE_IN", "0")),
            "price_out": float(os.getenv("CLOUD_PRICE_OUT", "0"))}


def ask(cfg, prompt, timeout=300):
    """One chat completion. Returns (text, prompt_tokens, completion_tokens)."""
    body = json.dumps({"model": cfg["model"], "temperature": 0,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(cfg["base_url"].rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {cfg['api_key']}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    usage = data.get("usage") or {}
    return (data["choices"][0]["message"]["content"] or "",
            usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))


def extract_json(text):
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    candidate = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(candidate)


def check(text, checks):
    """Return a list of failed check descriptions (empty list = pass)."""
    low = text.lower()
    fails = []
    for word in checks.get("contains_all", []):
        if word.lower() not in low:
            fails.append(f"missing '{word}'")
    if "contains_any" in checks and not any(w.lower() in low for w in checks["contains_any"]):
        fails.append(f"none of {checks['contains_any']}")
    for word in checks.get("not_contains", []):
        if word.lower() in low:
            fails.append(f"contains '{word}'")
    if "regex" in checks and not re.search(checks["regex"], text.strip(), re.I):
        fails.append("regex not matched")
    if "json_keys" in checks:
        try:
            obj = extract_json(text)
            missing = [k for k in checks["json_keys"] if k not in obj]
            if missing:
                fails.append(f"json missing {missing}")
        except (ValueError, TypeError):
            fails.append("invalid json")
    if "max_words" in checks and len(text.split()) > checks["max_words"]:
        fails.append(f"over {checks['max_words']} words")
    return fails


def run(target, tasks, out_dir):
    cfg = target_config(target)
    rows = []
    for t in tasks:
        start = time.time()
        try:
            text, tin, tout = ask(cfg, t["prompt"])
            fails = check(text, t["checks"])
        except (urllib.error.URLError, KeyError, TimeoutError, OSError) as e:
            text, tin, tout, fails = "", 0, 0, [f"error: {e}"]
        secs = round(time.time() - start, 2)
        cost = (tin * cfg["price_in"] + tout * cfg["price_out"]) / 1e6
        rows.append({"target": target, "model": cfg["model"], "id": t["id"], "category": t["category"],
                     "passed": not fails, "seconds": secs, "cost_usd": round(cost, 6),
                     "failures": "; ".join(fails), "output": text.strip()[:500]})
        print(f"{'PASS' if not fails else 'FAIL'}  {t['id']:<4} {secs:>6}s  {'; '.join(fails)}")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{target}-{time.strftime('%Y%m%d-%H%M%S')}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return rows, path


def summary(rows):
    lines = ["| Category | Passed | Median s |", "| --- | --- | --- |"]
    for cat in sorted({r["category"] for r in rows}) + ["all"]:
        sel = [r for r in rows if cat == "all" or r["category"] == cat]
        lines.append(f"| {cat} | {sum(r['passed'] for r in sel)}/{len(sel)} | "
                     f"{statistics.median(r['seconds'] for r in sel):.1f} |")
    lines.append(f"\nTotal cost: ${sum(r['cost_usd'] for r in rows):.4f}")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", choices=["local", "cloud"], default="local")
    ap.add_argument("--tasks", default=str(HERE / "tasks.json"))
    ap.add_argument("--only", help="comma-separated task ids")
    a = ap.parse_args()
    tasks = json.loads(Path(a.tasks).read_text(encoding="utf-8"))["tasks"]
    if a.only:
        tasks = [t for t in tasks if t["id"] in a.only.split(",")]
    rows, path = run(a.target, tasks, HERE / "results")
    print(f"\nSaved {path}\n\n{summary(rows)}")
