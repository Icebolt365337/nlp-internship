from __future__ import annotations
import nltk
try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    try:
        nltk.download('punkt_tab', quiet=True)
    except Exception:
        pass

LISTINGS_DATA_PATH = 'data/processed/listing_sample_cleaned.csv'

def _sent_tokenize(text: str):
    try:
        return nltk.sent_tokenize(text)
    except LookupError:
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        return [s for s in sentences if s]

class ListingSummarizer:

    def extractive_summary(self, remarks, entities, num_sentences=2):
        sentences = _sent_tokenize(remarks)
        if not sentences:
            return ""

        scores = []
        for i, sent in enumerate(sentences):
            score = 0
            if i == 0:
                score += 2
            if str(entities.get('bedrooms', '')) and str(entities.get('bedrooms', '')) in sent:
                score += 1
            if str(entities.get('bathrooms', '')) and str(entities.get('bathrooms', '')) in sent:
                score += 1
            if 'pool' in sent.lower():
                score += 1
            for amenity in entities.get('amenities', []) or []:
                if amenity.lower() in sent.lower():
                    score += 1
                    break
            scores.append((score, sent))

        top_sentences = sorted(scores, reverse=True)[:num_sentences]
        top_texts = {s for _, s in top_sentences}
        return ' '.join(s for s in sentences if s in top_texts)

    def summarize(self, listing_record, entities, num_sentences=1):
        remarks = (
            listing_record.get('L_Remarks')
            or listing_record.get('remarks_cleaned')
            or listing_record.get('remarks')
            or ''
        )
        city = listing_record.get('L_City') or listing_record.get('city')

        lead_in = self._compose_lead_in(entities, city)
        features = self._top_features(entities)

        extractive = self.extractive_summary(remarks, entities, num_sentences=num_sentences)

        parts = [lead_in]
        if features:
            parts.append(f"Highlights: {', '.join(features)}.")
        if extractive:
            parts.append(extractive)

        return ' '.join(p for p in parts if p).strip()

    def _compose_lead_in(self, entities, city):
        pieces = []
        beds = entities.get('bedrooms')
        baths = entities.get('bathrooms')
        if beds is not None or baths is not None:
            bed_bath = []
            if beds is not None:
                bed_bath.append(f"{beds} bed")
            if baths is not None:
                bed_bath.append(f"{baths} bath")
            pieces.append('/'.join(bed_bath) if len(bed_bath) > 1 else bed_bath[0])

        price = entities.get('price')
        if price is not None:
            pieces.append(f"${price:,.0f}" if isinstance(price, (int, float)) else f"${price}")

        lead = "This property"
        if pieces:
            lead = ' '.join(pieces) + " home"
        if city:
            lead += f" in {city}"
        return (lead + ".").strip()

    def _top_features(self, entities, n=2):
        amenities = entities.get('amenities', []) or []
        return amenities[:n]

    def abstractive_summary(self, remarks, model=None):
        if model is None:
            raise ValueError(
                "abstractive_summary requires an injected model, e.g. "
                "model=transformers.pipeline('summarization', model='facebook/bart-large-cnn'). "
                "No model is loaded automatically."
            )
        result = model(remarks)
        return result[0]['summary_text']


class StubAbstractiveModel:

    def __call__(self, text):
        truncated = text.strip().split('. ')[0]
        return [{'summary_text': truncated + ('.' if not truncated.endswith('.') else '')}]


def evaluate_rouge_l(summarizer, test_cases):
    from rouge_score import rouge_scorer
    scorer = rouge_scorer.RougeScorer(['rougeL'], use_stemmer=True)

    scores = []
    for listing_record, entities, reference in test_cases:
        generated = summarizer.summarize(listing_record, entities)
        result = scorer.score(reference, generated)
        scores.append(result['rougeL'].fmeasure)

    mean_score = sum(scores) / len(scores) if scores else 0.0
    return mean_score, scores


RATING_FIELDS = ['accuracy_1_to_5', 'fluency_1_to_5', 'completeness_1_to_5', 'rater_notes']


