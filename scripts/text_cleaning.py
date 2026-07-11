import re
import html
import pandas as pd
from collections import Counter

# Diagnostics (full_abbreviation_counts, promote_confirmed_candidates,
# top_short_tokens, diagnose_ambiguous_terms, _candidate_pool) already ran
# against the real dataset. Result: of ~50 guessed MLS-jargon candidates,
# only 19 actually appear in the data, and a scan of frequent short tokens
# turned up nothing further -- every high-frequency short token was a full
# English word (living, space, offers, views, bath, dining, garage, suite,
# pool, ...), not an abbreviation. This dataset's remarks are written in
# full prose rather than heavy MLS shorthand. abbrev_map below reflects
# that finding: 19 confirmed-present entries, not padded to hit 30+.
# Diagnostic methods are kept at the bottom for re-use if the data changes.


class TextCleaner:
    def __init__(self):
        self.abbrev_map = {
            'br': 'bedroom', 'ba': 'bathroom', 'sqft': 'square feet',
            'w/': 'with', 'w/o': 'without', 'w/d': 'washer/dryer',
            'mbr': 'master bedroom', 'bd': 'bedroom', 'bth': 'bathroom',
            'hoa': 'homeowners association', 'ac': 'air conditioning',
            'apt': 'apartment', 'condo': 'condominium',
            'yr': 'year', 'approx': 'approximately', 'flrs': 'floors',
            'lg': 'large', 'nr': 'near', 'incl': 'including',
        }
        # NOTE: 'sf' and 'dr' are deliberately excluded, per real-data profiling:
        #   - 'sf': 63/68 occurrences (93%) are directly preceded by a number
        #     (e.g. "1,100 sf") -> handled contextually in
        #     normalize_measurements instead of a blind whole-word swap.
        #     The remaining 5 are ambiguous (possibly "single family") and
        #     are correctly left untouched.
        #   - 'dr': of 14 occurrences, 11 are street names ("Sunset Dr"), and
        #     the other 3 are zoning codes ("SR-DR-SC") and "door" ("sliding
        #     dr") -- zero are "dining room" in this dataset.
        self._sorted_abbrevs = sorted(self.abbrev_map.keys(), key=len, reverse=True)
        # abbreviations commonly glued directly to a digit, e.g. "3br", "2.5ba"
        self._numeric_glued = ['br', 'ba', 'bd', 'sqft']

    def clean_text(self, text):
        if text is None or (isinstance(text, float) and pd.isna(text)):
            return ""
        text = self.normalize_unicode(text)
        text = self.normalize_html(text)
        text = self.normalize_prices(text)
        text = self.normalize_measurements(text)
        text = self.expand_abbreviations(text)
        text = self.normalize_whitespace(text)
        return text.strip()

    def normalize_unicode(self, text):
        if text is None or (isinstance(text, float) and pd.isna(text)):
            return text
        text = str(text)
        replacements = {
            '\u2018': "'", '\u2019': "'",  # curly single quotes
            '\u201c': '"', '\u201d': '"',  # curly double quotes
            '\u2013': '-', '\u2014': '-',  # en dash, em dash
            '\u00a0': ' ',                 # non-breaking space
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        return text

    def normalize_html(self, text):
        if text is None or (isinstance(text, float) and pd.isna(text)):
            return text
        text = str(text)
        text = html.unescape(text)             # &amp; -> &, &nbsp; -> ' '
        text = re.sub(r'<[^>]+>', ' ', text)    # strip tags
        return text

    def normalize_prices(self, text):
        if text is None or (isinstance(text, float) and pd.isna(text)):
            return text
        text = str(text)
        # 450k -> 450000
        text = re.sub(r'\b(\d+(?:\.\d+)?)k\b', lambda m: str(int(float(m.group(1)) * 1000)), text, flags=re.I)
        # 1.2m -> 1200000
        text = re.sub(r'\b(\d+(?:\.\d+)?)m\b', lambda m: str(int(float(m.group(1)) * 1000000)), text, flags=re.I)
        return text

    def normalize_measurements(self, text):
        if text is None or (isinstance(text, float) and pd.isna(text)):
            return text
        text = str(text)
        # strip thousands-separator commas before sqft/sf/acres: "2,000 sqft" -> "2000 sqft"
        text = re.sub(
            r'(\d{1,3}(?:,\d{3})+)(\s*(?:sq\.?\s*ft\.?|sqft|sf|acres?))',
            lambda m: m.group(1).replace(',', '') + m.group(2),
            text, flags=re.I
        )
        # sq ft / sq. ft. / sqft -> square feet
        text = re.sub(r'\bsq\.?\s*ft\.?\b', 'square feet', text, flags=re.I)
        text = re.sub(r'\bsqft\b', 'square feet', text, flags=re.I)
        # "sf" is ambiguous (square feet vs. single family), so only expand it
        # when directly preceded by a number, e.g. "1,100 sf" -> "1100 square feet"
        text = re.sub(r'\b(\d+(?:\.\d+)?)\s*sf\b', r'\1 square feet', text, flags=re.I)
        # leading-dot decimals: .5 acres -> 0.5 acres
        text = re.sub(r'(?<!\d)\.(\d+)', r'0.\1', text)
        # room dimensions: 10x12 -> 10 by 12 feet
        text = re.sub(r'\b(\d+)\s*[xX]\s*(\d+)\b', r'\1 by \2 feet', text)
        return text

    def expand_abbreviations(self, text):
        if text is None or (isinstance(text, float) and pd.isna(text)):
            return text
        text = str(text)
        # split digit-glued abbreviations first: "3br" -> "3 br"
        # (\b alone won't split a digit from a letter, since both are "word" chars)
        for abbr in self._numeric_glued:
            text = re.sub(r'(?<=\d)(' + re.escape(abbr) + r')(?=\b)', r' \1', text, flags=re.I)
        # longest match first so multi-word entries expand fully
        for abbr in self._sorted_abbrevs:
            if '/' in abbr or ' ' in abbr:
                pattern = re.escape(abbr)
                if abbr.endswith('/'):
                    pattern += r'(?!o\b)'  # don't let "w/" eat "w/o"
                text = re.sub(pattern, self.abbrev_map[abbr], text, flags=re.I)
            else:
                text = re.sub(r'\b' + re.escape(abbr) + r'\b', self.abbrev_map[abbr], text, flags=re.I)
        return text

    def normalize_whitespace(self, text):
        if text is None or (isinstance(text, float) and pd.isna(text)):
            return text
        text = str(text)
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\s+([.,!?;:])', r'\1', text)
        text = re.sub(r'!{2,}', '!', text)
        return text.strip()

    def profile_column(self, df, column_name):
        """Analyze what's actually in L_Remarks"""
        col = df[column_name]
        non_null = col.dropna().astype(str)
        return {
            'null_rate': col.isnull().mean(),
            'avg_length': non_null.str.len().mean() if len(non_null) else 0.0,
            'common_terms': self._extract_top_ngrams(non_null),
            'price_mentions': non_null.str.contains(r'\$?\d+\s*[kKmM]\b|\$\d').sum(),
            'has_html': non_null.str.contains(r'<[a-zA-Z/][^>]*>|&[a-zA-Z]+;', regex=True).sum(),
            'common_abbreviations': self._detect_abbreviations(non_null),
        }

    def _extract_top_ngrams(self, series, n=2, top_k=15):
        counter = Counter()
        for text in series:
            tokens = re.findall(r"[a-zA-Z0-9']+", text.lower())
            for i in range(len(tokens) - n + 1):
                counter[' '.join(tokens[i:i + n])] += 1
        return counter.most_common(top_k)

    def _detect_abbreviations(self, series, top_k=None):
        counter = Counter()
        joined = ' '.join(series).lower()
        for abbr in self.abbrev_map:
            if ' ' in abbr or '/' in abbr:
                pattern = re.escape(abbr)
            else:
                pattern = r'(?:\b|(?<=\d))' + re.escape(abbr) + r'\b'
            hits = len(re.findall(pattern, joined))
            if hits:
                counter[abbr] = hits
        # top_k=None returns everything, sorted by count -- with only 19
        # validated entries in abbrev_map there's no need to clip the report
        return counter.most_common(top_k)

    # ------------------------------------------------------------------
    # Diagnostic / evidence-gathering methods used to build abbrev_map above.
    # Not part of the normal clean_text pipeline; kept for re-use if the
    # dataset changes and the dictionary needs to be re-validated.
    # ------------------------------------------------------------------

    def diagnose_ambiguous_terms(self, df, column_name):
        """Breaks down 'sf' and 'dr' usage by context (see NOTE in __init__)."""
        raw = df[column_name].dropna().astype(str)
        joined_raw = ' '.join(raw)
        joined_lower = joined_raw.lower()

        sf_total = len(re.findall(r'\bsf\b', joined_lower))
        sf_digit_preceded = len(re.findall(r'\d+(?:\.\d+)?\s*sf\b', joined_lower))
        sf_standalone = sf_total - sf_digit_preceded

        dr_total = len(re.findall(r'\bdr\b', joined_lower))
        dr_room_context = len(re.findall(r'\b(?:formal|sep|separate)\s+dr\b', joined_lower))
        dr_street_context = len(re.findall(r'\b[A-Z][a-zA-Z]+\s+Dr\b', joined_raw))
        dr_other = dr_total - dr_room_context - dr_street_context

        return {
            'sf_total': sf_total,
            'sf_digit_preceded_likely_sqft': sf_digit_preceded,
            'sf_standalone_ambiguous': sf_standalone,
            'dr_total': dr_total,
            'dr_room_context_formal_sep': dr_room_context,
            'dr_street_context_e.g._Sunset_Dr': dr_street_context,
            'dr_other_unclear': dr_other,
        }

    def top_short_tokens(self, df, column_name, max_len=6, top_k=50):
        """Finds frequent short tokens not already in abbrev_map, to catch
        genuine abbreviations the current dict might be missing."""
        stopwords = {
            'a', 'an', 'the', 'and', 'or', 'of', 'to', 'in', 'on', 'at', 'is',
            'it', 'for', 'this', 'that', 'with', 'as', 'by', 'be', 'has',
            'new', 'home', 'room', 'large', 'nice', 'great', 'close', 'many',
            'all', 'from', 'you', 'your', 'each', 'plus', 'over', 'own',
            'per', 'off', 'out', 'up', 'so', 'no', 'not', 'one', 'two',
            'three', 'four', 'five', 'six', 'unit', 'floor', 'area', 'style',
            'both', 'well', 'more', 'also', 'high', 'full', 'just', 'while',
            'into', 'rare', 'can', 'its', 'are', 'there',
        }
        already_known = set(self.abbrev_map)
        non_null = df[column_name].dropna().astype(str)
        counter = Counter()
        for text in non_null:
            tokens = re.findall(r"[a-zA-Z]+(?:/[a-zA-Z]+)?", text.lower())
            for tok in tokens:
                bare = tok.rstrip('/')
                if len(bare) <= max_len and bare not in stopwords and tok not in already_known:
                    counter[tok] += 1
        return counter.most_common(top_k)


if __name__ == "__main__":
    cleaner = TextCleaner()
    df = pd.read_csv('data/processed/listing_sample.csv')

    profile = cleaner.profile_column(df, 'remarks')
    print(f"HTML tags found in {profile['has_html']} listings")
    print(f"Common abbreviations: {profile['common_abbreviations']}")

    df['remarks_cleaned'] = df['remarks'].apply(cleaner.clean_text)
    df.to_csv('data/processed/listing_sample_cleaned.csv', index=False)

    # Set to True to re-run the diagnostics that were used to build
    # abbrev_map (only needed again if the underlying dataset changes).
    RUN_DIAGNOSTICS = False
    if RUN_DIAGNOSTICS:
        print(f"Ambiguous term breakdown: {cleaner.diagnose_ambiguous_terms(df, 'remarks')}")
        print("Frequent short tokens not yet mapped:")
        for tok, count in cleaner.top_short_tokens(df, 'remarks'):
            print(f"  {tok!r}: {count}")


def test_price_normalization():
    cleaner = TextCleaner()
    assert '450000' in cleaner.normalize_prices('priced at 450k')
    assert '1200000' in cleaner.normalize_prices('$1.2m home')


def test_profiling():
    cleaner = TextCleaner()
    df = pd.read_csv('data/processed/listing_sample.csv')
    profile = cleaner.profile_column(df, 'remarks')
    assert 'null_rate' in profile
    assert 'avg_length' in profile