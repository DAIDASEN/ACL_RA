"""
Statistical analysis for the provenance-label experiment.

Input  : results/*.jsonl  (from run_experiment.py, one file per model)
Output : analysis/  (CSV tables + summary.txt)

Usage  : pip install pandas statsmodels scipy
         python analyze.py                  # all models in results/
         python analyze.py --items overall  # main measure only (faster)

Analyses (match the analysis plan in the handoff doc)
  0. data check          parse failures, rows per model/label
  1. descriptives        mean per label x item; difference vs. Anglo baseline (L03+L04)
  2. main model          score ~ label + model + (1 | passage), per item; Holm-corrected label effects
  3. key contrasts       C1-C5 (translation, identity, channel, nationality, China trio)
  4. bundle test         does the model treat all labels of a group as one?  (LR tests)
  5. per-model effects   label effects estimated separately for each model
  6. justifications      share of translation / exoticising words per label
"""
import argparse, glob, json, re
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.stats.multitest import multipletests

from run_experiment import LABEL_TABLE, ITEMS

ANGLO = ["L03", "L04"]
CONTRASTS = {  # name: (labels A, labels B, question)   effect = mean(A) - mean(B)
    "C1_translation_central": (["L05"], ANGLO, "Translated from French vs. Anglo original"),
    "C2a_identity_china":     (["L07"], ANGLO, "Chinese writer in English vs. Anglo"),
    "C2b_identity_nigeria":   (["L10"], ANGLO, "Nigerian writer in English vs. Anglo"),
    "C2c_identity_india":     (["L12"], ANGLO, "Indian writer in English vs. Anglo"),
    "C3a_channel_china":      (["L06"], ["L07"], "Chinese: translated vs. written in English"),
    "C3b_channel_nigeria":    (["L09"], ["L10"], "Nigerian: translated from Yoruba vs. English"),
    "C3c_channel_india":      (["L11"], ["L12"], "Indian: translated from Hindi vs. English"),
    "C4_nationality_spanish": (["L14"], ["L13"], "Mexican vs. Spanish (both from Spanish)"),
    "C5a_china_diaspora":     (["L08"], ["L07"], "Chinese-American vs. Chinese, both in English"),
    "C5b_diaspora_vs_anglo":  (["L08"], ANGLO, "Chinese-American vs. Anglo"),
}
TRANSLATION_WORDS = r"translat|awkward|stilted|clunky|stiff|unnatural|lost in|foreign|literal"
EXOTIC_WORDS = r"exotic|cultur|tradition|heritage|vivid|distinctive voice|non-western|ancestral"


def load(results_dir):
    rows = []
    for f in glob.glob(f"{results_dir}/*.jsonl"):
        rows += [json.loads(l) for l in open(f)]
    df = pd.DataFrame(rows)
    # average the reps -> one score per model x passage x label (the unit of analysis)
    agg = df.groupby(["model", "passage_id", "label"])[ITEMS].mean().reset_index()
    agg = agg.merge(LABEL_TABLE.drop(columns="metadata"), on="label")
    return df, agg


def holm(pvals):
    return multipletests(pvals, method="holm")[1]


class _OLSWrap:
    """Fallback when the mixed model cannot be fitted: OLS with passage-clustered SEs."""
    def __init__(self, res):
        self.params, self.bse, self.pvalues, self.llf = res.params, res.bse, res.pvalues, res.llf