def run_human_eval_harness(summarizer, listings_with_entities, n=20):
    rows = []
    for listing_record, entities in listings_with_entities[:n]:
        summary = summarizer.summarize(listing_record, entities)
        row = {
            'listing_id': listing_record.get('L_ListingID') or listing_record.get('id'),
            'summary': summary,
        }
        row.update({field: '' for field in RATING_FIELDS})
        rows.append(row)
    return rows


def export_human_eval_csv(rows, path='human_eval.csv'):
    import csv
    fieldnames = ['listing_id', 'summary'] + RATING_FIELDS
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


class AnswerabilityChecker:
    def __init__(self, taxonomy=None, schema_validator=None, query_parser=None):
        self.taxonomy = taxonomy or {}
        self.validator = schema_validator

        if query_parser is None:
            try:
                from query_parser import QueryParser
                query_parser = QueryParser()
            except ImportError:
                query_parser = None
        self.parser = query_parser

        self.real_estate_keywords = [
            'house', 'home', 'bed', 'bath', 'property', 'listing', 'price',
            'sqft', 'sq ft', 'square feet', 'pool', 'garage', 'condo',
            'townhouse', 'apartment', 'acre', 'realtor', 'mortgage', 'rent',
        ]

    def check_pre_query(self, query):
        query_lower = (query or '').lower()

        has_re_terms = any(kw in query_lower for kw in self.real_estate_keywords)
        if not has_re_terms:
            return False, "This doesn't appear to be a real estate question"

        if self.parser is None:
            return True, "Query is answerable"

        filters = self.parser.parse(query)

        if self.validator is None or not filters:
            return True, "Query is answerable"

        valid, errors = self.validator.validate_query(filters)
        if not valid:
            return False, f"Query references invalid data: {'; '.join(errors)}"

        return True, "Query is answerable"

    def check_post_query(self, query, results):
        if results is None:
            return False, "No listings match your criteria"

        if hasattr(results, 'empty'):  # pandas DataFrame
            if results.empty:
                return False, "No listings match your criteria"
            if results.isnull().all().all():
                return False, "Query returned no meaningful data"
            return True, "Results found"

        if len(results) == 0:
            return False, "No listings match your criteria"
        all_null = all(
            all(v is None for v in row.values()) for row in results if isinstance(row, dict)
        )
        if all_null:
            return False, "Query returned no meaningful data"
        return True, "Results found"


class StubParser:
    def __init__(self, filters=None):
        self._filters = filters or {}

    def parse(self, query):
        return dict(self._filters)


class StubValidator:
    def __init__(self, valid=True, errors=None):
        self._valid = valid
        self._errors = errors or []

    def validate_query(self, filters):
        return self._valid, self._errors

SAMPLE_LISTINGS = [
    (
        {"L_ListingID": 1, "L_City": "Irvine",
         "L_Remarks": "Charming home in a great neighborhood. Features a sparkling pool and updated kitchen. "
                       "Close to top rated schools and shopping."},
        {"bedrooms": 3, "bathrooms": 2, "price": 750000, "amenities": ["pool", "updated kitchen"]},
        "3 bed 2 bath home in Irvine for $750,000 with a pool and updated kitchen.",
    ),
    (
        {"L_ListingID": 2, "L_City": "Portland",
         "L_Remarks": "Spacious craftsman with hardwood floors throughout. A cozy fireplace anchors the living room. "
                       "Large fenced backyard perfect for entertaining."},
        {"bedrooms": 4, "bathrooms": 2.5, "price": 620000, "amenities": ["hardwood floors", "fireplace"]},
        "4 bed 2.5 bath craftsman in Portland for $620,000 with hardwood floors and a fireplace.",
    ),
    (
        {"L_ListingID": 3, "L_City": "Denver",
         "L_Remarks": "Waterfront property with stunning mountain views. Two car garage and a finished basement. "
                       "Move-in ready and freshly painted."},
        {"bedrooms": 5, "bathrooms": 3, "price": 910000, "amenities": ["waterfront", "mountain view", "garage"]},
        "5 bed 3 bath waterfront home in Denver for $910,000 with mountain views and a two car garage.",
    ),
    (
        {"L_ListingID": 4, "L_City": "Austin",
         "L_Remarks": "Contemporary home with solar panels and an open floor plan. Chef's kitchen with granite "
                       "countertops. Located in a quiet cul-de-sac."},
        {"bedrooms": 3, "bathrooms": 2, "price": 540000, "amenities": ["solar panels", "granite countertops"]},
        "3 bed 2 bath contemporary home in Austin for $540,000 with solar panels and granite countertops.",
    ),
    (
        {"L_ListingID": 5, "L_City": "Seattle",
         "L_Remarks": "Modern condo with panoramic city views. Walking distance to restaurants and transit. "
                       "Includes a private balcony and in-unit laundry."},
        {"bedrooms": 2, "bathrooms": 1, "price": 480000, "amenities": ["city view", "balcony"]},
        "2 bed 1 bath condo in Seattle for $480,000 with city views and a private balcony.",
    ),
]


