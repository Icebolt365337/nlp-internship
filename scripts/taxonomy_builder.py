import json
import os
import re
from collections import Counter

import pandas as pd
import pytest

from taxonomy_data import TAXONOMY


def build_terms(taxonomy=TAXONOMY):
    terms = []
    i = 0
    for category, words in taxonomy.items():
        for term in words:
            terms.append({"id": i, "term": term, "category": category})
            i += 1
    return terms


def save_taxonomy_json(path="data/processed/taxonomy.json", taxonomy=TAXONOMY):
    terms = build_terms(taxonomy)
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    with open(path, "w") as f:
        json.dump({"categories": taxonomy, "terms": terms}, f, indent=2)
    return terms


_DEFAULT_STOPWORDS = {
    'a', 'an', 'the', 'and', 'or', 'of', 'to', 'in', 'on', 'at', 'is', 'it',
    'for', 'this', 'that', 'with', 'as', 'by', 'be', 'has', 'have', 'was',
    'are', 'from', 'you', 'your', 'each', 'plus', 'over', 'per', 'off',
    'out', 'up', 'so', 'no', 'not', 'one', 'two', 'three', 'four', 'five',
    'home', 'house', 'property', 'listing', 'located', 'features',
}


def find_matches(text, terms):
    text_lower = str(text).lower()
    return [term for term in terms if re.search(r'\b' + re.escape(term) + r's?\b', text_lower)]


def find_match_spans(text_lower, terms):
    spans = []
    for term in terms:
        for m in re.finditer(r'\b' + re.escape(term) + r's?\b', text_lower):
            spans.append((m.start(), m.end()))
    return spans


