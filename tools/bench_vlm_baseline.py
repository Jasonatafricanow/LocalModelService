#!/usr/bin/env python3
"""P0 baseline harness — measure *single-image* VLM stock-checking on real hardware.

Decision (2026-07-09): default is **one image per request, no collage**. This
script produces the data that decides whether collage is ever needed:

  * per-image latency (p50 / p95 / mean)
  * wall-clock to process a burst of N images **sequentially** (concurrency 1)
    vs. the SLA
  *货号 (product_code) accuracy + 品类 (type) accuracy + JSON-valid rate

Verdict:
  * PASS  -> single-image meets the SLA at acceptable accuracy -> DO NOT add collage.
  * FAIL(SLA)      -> too slow -> evaluate 2x2 vs 3x3 collage as a fallback.
  * FAIL(accuracy) -> model too weak -> bump model tier before anything else.

Usage (real run against Ollama on the 8GB box):
    python tools/bench_vlm_baseline.py \
        --manifest tools/bench_manifest.example.json \
        --images-dir /path/to/product_images \
        --base-url http://localhost:11434/v1 --api v1 \
        --model qwen2.5vl:3b --burst-size 20 --sla-seconds 180

llama.cpp (AMD 16GB) is the same, just --base-url http://localhost:8080/v1 --model <name>.

Validate the harness itself without any backend/images:
    python tools/bench_vlm_baseline.py --dry-run
    python tools/bench_vlm_baseline.py --dry-run --dry-miss 0.4 --dry-latency 12
"""
from __future__ import annotations

import argparse
import base64
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path

# Single-image prompt: language-neutral JSON only (葡语回复走文本路径，视觉只出 JSON).
PROMPT = (
    "You are a product-recognition assistant for a jewelry store. Look at the "
    "single image and return STRICT JSON only (no markdown, no prose) with this "
    'schema: {"product_code": <string or null>, "type": <string or null>, '
    '"quantity": <number or null>}. product_code is the small alphanumeric code '
    "printed on the tag/label (e.g. #12, A203). type is the jewelry category "
    "(colar/brinco/pulseira/anel or necklace/earring/bracelet/ring)."
)

# type 多语归一化 (pt <-> en) so scoring is language-agnostic.
TYPE_CANON = {
    "colar": "necklace", "necklace": "necklace",
    "brinco": "earring", "brincos": "earring", "earring": "earring", "earrings": "earring",
    "pulseira": "bracelet", "bracelet": "bracelet",
    "anel": "ring", "aneis": "ring", "anel(is)": "ring", "ring": "ring",
    "colar/gargantilha": "necklace", "gargantilha": "necklace",
}


# --------------------------------------------------------------------------- #
# Parsing / normalization
# --------------------------------------------------------------------------- #
def extract_json(text: str):
    """Best-effort JSON extraction, mirroring vision.py's tolerance.

    Accepts a bare object, a ```json fenced block, or the first {...} found.
    Returns a dict (first element if the model emitted a list) or None.
    """
    if not text:
        return None
    for candidate in _json_candidates(text):
        try:
            obj = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, list):
            obj = obj[0] if obj else None
        if isinstance(obj, dict):
            return obj
    return None


def _json_candidates(text: str):
    yield text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if m:
        yield m.group(1)
    m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if m:
        yield m.group(1)


def _first(d: dict, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def norm_code(v) -> str:
    if v is None:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(v)).upper()


def norm_type(v) -> str:
    if v is None:
        return ""
    s = str(v).strip().lower()
    return TYPE_CANON.get(s, s)