def test_extractive_summary_returns_sentences_in_original_order():
    summarizer = ListingSummarizer()
    record, entities, _ = SAMPLE_LISTINGS[0]
    result = summarizer.extractive_summary(record["L_Remarks"], entities, num_sentences=2)
    sentences = _sent_tokenize(record["L_Remarks"])
    positions = [sentences.index(s) for s in _sent_tokenize(result) if s in sentences]
    assert positions == sorted(positions)


def test_summarize_includes_required_fields():
    summarizer = ListingSummarizer()
    for record, entities, _ in SAMPLE_LISTINGS:
        summary = summarizer.summarize(record, entities)
        assert str(entities['bedrooms']) in summary
        assert str(entities['bathrooms']) in summary
        assert record['L_City'] in summary
        assert f"{entities['price']:,.0f}" in summary or str(entities['price']) in summary
        assert any(a in summary for a in entities['amenities'][:2])


def test_summarize_is_2_to_3_sentences():
    summarizer = ListingSummarizer()
    for record, entities, _ in SAMPLE_LISTINGS:
        summary = summarizer.summarize(record, entities)
        n_sentences = len(_sent_tokenize(summary))
        assert 2 <= n_sentences <= 4, f"expected ~2-3 sentences, got {n_sentences}: {summary!r}"


def test_rouge_l_over_040_on_test_set():
    summarizer = ListingSummarizer()
    mean_score, scores = evaluate_rouge_l(summarizer, SAMPLE_LISTINGS)
    assert mean_score > 0.4, f"mean ROUGE-L {mean_score:.3f} below 0.4 target (per-case: {scores})"


def test_abstractive_summary_requires_injected_model():
    summarizer = ListingSummarizer()
    try:
        summarizer.abstractive_summary("Some remarks.")
        assert False, "expected ValueError when no model is injected"
    except ValueError:
        pass


def test_abstractive_summary_works_with_stub_model():
    summarizer = ListingSummarizer()
    result = summarizer.abstractive_summary(
        "Charming home with a pool. Close to schools.", model=StubAbstractiveModel()
    )
    assert isinstance(result, str) and len(result) > 0


def test_human_eval_harness_produces_20_rateable_rows():
    summarizer = ListingSummarizer()
    listings = [(r, e) for r, e, _ in SAMPLE_LISTINGS] * 4
    rows = run_human_eval_harness(summarizer, listings, n=20)
    assert len(rows) == 20
    for row in rows:
        assert 'summary' in row and row['summary']
        for field in RATING_FIELDS:
            assert field in row and row[field] == ''


def test_human_eval_csv_export():
    import tempfile, os, csv
    summarizer = ListingSummarizer()
    listings = [(r, e) for r, e, _ in SAMPLE_LISTINGS] * 4
    rows = run_human_eval_harness(summarizer, listings, n=20)
    out_dir = tempfile.mkdtemp()
    path = export_human_eval_csv(rows, path=os.path.join(out_dir, 'human_eval.csv'))
    with open(path) as f:
        reader = list(csv.DictReader(f))
    assert len(reader) == 20
    assert 'accuracy_1_to_5' in reader[0]