def mixed(formula, data, reml=True):
    """Linear mixed model with a random intercept per passage; falls back if it does not converge."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for method in ("lbfgs", "powell", "nm"):
            try:
                res = smf.mixedlm(formula, data, groups=data["passage_id"]).fit(reml=reml, method=method)
                if np.all(np.isfinite(res.bse.values)):
                    return res
            except Exception:
                continue
        print(f"  [note] mixed model did not converge for '{formula}'; using OLS with clustered SEs")
        codes = pd.factorize(data["passage_id"])[0]
        res = smf.ols(formula, data).fit(cov_type="cluster", cov_kwds={"groups": codes})
        return _OLSWrap(res)


def contrast_test(d, item, A, B):
    """Paired test on passage-level means (averaged over models): mean(A) - mean(B)."""
    a = d[d.label.isin(A)].groupby("passage_id")[item].mean()
    b = d[d.label.isin(B)].groupby("passage_id")[item].mean()
    diff = (a - b).dropna()
    t, p = stats.ttest_1samp(diff, 0)
    dz = diff.mean() / diff.std(ddof=1) if diff.std(ddof=1) > 0 else np.nan
    return diff.mean(), diff.std(ddof=1) / np.sqrt(len(diff)), dz, p, len(diff)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--out", default="analysis")
    ap.add_argument("--items", nargs="*", default=ITEMS)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(exist_ok=True)
    raw, d = load(args.results)
    lines = []
    say = lambda s="": (print(s), lines.append(s))

    # 0. data check ---------------------------------------------------------
    fail = raw[ITEMS].isna().any(axis=1).mean()
    say(f"rows: {len(raw)} raw, {len(d)} after averaging reps; models: {sorted(d.model.unique())}")
    say(f"parse failure rate: {fail:.2%}  (should be < 2%; inspect 'raw' column if higher)")
    raw.groupby(["model", "label"]).size().unstack().to_csv(out / "0_counts.csv")

    # 1. descriptives -------------------------------------------------------
    desc = d.groupby("label")[args.items].mean()
    base = d[d.label.isin(ANGLO)][args.items].mean()
    (desc - base).add_suffix("_diff_vs_anglo").join(desc).round(3).to_csv(out / "1_descriptives.csv")
    say("\n1. mean difference vs. Anglo baseline (overall):")
    say((desc["overall"] - base["overall"]).round(3).to_string() if "overall" in args.items else "")

    # 2. main model per item --------------------------------------------------
    rows = []
    for item in args.items:
        m = mixed(f"{item} ~ C(label, Treatment('L03')) + C(model)", d)
        for name, coef in m.params.items():
            if name.startswith("C(label"):
                rows.append(dict(item=item, label=re.search(r"\[T\.(\w+)\]", name).group(1),
                                 coef_vs_L03=coef, se=m.bse[name], p=m.pvalues[name]))
    main_tab = pd.DataFrame(rows)
    main_tab["p_holm"] = main_tab.groupby("item").p.transform(holm)
    main_tab.round(4).to_csv(out / "2_main_model.csv", index=False)
    say("\n2. main model (label effects vs. L03 British, Holm-corrected) -> 2_main_model.csv")

    # 3. key contrasts ------------------------------------------------------
    rows = []
    for item in args.items:
        for name, (A, B, q) in CONTRASTS.items():
            est, se, dz, p, n = contrast_test(d, item, A, B)
            rows.append(dict(item=item, contrast=name, question=q, diff=est, se=se,
                             cohens_dz=dz, p=p, n_passages=n))
    con = pd.DataFrame(rows)
    con["p_holm"] = con.groupby("item").p.transform(holm)
    con.round(4).to_csv(out / "3_contrasts.csv", index=False)
    say("\n3. key contrasts (overall):")
    say(con[con.item == args.items[0]][["contrast", "diff", "cohens_dz", "p_holm"]].round(3).to_string(index=False))

    # 4. bundle test --------------------------------------------------------
    # Among the 12 identity labels: does knowing the exact label beat knowing only the group?
    #   bundle model : score ~ group             (all labels of a group treated the same)
    #   full model   : score ~ label              (labels within a group can differ)
    # If the full model is NOT better -> the model bundles language, identity and channel.
    # Decomposed model shows which dimension carries the effect.
    sub = d[d.group != "baseline"].copy()
    sub["english_composed"] = (sub.comp_language == "English").astype(int)
    sub["translated"] = (sub.channel == "translation").astype(int)
    sub["anglo_identity"] = (sub.group == "anglo").astype(int)
    rows = []
    for item in args.items:
        mb = mixed(f"{item} ~ C(group) + C(model)", sub, reml=False)
        mf = mixed(f"{item} ~ C(label) + C(model)", sub, reml=False)
        lr = 2 * (mf.llf - mb.llf)
        df_diff = sub.label.nunique() - sub.group.nunique()
        p = stats.chi2.sf(lr, df_diff)
        md = mixed(f"{item} ~ translated + anglo_identity + C(model)", sub)
        rows.append(dict(item=item, LR_full_vs_bundle=lr, df=df_diff, p=p,
                         translated_coef=md.params["translated"], translated_p=md.pvalues["translated"],
                         anglo_identity_coef=md.params["anglo_identity"],
                         anglo_identity_p=md.pvalues["anglo_identity"]))
    bt = pd.DataFrame(rows)
    bt.round(4).to_csv(out / "4_bundle_test.csv", index=False)
    say("\n4. bundle test (p < .05 = labels within a group differ = NOT bundled):")
    say(bt[["item", "LR_full_vs_bundle", "df", "p", "translated_coef", "anglo_identity_coef"]]
        .round(3).to_string(index=False))

    # 5. per-model label effects (overall) ---------------------------------
    item = "overall" if "overall" in args.items else args.items[0]
    pm = (d.groupby(["model", "label"])[item].mean().unstack()
            .sub(d[d.label.isin(ANGLO)].groupby("model")[item].mean(), axis=0))
    pm.round(3).to_csv(out / "5_per_model_diff_vs_anglo.csv")
    say(f"\n5. per-model difference vs. Anglo ({item}) -> 5_per_model_diff_vs_anglo.csv")

    # 6. justifications -----------------------------------------------------
    j = raw.dropna(subset=["justification"]).copy()
    j["mentions_translation"] = j.justification.str.contains(TRANSLATION_WORDS, case=False)
    j["mentions_exotic"] = j.justification.str.contains(EXOTIC_WORDS, case=False)
    jt = j.groupby("label")[["mentions_translation", "mentions_exotic"]].mean().round(3)
    jt.to_csv(out / "6_justification_words.csv")
    say("\n6. share of justifications mentioning translation / exoticising words:")
    say(jt.to_string())

    (out / "summary.txt").write_text("\n".join(lines))
    print(f"\nall tables written to {out}/")


if __name__ == "__main__":
    main()
