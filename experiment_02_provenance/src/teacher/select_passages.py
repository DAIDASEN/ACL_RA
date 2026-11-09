"""
Build a candidate pool of neutral literary passages from r/WritingPrompts.

Source : euclaise/WritingPrompts_preferences (Hugging Face, MIT license)
         fields: post_title, post_text, post_scores,
                 comment_texts[], comment_scores[], comment_times[]
Output : candidates.csv  (~200 rows by default, for manual review)
         candidates_all.csv (every passage that passed the automatic filters)

What it does
  1. keeps stories posted before 2022-11-30 (before ChatGPT's release)
  2. cleans Reddit markdown, drops bot/moderator comments and very short replies
  3. cuts a 150-300 word excerpt on paragraph boundaries
  4. rejects excerpts with cultural/identity markers:
       - named entities found by spaCy (people, places, nationalities, orgs, brands, events...)
       - a keyword list (holidays, religion, sports, US/UK-specific words, currencies)
       - English-only wordplay signals are left to manual review
  5. rejects obvious sci-fi/fantasy excerpts (aliens, magic, spaceships ...)
  6. rejects dialogue-heavy excerpts
  7. assigns quality tiers by upvotes (terciles) and samples evenly, max 1 story per prompt

Usage
  pip install datasets spacy pandas pyarrow
  python -m spacy download en_core_web_sm
  python select_passages.py                       # downloads (~1.4 GB) and runs on everything
  python select_passages.py --max-posts 20000     # quicker trial run
  python select_passages.py --parquet data/*.parquet   # if you downloaded the files yourself
"""
import argparse, glob, random, re
from datetime import datetime, timezone
import pandas as pd

CUTOFF = datetime(2022, 11, 30, tzinfo=timezone.utc)
MIN_WORDS, MAX_WORDS = 150, 300

# --- marker lists -------------------------------------------------------------
# spaCy entity labels that reveal origin / identity
BLOCK_ENTS = {"PERSON", "NORP", "GPE", "LOC", "FAC", "ORG", "EVENT",
              "PRODUCT", "WORK_OF_ART", "LANGUAGE", "LAW", "MONEY"}

CULTURE_WORDS = r"""
christmas thanksgiving halloween easter hanukkah ramadan diwali eid passover
church chapel mosque temple synagogue pastor priest rabbi imam bible quran
prayer pray amen jesus christ god allah buddha
baseball football soccer basketball hockey cricket rugby touchdown quarterback
dollar dollars bucks pound pounds quid euro euros cents
highway freeway interstate sidewalk subway apartment mall walmart starbucks
mcdonald diner prom sophomore freshman senior high-school college frat sorority
mom mommy y'all ain't gonna wanna gotta
""".split()

GENRE_WORDS = r"""
alien aliens spaceship starship spacecraft galaxy planet planets asteroid orbit
robot robots android cyborg laser warp
dragon dragons wizard wizards witch witches magic magical spell spells sorcerer
demon demons angel angels vampire vampires zombie zombies werewolf elf elves
dwarf dwarves orc orcs kingdom castle knight sword portal immortal immortality
superhero superpower superpowers villain reincarnated afterlife grim reaper satan
""".split()

CULTURE_RE = re.compile(r"\b(" + "|".join(map(re.escape, CULTURE_WORDS)) + r")\b", re.I)
GENRE_RE = re.compile(r"\b(" + "|".join(map(re.escape, GENRE_WORDS)) + r")\b", re.I)
BOT_RE = re.compile(r"(automoderator|welcome to the prompt|this comment has been removed|"
                    r"\[removed\]|\[deleted\]|off-topic|r/\w+|reddit|upvote|subscribe|"
                    r"part \d|edit:|thanks for reading|first time posting)", re.I)


# --- helpers -------------------------------------------------------------------
def parse_time(t):
    """comment_times may be unix seconds (str/int) or ISO strings."""
    if t is None:
        return None
    s = str(t).strip()
    try:
        return datetime.fromtimestamp(float(s), tz=timezone.utc)
    except ValueError:
        pass
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def clean_markdown(text):
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)        # [txt](link) -> txt
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_~^#>`]+", "", text)                      # emphasis, quotes, headers
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&nbsp;|&#x200B;", " ", text)
    text = re.sub(r"\n\s*[-=]{3,}\s*\n", "\n\n", text)          # horizontal rules
    return text.strip()


def paragraphs(text):
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    return [p for p in paras if p]


def excerpts(paras):
    """All windows of consecutive paragraphs with MIN..MAX words, ending on sentence punctuation."""
    out = []
    for i in range(len(paras)):
        words = 0
        for j in range(i, len(paras)):
            words += len(paras[j].split())
            if words > MAX_WORDS:
                break
            if words >= MIN_WORDS and re.search(r"[.!?…\"”']$", paras[j]):
                out.append(("\n\n".join(paras[i:j + 1]), words))
    return out


