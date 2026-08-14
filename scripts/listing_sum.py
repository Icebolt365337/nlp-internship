from __future__ import annotations

LISTINGS_DATA_PATH = 'data/processed/listing_sample_cleaned.csv'


class _FallbackSummarizer:

    def summarize(self, listing_record, entities):
        city = listing_record.get('L_City') or listing_record.get('city')
        beds = entities.get('bedrooms')
        baths = entities.get('bathrooms')
        price = entities.get('price')
        amenities = (entities.get('amenities') or [])[:2]

        pieces = []
        if beds is not None:
            pieces.append(f"{beds} bed")
        if baths is not None:
            pieces.append(f"{baths} bath")
        lead = '/'.join(pieces) + " home" if pieces else "Home"
        if city:
            lead += f" in {city}"
        if price is not None:
            lead += f" for ${price:,.0f}" if isinstance(price, (int, float)) else f" for ${price}"
        lead += "."

        if amenities:
            lead += f" Features {', '.join(amenities)}."
        return lead


class AnswerabilityChecker:
    def __init__(self, taxonomy=None, schema_validator=None, query_parser=None):
        self.taxonomy = taxonomy or {}
        self.validator = schema_validator  # optional: skip data-validity check if not provided

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
        """Check BEFORE generating SQL."""
        query_lower = (query or '').lower()

        # Check 1: Is this a real estate question?
        has_re_terms = any(kw in query_lower for kw in self.real_estate_keywords)
        if not has_re_terms:
            return False, "This doesn't appear to be a real estate question"

        # Check 2: Does query reference valid data? (Week 4's schema validator)
        if self.parser is None:
            # No parser available -- can't extract filters to validate,
            # so we can't rule the query out on this check.
            return True, "Query is answerable"

        filters = self.parser.parse(query)

        if self.validator is None or not filters:
            # No validator wired up, or nothing to validate (e.g. a query
            # with no structured filters at all, like "tell me about homes").
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

        # list-of-dicts (or similar) fallback
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


def test_integration_with_real_query_parser_and_schema_validator_if_available():
    """If query_parser.py's real QueryParser/SchemaValidator are importable
    in this environment, exercise the actual end-to-end integration path
    instead of stubs."""
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
        try:
            from entity_extractor import EntityExtractor
            remarks = row.get('remarks_cleaned') or row.get('remarks') or row.get('L_Remarks') or ''
            example_entities = EntityExtractor().extract_all(remarks)
        except ImportError:
            example_entities = {
                "bedrooms": row.get('beds'), "bathrooms": row.get('baths'),
                "price": row.get('price'), "amenities": [],
            }
        print(f"  Loaded example listing from {LISTINGS_DATA_PATH}")
    else:
        print(f"  ({LISTINGS_DATA_PATH} not found -- using one hardcoded example listing instead)")

    try:
        from listing_summarizer import ListingSummarizer
        summarizer = ListingSummarizer()
    except ImportError:
        summarizer = _FallbackSummarizer()
        print("  (listing_summarizer.py not found -- using a minimal built-in summarizer instead)")

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