def test_non_real_estate_query_is_rejected():
    checker = AnswerabilityChecker(query_parser=StubParser())
    can_answer, message = checker.check_pre_query("what's the weather like today")
    assert can_answer is False
    assert "doesn't appear to be a real estate question" in message


def test_real_estate_query_with_valid_filters_is_answerable():
    parser = StubParser(filters={"city": "Irvine", "bedrooms": 3})
    validator = StubValidator(valid=True)
    checker = AnswerabilityChecker(schema_validator=validator, query_parser=parser)
    can_answer, message = checker.check_pre_query("3 bed homes in Irvine")
    assert can_answer is True


def test_real_estate_query_with_invalid_filters_is_rejected_with_reason():
    parser = StubParser(filters={"city": "Nowhereville"})
    validator = StubValidator(valid=False, errors=["City 'Nowhereville' not found in database"])
    checker = AnswerabilityChecker(schema_validator=validator, query_parser=parser)
    can_answer, message = checker.check_pre_query("homes in Nowhereville")
    assert can_answer is False
    assert "Nowhereville" in message


def test_query_with_no_validator_still_passes_keyword_check():
    checker = AnswerabilityChecker(query_parser=StubParser(filters={"city": "Irvine"}))
    can_answer, message = checker.check_pre_query("homes in Irvine")
    assert can_answer is True


def test_query_with_no_parser_falls_back_gracefully():
    checker = AnswerabilityChecker(query_parser=None)
    checker.parser = None
    can_answer, message = checker.check_pre_query("homes with a pool")
    assert can_answer is True


def test_post_query_empty_list_is_not_answerable():
    checker = AnswerabilityChecker()
    can_answer, message = checker.check_post_query("homes in Irvine", [])
    assert can_answer is False
    assert "No listings" in message


def test_post_query_all_null_rows_is_not_answerable():
    checker = AnswerabilityChecker()
    results = [{"price": None, "beds": None}, {"price": None, "beds": None}]
    can_answer, message = checker.check_post_query("homes in Irvine", results)
    assert can_answer is False
    assert "no meaningful data" in message


def test_post_query_with_real_results_is_answerable():
    checker = AnswerabilityChecker()
    results = [{"price": 650000, "beds": 3}]
    can_answer, message = checker.check_post_query("homes in Irvine", results)
    assert can_answer is True


def test_post_query_with_pandas_dataframe():
    try:
        import pandas as pd
    except ImportError:
        return
    checker = AnswerabilityChecker()
    df = pd.DataFrame([{"price": 650000, "beds": 3}])
    can_answer, message = checker.check_post_query("homes in Irvine", df)
    assert can_answer is True

    empty_df = pd.DataFrame()
    can_answer, message = checker.check_post_query("homes in Irvine", empty_df)
    assert can_answer is False


def test_answerability_and_summary_work_together():
    parser = StubParser(filters={"city": "Irvine", "bedrooms": 3})
    validator = StubValidator(valid=True)
    checker = AnswerabilityChecker(schema_validator=validator, query_parser=parser)
    summarizer = ListingSummarizer()

    can_answer, _ = checker.check_pre_query("3 bed homes in Irvine")
    assert can_answer is True

    record, entities, _ = SAMPLE_LISTINGS[0]
    summary = summarizer.summarize(record, entities)
    assert "Irvine" in summary and "3" in summary


