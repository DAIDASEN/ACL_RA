"""Basic plot-distance summaries for ONE model x country x wording cell.

Inputs are already quality-filtered story records with story_id, genre and vector.
This module does not implement extraction, embedding, bootstrap or inference.
"""
import itertools
import math
from collections import Counter
from statistics import mean

TYPED = ('romance', 'horror', 'science fiction', 'crime', 'comedy')


def cosine_distance(a, b):
    if len(a) != len(b) or not a:
        raise ValueError('vectors must have the same nonzero dimension')
    if not all(math.isfinite(x) for x in (*a, *b)):
        raise ValueError('vectors must be finite')
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        raise ValueError('zero vector')
    similarity = sum(x * y for x, y in zip(a, b)) / na / nb
    return 1 - max(-1.0, min(1.0, similarity))


def combine(d_open, d_within, d_between):
    typed = 0.2 * d_within + 0.8 * d_between
    return dict(D_open=d_open, D_within=d_within, D_between=d_between,
                D_typed=typed, Delta=typed - d_open, Separation=d_between - d_within)


def pair_mean(left, right=None):
    pairs = itertools.combinations(left, 2) if right is None else itertools.product(left, right)
    # A repeated draw of one original story never forms a self-pair.
    distances = [cosine_distance(a['vector'], b['vector']) for a, b in pairs
                 if a['story_id'] != b['story_id']]
    return mean(distances) if distances else None


def summarize(records):
    """Conservative missing-cell policy; do not pool models/countries/wordings."""
    for field in ('model', 'country', 'wording'):
        values = {r.get(field) for r in records}
        if len(values) > 1:
            raise ValueError(f'input must be one {field} cell')
    allowed = ('OPEN',) + TYPED
    if any(r['genre'] not in allowed for r in records):
        raise ValueError('unknown genre')
    # Repeated IDs are ambiguous in the ordinary summary API. A future bootstrap
    # implementation must explicitly manage resampling multiplicities separately.
    ids = [r['story_id'] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate story_id; summarize expects independent original requests')
    counts = Counter(r['genre'] for r in records)
    missing = [genre for genre in allowed if counts[genre] < 2]
    result = dict(n={g: counts[g] for g in allowed}, missing_genres=missing)
    if missing:
        return {**result, **{k: None for k in
                ('D_open', 'D_within', 'D_between', 'D_typed', 'Delta', 'Separation')}}
    groups = {genre: [r for r in records if r['genre'] == genre] for genre in allowed}
    d_open = pair_mean(groups['OPEN'])
    d_within = mean(pair_mean(groups[g]) for g in TYPED)
    d_between = mean(pair_mean(groups[a], groups[b]) for a, b in itertools.combinations(TYPED, 2))
    return {**result, **combine(d_open, d_within, d_between)}