def dialogue_ratio(text):
    quoted = sum(len(m.split()) for m in re.findall(r"[\"“]([^\"”]+)[\"”]", text))
    return quoted / max(1, len(text.split()))


def check_text(nlp, text):
    """Return a list of reasons to reject (empty list = keep)."""
    reasons = []
    if CULTURE_RE.search(text):
        reasons.append("culture_word:" + CULTURE_RE.search(text).group(0).lower())
    if GENRE_RE.search(text):
        reasons.append("genre_word:" + GENRE_RE.search(text).group(0).lower())
    if dialogue_ratio(text) > 0.35:
        reasons.append("dialogue_heavy")
    if not reasons:  # spaCy is the slow step, run it last
        ents = [(e.text, e.label_) for e in nlp(text).ents if e.label_ in BLOCK_ENTS]
        if ents:
            reasons.append("entity:" + "|".join(f"{t}/{l}" for t, l in ents[:3]))
    return reasons


# --- data loading --------------------------------------------------------------
def iter_posts(args):
    if args.parquet:
        files = sorted(f for p in args.parquet for f in glob.glob(p))
        for f in files:
            for row in pd.read_parquet(f).to_dict("records"):
                yield row
    else:
        from datasets import load_dataset
        ds = load_dataset("euclaise/WritingPrompts_preferences", split="train", streaming=True)
        for row in ds:
            yield row


# --- main ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", nargs="*", help="local parquet files instead of downloading")
    ap.add_argument("--max-posts", type=int, default=None, help="stop after N prompts (trial runs)")
    ap.add_argument("--min-score", type=int, default=2, help="ignore stories with fewer upvotes")
    ap.add_argument("--n", type=int, default=200, help="size of the final candidate sample")
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()

    import spacy
    nlp = spacy.load("en_core_web_sm", disable=["lemmatizer"])
    random.seed(args.seed)

    kept, stats = [], {"posts": 0, "stories": 0, "too_late": 0, "bot_or_short": 0,
                       "no_window": 0, "rejected_markers": 0, "kept": 0}
    for p_idx, post in enumerate(iter_posts(args)):
        if args.max_posts and p_idx >= args.max_posts:
            break
        stats["posts"] += 1
        title = post.get("post_title") or ""
        if not title.upper().startswith(("[WP]", "[SP]", "[EU]", "[CW]", "[TT]")):
            continue
        for k, (text, score, t) in enumerate(zip(post["comment_texts"],
                                                  post["comment_scores"],
                                                  post["comment_times"])):
            stats["stories"] += 1
            when = parse_time(t)
            if when is None or when >= CUTOFF:
                stats["too_late"] += 1
                continue
            if score is None or score < args.min_score or not text or BOT_RE.search(text) \
                    or len(text.split()) < MIN_WORDS:
                stats["bot_or_short"] += 1
                continue
            windows = excerpts(paragraphs(clean_markdown(text)))
            if not windows:
                stats["no_window"] += 1
                continue
            # try windows in random order, keep the first clean one
            random.shuffle(windows)
            chosen = None
            for exc, wc in windows[:6]:
                if not check_text(nlp, exc):
                    chosen = (exc, wc)
                    break
            if not chosen:
                stats["rejected_markers"] += 1
                continue
            stats["kept"] += 1
            kept.append(dict(story_id=f"p{p_idx}_c{k}", prompt_id=f"p{p_idx}",
                             prompt_title=title, upvotes=int(score),
                             posted=when.date().isoformat(), words=chosen[1],
                             passage=chosen[0]))

    print("filter stats:", stats)
    if not kept:
        print("nothing kept - check the data / loosen filters")
        return
    df = pd.DataFrame(kept)
    # quality tiers by upvote terciles (only to spread quality, not a quality measure)
    df["tier"] = pd.qcut(df.upvotes.rank(method="first"), 3, labels=["low", "mid", "high"])
    df.to_csv("candidates_all.csv", index=False)

    # sample evenly per tier, at most one story per prompt
    df = df.sample(frac=1, random_state=args.seed).drop_duplicates("prompt_id")
    per_tier = args.n // 3
    sample = pd.concat([df[df.tier == t].head(per_tier) for t in ["high", "mid", "low"]])
    sample = sample.assign(passage_id=[f"P{i:03d}" for i in range(len(sample))])
    # empty columns for the manual checks
    for col in ["keep_manual", "neutralized_edits", "plausibility_ok", "probe_recognized", "notes"]:
        sample[col] = ""
    cols = ["passage_id", "tier", "upvotes", "posted", "words", "prompt_title", "story_id",
            "passage", "keep_manual", "neutralized_edits", "plausibility_ok",
            "probe_recognized", "notes"]
    sample[cols].to_csv("candidates.csv", index=False)
    print(f"candidates_all.csv: {len(df)} unique-prompt passages; "
          f"candidates.csv: {len(sample)} sampled "
          f"({sample.tier.value_counts().to_dict()})")


if __name__ == "__main__":
    main()
