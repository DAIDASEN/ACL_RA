"""
Memorization check for passages without title/author (e.g. Reddit stories).

Prefix probing (Carlini et al. 2023; also used in OWL, Srivastava et al. 2025):
show the model the first ~60% of a passage, ask it to continue, and check whether the
continuation reproduces the real remainder.

A passage is flagged as "memorized" if the continuation shares any run of >= 10 consecutive
words with the true remainder (verbatim recall), or a word-level LCS ratio >= 0.5.

Input  : final_passages.csv (or candidates.csv)  columns: passage_id, passage
Output : memorization.csv   one row per passage x model, with a `memorized` flag

Usage  : python probe_memorization.py --passages candidates.csv --model gpt-4o
         python probe_memorization.py --passages candidates.csv --model mock --mock
"""
import argparse, os, re
import pandas as pd

PROMPT = """Continue the following passage exactly as it continues in its original source. \
If you do not know the original, continue it as best you can.

{prefix}"""

NGRAM = 10


def words(s):
    return re.findall(r"[a-z0-9']+", s.lower())


def longest_shared_run(a, b):
    """Length of the longest run of consecutive words shared by word lists a and b."""
    best, prev = 0, [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def lcs_ratio(a, b):
    if not a or not b:
        return 0.0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[-1]))
        prev = cur
    return prev[-1] / len(b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--passages", default="final_passages.csv")
    ap.add_argument("--model", required=True)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--api-key-env", default="OPENAI_API_KEY")
    ap.add_argument("--prefix-share", type=float, default=0.6)
    ap.add_argument("--out", default="memorization.csv")
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()

    df = pd.read_csv(args.passages)
    client = None
    if not args.mock:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ[args.api_key_env], base_url=args.base_url)

    rows = []
    for p in df.itertuples():
        toks = p.passage.split()
        cut = int(len(toks) * args.prefix_share)
        prefix, truth = " ".join(toks[:cut]), " ".join(toks[cut:])
        if args.mock:
            cont = "The weather turned and she walked home slowly."
        else:
            r = client.chat.completions.create(
                model=args.model, temperature=0, max_tokens=300,
                messages=[{"role": "user", "content": PROMPT.format(prefix=prefix)}])
            cont = r.choices[0].message.content or ""
        a, b = words(cont), words(truth)
        run, ratio = longest_shared_run(a, b), lcs_ratio(a, b)
        rows.append(dict(passage_id=p.passage_id, model=args.model, longest_shared_run=run,
                         lcs_ratio=round(ratio, 3), memorized=(run >= NGRAM or ratio >= 0.5),
                         continuation=cont))
    res = pd.DataFrame(rows)
    # append so several models can be checked into one file
    header = not os.path.exists(args.out)
    res.to_csv(args.out, mode="a", header=header, index=False)
    print(f"{args.model}: {res.memorized.sum()} of {len(res)} passages flagged as memorized -> {args.out}")


if __name__ == "__main__":
    main()