def merge_spans(spans):
    if not spans:
        return []
    spans = sorted(spans)
    merged = [spans[0]]
    for start, end in spans[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def _alpha_len(s):
    return len(re.findall(r'[a-zA-Z]', s))


def compute_coverage(df, column, terms):
    non_null = df[column].dropna().astype(str)

    listings_with_match = 0
    total_letters = 0
    covered_letters = 0

    for text in non_null:
        text_lower = text.lower()
        merged = merge_spans(find_match_spans(text_lower, terms))
        if merged:
            listings_with_match += 1
        covered_letters += sum(_alpha_len(text_lower[start:end]) for start, end in merged)
        total_letters += _alpha_len(text_lower)

    return {
        "total_listings": len(non_null),
        "listings_with_taxonomy_match": listings_with_match,
        "listing_coverage": listings_with_match / len(non_null) if len(non_null) else 0.0,
        "span_coverage": covered_letters / total_letters if total_letters else 0.0,
    }


def find_uncovered_terms(df, column, terms, top_k=30, stopwords=_DEFAULT_STOPWORDS):
    non_null = df[column].dropna().astype(str)
    counter = Counter()

    for text in non_null:
        text_lower = text.lower()
        merged = merge_spans(find_match_spans(text_lower, terms))
        covered = [False] * len(text_lower)
        for start, end in merged:
            for i in range(start, end):
                covered[i] = True
        for m in re.finditer(r"[a-zA-Z']+", text_lower):
            word = m.group()
            if len(word) <= 2 or word in stopwords:
                continue
            if not all(covered[m.start():m.end()]):
                counter[word] += 1

    return counter.most_common(top_k)


def find_word_context(df, column, word, terms, top_k=15):
    non_null = df[column].dropna().astype(str)
    before, after = Counter(), Counter()

    for text in non_null:
        text_lower = text.lower()
        merged = merge_spans(find_match_spans(text_lower, terms))
        covered = [False] * len(text_lower)
        for start, end in merged:
            for i in range(start, end):
                covered[i] = True

        tokens = list(re.finditer(r"[a-zA-Z']+", text_lower))
        for i, m in enumerate(tokens):
            if m.group() != word.lower():
                continue
            if all(covered[m.start():m.end()]):
                continue  # already covered by an existing match -- skip
            if i > 0:
                before[tokens[i - 1].group()] += 1
            if i < len(tokens) - 1:
                after[tokens[i + 1].group()] += 1

    return {"before": before.most_common(top_k), "after": after.most_common(top_k)}


def compute_category_coverage(df, column, categories):
    non_null = df[column].dropna().astype(str)
    results = {}
    for category, terms in categories.items():
        hits = sum(1 for text in non_null if find_matches(text, terms))
        results[category] = hits / len(non_null) if len(non_null) else 0.0
    return results


CSV_PATH = "data/processed/listing_sample.csv"
REMARKS_COLUMN = "remarks"


def load_user_csv(csv_path=None, column=None):
    csv_path = csv_path or CSV_PATH
    column = column or REMARKS_COLUMN
    if not os.path.exists(csv_path):
        return None, None
    df = pd.read_csv(csv_path)
    if column not in df.columns:
        raise ValueError(
            f"Column '{column}' not found in {csv_path}. "
            f"Available columns: {list(df.columns)}. "
            f"Set REMARKS_COLUMN to override."
        )
    return df, column


TARGET_COVERAGE = 0.30


def test_taxonomy_has_at_least_8_categories():
    assert len(TAXONOMY) >= 8


def test_taxonomy_has_at_least_200_terms():
    assert len(build_terms(TAXONOMY)) >= 200


def test_no_duplicate_terms_within_taxonomy():
    all_terms = [term for terms in TAXONOMY.values() for term in terms]
    assert len(all_terms) == len(set(all_terms)), "duplicate term found across categories"


def test_every_category_has_at_least_10_terms():
    for category, terms in TAXONOMY.items():
        assert len(terms) >= 10, f"{category} has only {len(terms)} terms"


def test_no_empty_or_whitespace_terms():
    for terms in TAXONOMY.values():
        for term in terms:
            assert term.strip() == term
            assert len(term) > 0


def test_coverage_on_user_csv_meets_target():
    df, column = load_user_csv()
    if df is None:
        pytest.skip(
            f"No file found at CSV_PATH ('{CSV_PATH}'). Edit CSV_PATH near the top "
            f"of taxonomy.py to point at your real listing CSV."
        )
    terms = [t["term"] for t in build_terms(TAXONOMY)]
    result = compute_coverage(df, column, terms)
    assert result["listing_coverage"] >= TARGET_COVERAGE, (
        f"Only {result['listing_coverage']:.1%} coverage on {CSV_PATH}, "
        f"target is {TARGET_COVERAGE:.0%}"
    )


def test_user_csv_category_coverage_reported():
    df, column = load_user_csv()
    if df is None:
        pytest.skip(f"No file found at CSV_PATH ('{CSV_PATH}').")
    cat_coverage = compute_category_coverage(df, column, TAXONOMY)
    print("\nPer-category coverage on your data:")
    for cat, cov in sorted(cat_coverage.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cov:.1%}")
    assert all(cov >= 0.0 for cov in cat_coverage.values())


def test_empty_dataset_returns_zero_coverage_not_error():
    terms = [t["term"] for t in build_terms(TAXONOMY)]
    df = pd.DataFrame({"remarks": pd.Series(dtype=str)})
    result = compute_coverage(df, "remarks", terms)
    assert result["listing_coverage"] == 0.0
    assert result["total_listings"] == 0


def test_span_coverage_does_not_double_count_overlapping_matches():
    terms = ["two car garage", "garage"]
    df = pd.DataFrame({"remarks": ["comes with a two car garage"]})
    result = compute_coverage(df, "remarks", terms)
    assert result["span_coverage"] <= 1.0
    # "two car garage" = 12 letters, all of which are covered exactly once
    assert result["span_coverage"] == pytest.approx(12 / _alpha_len("comes with a two car garage"))


def test_span_coverage_full_text_match_is_100_percent():
    terms = ["swimming pool"]
    df = pd.DataFrame({"remarks": ["swimming pool"]})
    result = compute_coverage(df, "remarks", terms)
    assert result["span_coverage"] == 1.0


def test_find_uncovered_terms_excludes_matched_words():
    terms = ["garage"]
    df = pd.DataFrame({"remarks": ["home with a garage and a spectacular view"]})
    uncovered = dict(find_uncovered_terms(df, "remarks", terms, stopwords=set()))
    assert "garage" not in uncovered
    assert "spectacular" in uncovered
    assert "view" in uncovered


def test_find_uncovered_terms_excludes_stopwords():
    terms = []
    df = pd.DataFrame({"remarks": ["this is the listing you have been looking for"]})
    uncovered = dict(find_uncovered_terms(df, "remarks", terms))
    assert "this" not in uncovered
    assert "the" not in uncovered
    assert "looking" in uncovered


def test_plural_bedroom_is_matched():
    terms = ["bedroom"]
    df = pd.DataFrame({"remarks": ["this home has 4 bedrooms and a large yard"]})
    result = compute_coverage(df, "remarks", terms)
    assert result["listing_coverage"] == 1.0


def test_plural_fix_does_not_break_singular_matching():
    terms = ["bedroom"]
    df = pd.DataFrame({"remarks": ["1 bedroom condo"]})
    result = compute_coverage(df, "remarks", terms)
    assert result["listing_coverage"] == 1.0


def test_primary_bedroom_and_suite_are_recognized():
    all_terms = [t["term"] for t in build_terms(TAXONOMY)]
    df = pd.DataFrame({"remarks": [
        "the primary suite features a walk-in closet",
        "primary bedroom on the main floor",
    ]})
    result = compute_coverage(df, "remarks", all_terms)
    assert result["listing_coverage"] == 1.0


def test_find_word_context_identifies_common_neighbor():
    df = pd.DataFrame({"remarks": [
        "features a private pool in the backyard",
        "enjoy the private pool and spa",
        "private entrance off the street",
    ]})
    context = find_word_context(df, "remarks", "private", terms=[])
    after_words = dict(context["after"])
    assert after_words.get("pool", 0) == 2


def test_find_word_context_excludes_already_covered_instances():
    terms = ["living room"]
    df = pd.DataFrame({"remarks": [
        "spacious living room with a fireplace",
        "open living space with high ceilings",
    ]})
    context = find_word_context(df, "remarks", "living", terms=terms)
    after_words = dict(context["after"])
    assert after_words.get("room", 0) == 0
    assert after_words.get("space", 0) == 1


def test_all_null_column_returns_zero_coverage():
    terms = [t["term"] for t in build_terms(TAXONOMY)]
    df = pd.DataFrame({"remarks": [None, None, None]})
    result = compute_coverage(df, "remarks", terms)
    assert result["listing_coverage"] == 0.0


def test_load_user_csv_raises_on_bad_column(tmp_path):
    csv_file = tmp_path / "sample.csv"
    pd.DataFrame({"description": ["a home with a pool"]}).to_csv(csv_file, index=False)
    with pytest.raises(ValueError):
        load_user_csv(csv_path=str(csv_file), column="remarks")


def test_load_user_csv_returns_none_for_missing_path():
    df, column = load_user_csv(csv_path="does/not/exist.csv")
    assert df is None and column is None


if __name__ == "__main__":
    terms = save_taxonomy_json()
    print(f"Taxonomy: {len(TAXONOMY)} categories, {len(terms)} terms -> data/processed/taxonomy.json")

    term_strings = [t["term"] for t in terms]
    df, resolved_column = load_user_csv()

    if df is None:
        print(f"\nNo file found at CSV_PATH ('{CSV_PATH}'). Edit CSV_PATH near the top of")
        print("this file to point at your real listing CSV.")
    else:
        overall = compute_coverage(df, resolved_column, term_strings)
        print(f"\n=== Coverage report: {CSV_PATH} ===")
        print(f"Total listings: {overall['total_listings']}")
        print(f"Listings with >=1 taxonomy term: {overall['listings_with_taxonomy_match']} "
              f"({overall['listing_coverage']:.1%})")
        print(f"Span coverage (non-overlapping): {overall['span_coverage']:.1%}")
        target_status = "PASS" if overall["listing_coverage"] >= TARGET_COVERAGE else "FAIL"
        print(f"Target: listing_coverage >= {TARGET_COVERAGE:.0%}  ->  {target_status}")

        print("\nPer-category coverage:")
        cat_coverage = compute_category_coverage(df, resolved_column, TAXONOMY)
        for cat, cov in sorted(cat_coverage.items(), key=lambda x: -x[1]):
            print(f"  {cat}: {cov:.1%}")

        print("\nMost frequent uncovered words (candidates for new taxonomy terms):")
        for word, count in find_uncovered_terms(df, resolved_column, term_strings, top_k=20):
            print(f"  {word!r}: {count}")

        print("\nContext for ambiguous uncovered words (edit this list to whatever")
        print("your own uncovered-words output shows) -- only genuinely uncovered")
        print("occurrences are counted, so this won't be diluted by phrases that")
        print("already match an existing taxonomy term:")
        for word in ["private", "views", "space", "living", "area", "access",
                     "outdoor", "room", "floor", "dining", "additional"]:
            context = find_word_context(df, resolved_column, word, term_strings, top_k=5)
            print(f"  {word!r} -> before: {context['before']}  |  after: {context['after']}")