"""
Run the provenance-label experiment.

Same English passage, 14 provenance labels; the model rates 6 items on 1-7 (no definitions, CAT style).
Scales: literariness + overall quality (Koolen et al. 2020); creativity, writing ability, enjoyment
(Kaufman et al. 2010); naturalness of the English prose (adapted from translation-studies fluency).

Input  : final_passages.csv   columns: passage_id, passage
Output : results/<model>.jsonl   one line per (passage, label, rep); the script resumes where it stopped

Usage (one model per run; any OpenAI-compatible endpoint):
  export OPENAI_API_KEY=...            # or another env var, see --api-key-env
  python run_experiment.py --model gpt-4o
  python run_experiment.py --model qwen-max --base-url https://dashscope.aliyuncs.com/compatible-mode/v1 \
                           --api-key-env DASHSCOPE_API_KEY
  # pilot: 20 passages, 6 labels, 1 rep
  python run_experiment.py --model gpt-4o --n-passages 20 --labels L01 L03 L05 L06 L07 L10 --reps 1
  # offline dry run (random scores)
  python run_experiment.py --model mock --mock
"""
import argparse, json, os, random, re, time
from pathlib import Path
import pandas as pd

# ---------------------------------------------------------------------------
# 14 labels. Each is coded on three dimensions for the analysis.
#   identity      : who the author is
#   comp_language : language the work was written in
#   channel       : original (written in English) vs translation
# ---------------------------------------------------------------------------
def meta(identity, language, translated):
    this = "an English translation" if translated else "the original English text"
    return f"Author: {identity}\nOriginal language: {language}\nThis text: {this}"

LABELS = [
    # id    group        identity            comp_language  channel        metadata block
    ("L01", "baseline",  None,               None,          None,          None),
    ("L02", "baseline",  None,               None,          None,          "First published: 2019"),
    ("L03", "anglo",     "British",          "English",     "original",    meta("a British writer", "English", False)),
    ("L04", "anglo",     "American",         "English",     "original",    meta("an American writer", "English", False)),
    ("L05", "france",    "French",           "French",      "translation", meta("a French writer", "French", True)),
    ("L06", "china",     "Chinese",          "Chinese",     "translation", meta("a Chinese writer", "Chinese", True)),
    ("L07", "china",     "Chinese",          "English",     "original",    meta("a Chinese writer", "English", False)),
    ("L08", "china",     "Chinese-American", "English",     "original",    meta("a Chinese-American writer", "English", False)),
    ("L09", "nigeria",   "Nigerian",         "Yoruba",      "translation", meta("a Nigerian writer", "Yoruba", True)),
    ("L10", "nigeria",   "Nigerian",         "English",     "original",    meta("a Nigerian writer", "English", False)),
    ("L11", "india",     "Indian",           "Hindi",       "translation", meta("an Indian writer", "Hindi", True)),
    ("L12", "india",     "Indian",           "English",     "original",    meta("an Indian writer", "English", False)),
    ("L13", "hispanic",  "Spanish",          "Spanish",     "translation", meta("a Spanish writer", "Spanish", True)),
    ("L14", "hispanic",  "Mexican",          "Spanish",     "translation", meta("a Mexican writer", "Spanish", True)),
]
LABEL_TABLE = pd.DataFrame(LABELS, columns=["label", "group", "identity", "comp_language",
                                            "channel", "metadata"])
ITEMS = ["literariness", "overall", "creativity", "writing", "enjoyment", "naturalness"]

PROMPT = """{meta_block}<passage>
{passage}
</passage>

Rate this passage on each of the following, from 1 (lowest) to 7 (highest):
literariness, overall quality, creativity, writing ability, enjoyment, naturalness of the English prose.
Then give a one-sentence justification.

Respond with JSON only:
{{"literariness": , "overall": , "creativity": , "writing": , "enjoyment": , "naturalness": , "justification": ""}}"""


def build_prompt(label_id, passage):
    m = LABEL_TABLE.set_index("label").loc[label_id, "metadata"]
    block = f"{m}\n\n" if isinstance(m, str) and m else ""
    return PROMPT.format(meta_block=block, passage=passage.strip())


def parse(text):
    """Return dict of item scores (int 1-7 or None) + justification."""
    out = {k: None for k in ITEMS}
    out["justification"] = ""
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            for k in ITEMS:
                v = d.get(k)
                if isinstance(v, (int, float)) and 1 <= v <= 7:
                    out[k] = int(round(v))
            out["justification"] = str(d.get("justification", ""))
            return out
        except Exception:
            pass
    for k in ITEMS:  # fallback: regex per key
        s = re.search(rf'"{k}"\s*:\s*(\d)', text or "")
        if s and 1 <= int(s.group(1)) <= 7:
            out[k] = int(s.group(1))
    return out


def call_model(client, args, prompt):
    if args.mock:
        return json.dumps({**{k: random.randint(3, 6) for k in ITEMS}, "justification": "mock"})
    for attempt in range(5):  # simple retry with backoff
        try:
            r = client.chat.completions.create(
                model=args.model, temperature=args.temperature, max_tokens=300,
                messages=[{"role": "user", "content": prompt}])
            return r.choices[0].message.content
        except Exception as e:
            wait = 2 ** attempt
            print(f"  API error ({e.__class__.__name__}); retry in {wait}s")
            time.sleep(wait)
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--passages", default="final_passages.csv")
    ap.add_argument("--model", required=True)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--api-key-env", default="OPENAI_API_KEY")
    ap.add_argument("--labels", nargs="*", default=None, help="subset of label ids (default: all 14)")
    ap.add_argument("--n-passages", type=int, default=None, help="use only the first N passages")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--outdir", default="results")
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()

    passages = pd.read_csv(args.passages)
    if args.n_passages:
        passages = passages.head(args.n_passages)
    labels = args.labels or LABEL_TABLE.label.tolist()

    client = None
    if not args.mock:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ[args.api_key_env], base_url=args.base_url)

    out_path = Path(args.outdir) / f"{args.model.replace('/', '_')}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_path.exists():  # resume
        for line in out_path.open():
            r = json.loads(line)
            done.add((r["passage_id"], r["label"], r["rep"]))

    jobs = [(p.passage_id, p.passage, l, rep) for p in passages.itertuples()
            for l in labels for rep in range(args.reps)]
    random.Random(0).shuffle(jobs)  # spread labels over time (API drift)
    todo = [j for j in jobs if (j[0], j[2], j[3]) not in done]
    print(f"{len(jobs)} jobs, {len(todo)} to run -> {out_path}")

    with out_path.open("a") as f:
        for i, (pid, text, label, rep) in enumerate(todo, 1):
            raw = call_model(client, args, build_prompt(label, text))
            rec = {"model": args.model, "passage_id": pid, "label": label, "rep": rep,
                   **parse(raw), "raw": raw}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if i % 100 == 0:
                print(f"  {i}/{len(todo)}")
    print("done")


if __name__ == "__main__":
    main()