# --------------------------------------------------------------------------- #
# Backends
# --------------------------------------------------------------------------- #
def call_vlm(image_bytes: bytes, base_url: str, model: str, api: str, timeout: int) -> str:
    """Return the raw model text for one image. Raises on transport error."""
    import requests  # lazy: dry-run needs no network

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    if api == "v1":
        url = base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": model,
            "temperature": 0.1,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }],
        }
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    # api == "ollama" native /api/chat
    url = base_url.rstrip("/") + "/api/chat"
    payload = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0.1},
        "messages": [{"role": "user", "content": PROMPT, "images": [b64]}],
    }
    r = requests.post(url, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()["message"]["content"]


def dry_call(entry: dict, miss: float, latency: float, rng: random.Random) -> tuple[str, float]:
    """Fabricate a plausible (text, latency) pair to validate the harness."""
    lat = max(0.1, rng.gauss(latency, latency * 0.2))
    code = entry.get("code")
    typ = entry.get("type")
    if code is not None and rng.random() < miss:      # simulate an OCR miss
        code = None
    if typ is not None and rng.random() < miss * 0.5:
        typ = None
    if rng.random() < 0.05:                             # simulate a broken-JSON reply
        return "sorry, I cannot read the code clearly", lat
    return json.dumps({"product_code": code, "type": typ, "quantity": 1}), lat


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def load_manifest(args) -> list[dict]:
    if args.dry_run and not args.manifest:
        return [{"file": f"synthetic_{i:02d}.jpg",
                 "code": f"#{i:02d}",
                 "type": ["colar", "brinco", "pulseira", "anel"][i % 4]}
                for i in range(1, args.dry_n + 1)]
    data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("items", [])
    return data[: args.limit] if args.limit else data


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, round((pct / 100.0) * (len(s) - 1))))
    return s[k]


def run(args) -> dict:
    rng = random.Random(args.seed)
    entries = load_manifest(args)
    if not entries:
        raise SystemExit("manifest is empty")

    images_dir = Path(args.images_dir) if args.images_dir else None
    rows, latencies = [], []
    # Serial baseline time = sum of the first burst-size per-image latencies
    # (concurrency 1). Robust across dry-run/real; excludes harness overhead.
    burst_latency = 0.0

    for i, entry in enumerate(entries, 1):
        fname = entry.get("file") or entry.get("filename")
        try:
            if args.dry_run:
                text, lat = dry_call(entry, args.dry_miss, args.dry_latency, rng)
            else:
                img = (images_dir / fname) if images_dir else Path(fname)
                data = img.read_bytes()
                t0 = time.perf_counter()
                text = call_vlm(data, args.base_url, args.model, args.api, args.timeout)
                lat = time.perf_counter() - t0
            err = None
        except Exception as e:                     # noqa: BLE001 - report, don't crash
            text, lat, err = "", 0.0, f"{type(e).__name__}: {e}"

        parsed = extract_json(text)
        pred_code = norm_code(_first(parsed, "product_code", "code", "product_model", "codigo")) if parsed else ""
        pred_type = norm_type(_first(parsed, "type", "category", "tipo", "categoria")) if parsed else ""
        exp_code = norm_code(entry.get("code"))
        exp_type = norm_type(entry.get("type"))

        rows.append({
            "file": fname,
            "latency_s": round(lat, 2),
            "json_ok": parsed is not None,
            "pred_code": pred_code, "exp_code": exp_code,
            "code_ok": bool(exp_code) and pred_code == exp_code,
            "pred_type": pred_type, "exp_type": exp_type,
            "type_ok": bool(exp_type) and pred_type == exp_type,
            "error": err,
        })
        if err is None:
            latencies.append(lat)
        if i <= args.burst_size:
            burst_latency += lat

    n = len(rows)
    coded = [r for r in rows if r["exp_code"]]
    typed = [r for r in rows if r["exp_type"]]
    summary = {
        "images": n,
        "errors": sum(1 for r in rows if r["error"]),
        "json_valid_rate": round(sum(r["json_ok"] for r in rows) / n, 3),
        "code_accuracy": round(sum(r["code_ok"] for r in coded) / len(coded), 3) if coded else None,
        "type_accuracy": round(sum(r["type_ok"] for r in typed) / len(typed), 3) if typed else None,
        "latency_p50": round(percentile(latencies, 50), 2),
        "latency_p95": round(percentile(latencies, 95), 2),
        "latency_mean": round(statistics.fmean(latencies), 2) if latencies else 0.0,
        "burst_size": min(args.burst_size, n),
        "burst_wall_s": round(burst_latency, 1),
        "sla_seconds": args.sla_seconds,
    }

    sla_ok = summary["burst_wall_s"] <= args.sla_seconds
    code_ok = summary["code_accuracy"] is None or summary["code_accuracy"] >= args.code_threshold
    type_ok = summary["type_accuracy"] is None or summary["type_accuracy"] >= args.type_threshold
    summary["sla_ok"] = sla_ok
    summary["accuracy_ok"] = code_ok and type_ok
    summary["verdict"] = "PASS" if (sla_ok and code_ok and type_ok) else "FAIL"

    reasons = []
    if not sla_ok:
        over = summary["burst_wall_s"] - args.sla_seconds
        reasons.append(f"SLA 超时 {over:.0f}s → 评估拼图 (2x2 vs 3x3) 作为回退")
    if not code_ok:
        reasons.append(f"货号准确率 {summary['code_accuracy']} < {args.code_threshold} → 先升模型档，别上拼图")
    if not type_ok:
        reasons.append(f"品类准确率 {summary['type_accuracy']} < {args.type_threshold} → 先升模型档")
    if not reasons:
        reasons.append("单图基线达标 → 按计划不引入拼图 (collage 不做)")
    summary["recommendation"] = "；".join(reasons)
    return {"summary": summary, "rows": rows}