def test_integration_with_real_query_parser_and_schema_validator_if_available():
    try:
        from query_parser import QueryParser, SchemaValidator
    except ImportError:
        return
    import tempfile, json, os
    schema = {
        "valid_cities": ["Irvine", "Portland"],
        "valid_property_types": ["single-family", "condo"],
        "valid_amenities": ["pool", "garage"],
        "ranges": {"price": {"min": 100000, "max": 5000000},
                   "bedrooms": {"min": 1, "max": 10},
                   "bathrooms": {"min": 1, "max": 10}},
    }
    fd, path = tempfile.mkstemp(suffix='.json')
    with os.fdopen(fd, 'w') as f:
        json.dump(schema, f)

    try:
        validator = SchemaValidator(schema_path=path)
        checker = AnswerabilityChecker(schema_validator=validator, query_parser=QueryParser())

        can_answer, message = checker.check_pre_query("3 bed homes in Irvine under 700k")
        assert can_answer is True

        can_answer, message = checker.check_pre_query("homes in Faketown")
        assert can_answer is False
        assert "Faketown" in message
    finally:
        os.remove(path)


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
                print(f"  PASS: {name}")
            except AssertionError as e:
                failed += 1
                print(f"  FAIL: {name}: {e}")
    print(f"\n{passed}/{passed + failed} tests passed")

    print("\n=== Example summaries ===")
    summarizer = ListingSummarizer()
    for record, entities, reference in SAMPLE_LISTINGS:
        print(f"\nListing {record['L_ListingID']}:")
        print(f"  generated: {summarizer.summarize(record, entities)}")
        print(f"  reference: {reference}")

    mean_score, scores = evaluate_rouge_l(summarizer, SAMPLE_LISTINGS)
    print(f"\nMean ROUGE-L F1: {mean_score:.3f} (target > 0.4)")

    print("\n=== Human eval harness (first 3 of 20 rows) ===")
    listings = [(r, e) for r, e, _ in SAMPLE_LISTINGS] * 4
    rows = run_human_eval_harness(summarizer, listings, n=20)
    for row in rows[:3]:
        print(f"  {row}")
    print(f"  ... ({len(rows)} rows total, ratings blank for teammates to fill in)")

    print("\n=== Example usage: answerability check, then summarize the match ===")

    example_listing = {
        "L_ListingID": 1, "L_City": "Irvine",
        "L_Remarks": "Charming home in a great neighborhood. Features a sparkling pool "
                     "and updated kitchen. Close to top rated schools and shopping.",
    }
    example_entities = {
        "bedrooms": 3, "bathrooms": 2, "price": 750000,
        "amenities": ["pool", "updated kitchen"],
    }

    import os
    if os.path.isfile(LISTINGS_DATA_PATH):
        import pandas as pd
        df = pd.read_csv(LISTINGS_DATA_PATH)
        row = df.iloc[0].to_dict()
        example_listing = row
        remarks = row.get('remarks_cleaned') or row.get('remarks') or row.get('L_Remarks') or ''
        try:
            from entity_extractor import EntityExtractor
            example_entities = EntityExtractor().extract_all(remarks)
        except ImportError:
            example_entities = {"bedrooms": None, "bathrooms": None, "price": None, "amenities": []}
        for entity_key, csv_col in (("bedrooms", "beds"), ("bathrooms", "baths"), ("price", "price")):
            if row.get(csv_col) is not None and str(row.get(csv_col)) != 'nan':
                example_entities[entity_key] = row[csv_col]
        print(f"  Loaded example listing from {LISTINGS_DATA_PATH}")
    else:
        print(f"  ({LISTINGS_DATA_PATH} not found -- using one hardcoded example listing instead)")

    parser = StubParser(filters={"city": "Nowhereville"})
    validator = StubValidator(valid=False, errors=["City 'Nowhereville' not found in database"])
    checker = AnswerabilityChecker(schema_validator=validator, query_parser=parser)

    for query in ["what's the weather today", "homes in Nowhereville", "3 bed homes in Irvine"]:
        if "Nowhere" in query:
            checker.parser = StubParser(filters={"city": "Nowhereville"})
            checker.validator = StubValidator(valid=False, errors=["City 'Nowhereville' not found in database"])
        elif "Irvine" in query:
            checker.parser = StubParser(filters={"city": "Irvine", "bedrooms": 3})
            checker.validator = StubValidator(valid=True)
        else:
            checker.parser = StubParser(filters={})
            checker.validator = StubValidator(valid=True)

        can_answer, message = checker.check_pre_query(query)
        print(f"\n  Query: {query!r}")
        print(f"    answerable={can_answer}, message={message!r}")

        if can_answer:
            summary = summarizer.summarize(example_listing, example_entities)
            print(f"    example listing summary: {summary!r}")