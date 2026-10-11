"""Score speech-to-text on your own recordings with word error rate (WER). Lower is better.

Put clips in eval/voice/ and list them in eval/voice/manifest.csv with columns: file,lang,reference
  (lang = en or hinglish; reference = exactly what you said, typed in the script you'd want back)

  python eval/stt_eval.py --whisper small,medium     # local faster-whisper (pip install faster-whisper)
  python eval/stt_eval.py --hyp-csv wispr.csv        # score transcripts from another tool, e.g. Wispr Flow
                                                     # columns: file,hypothesis  (system name = file stem)
"""
import argparse
import csv
import re
import statistics
import time
from pathlib import Path

HERE = Path(__file__).parent
VOICE = HERE / "voice"


def words(text):
    return re.findall(r"\w+", text.lower())


def wer(reference, hypothesis):
    ref, hyp = words(reference), words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1] / len(ref)


def load_manifest():
    with (VOICE / "manifest.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def whisper_hyps(size, clips):
    from faster_whisper import WhisperModel  # imported here so --hyp-csv works without it
    model = WhisperModel(size, device="auto", compute_type="int8")
    out = {}
    for c in clips:
        start = time.time()
        segments, _ = model.transcribe(str(VOICE / c["file"]))
        out[c["file"]] = (" ".join(s.text for s in segments).strip(), round(time.time() - start, 2))
    return out


def score(system, clips, hyps):
    rows = []
    for c in clips:
        hyp, secs = hyps.get(c["file"], ("", None))
        rows.append({"system": system, "file": c["file"], "lang": c["lang"],
                     "wer": round(wer(c["reference"], hyp), 3), "seconds": secs,
                     "reference": c["reference"], "hypothesis": hyp})
    return rows


def summary(rows):
    lines = ["| System | Language | Clips | Mean WER |", "| --- | --- | --- | --- |"]
    for system in sorted({r["system"] for r in rows}):
        for lang in sorted({r["lang"] for r in rows}):
            sel = [r["wer"] for r in rows if r["system"] == system and r["lang"] == lang]
            if sel:
                lines.append(f"| {system} | {lang} | {len(sel)} | {statistics.mean(sel):.1%} |")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--whisper", help="comma-separated faster-whisper sizes, e.g. small,medium")
    ap.add_argument("--hyp-csv", action="append", default=[], help="external transcripts CSV (repeatable)")
    a = ap.parse_args()
    clips = load_manifest()
    rows = []
    for size in filter(None, (a.whisper or "").split(",")):
        rows += score(f"whisper-{size}", clips, whisper_hyps(size, clips))
    for path in a.hyp_csv:
        with open(path, encoding="utf-8") as f:
            hyps = {r["file"]: (r["hypothesis"], None) for r in csv.DictReader(f)}
        rows += score(Path(path).stem, clips, hyps)
    if not rows:
        raise SystemExit("Nothing to score: pass --whisper and/or --hyp-csv.")
    out = HERE / "results" / f"stt-{time.strftime('%Y%m%d-%H%M%S')}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Saved {out}\n\n{summary(rows)}")