def print_report(report: dict) -> None:
    s = report["summary"]
    print("\n" + "=" * 64)
    print("  P0 单图基线报告  (single-image baseline)")
    print("=" * 64)
    print(f"  images processed : {s['images']}  (errors: {s['errors']})")
    print(f"  JSON valid rate  : {s['json_valid_rate']*100:.1f}%")
    ca = "n/a" if s["code_accuracy"] is None else f"{s['code_accuracy']*100:.1f}%"
    ta = "n/a" if s["type_accuracy"] is None else f"{s['type_accuracy']*100:.1f}%"
    print(f"  货号 accuracy    : {ca}")
    print(f"  品类 accuracy    : {ta}")
    print(f"  latency  p50/p95 : {s['latency_p50']}s / {s['latency_p95']}s  (mean {s['latency_mean']}s)")
    print(f"  burst {s['burst_size']:>2} 串行   : {s['burst_wall_s']}s   vs SLA {s['sla_seconds']}s"
          f"  [{'OK' if s['sla_ok'] else 'OVER'}]")
    print("-" * 64)
    print(f"  VERDICT          : {s['verdict']}")
    print(f"  → {s['recommendation']}")
    print("=" * 64 + "\n")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="P0 single-image VLM baseline benchmark")
    p.add_argument("--manifest", help="JSON: [{file, code?, type?}, ...]")
    p.add_argument("--images-dir", help="dir holding the manifest's image files")
    p.add_argument("--base-url", default="http://localhost:11434/v1")
    p.add_argument("--model", default="qwen2.5vl:3b")
    p.add_argument("--api", choices=["v1", "ollama"], default="v1")
    p.add_argument("--burst-size", type=int, default=20)
    p.add_argument("--sla-seconds", type=float, default=180)
    p.add_argument("--code-threshold", type=float, default=0.90)
    p.add_argument("--type-threshold", type=float, default=0.90)
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--limit", type=int, default=0, help="cap images processed (0=all)")
    p.add_argument("--out", help="write full JSON report here")
    p.add_argument("--seed", type=int, default=0)
    # dry-run knobs (validate harness without a backend)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--dry-n", type=int, default=20, help="synthetic images when --dry-run")
    p.add_argument("--dry-miss", type=float, default=0.05, help="simulated OCR miss rate")
    p.add_argument("--dry-latency", type=float, default=6.0, help="simulated per-image seconds")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    report = run(args)
    print_report(report)
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  full report → {args.out}\n")
    return 0 if report["summary"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
