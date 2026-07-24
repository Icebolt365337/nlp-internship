import re
import json
import os


class QueryParser:

    def parse(self, query):
        filters = {}

        # --- Price ---
        if match := re.search(r'between\s+\$?(\d[\d,]*(?:\.\d+)?)\s*([km]?)\s+and\s+\$?(\d[\d,]*(?:\.\d+)?)\s*([km]?)', query, re.I):
            lo = self._parse_number(match.group(1), match.group(2))
            hi = self._parse_number(match.group(3), match.group(4))
            filters['price_min'], filters['price_max'] = min(lo, hi), max(lo, hi)
        elif match := re.search(r'\$?(\d[\d,]*(?:\.\d+)?)(k|m)\s*-\s*\$?(\d[\d,]*(?:\.\d+)?)\s*([km]?)', query, re.I):
            # requires k/m suffix on the first number so "2-3 bed" isn't mistaken for a price
            lo = self._parse_number(match.group(1), match.group(2))
            hi = self._parse_number(match.group(3), match.group(4))
            filters['price_min'], filters['price_max'] = min(lo, hi), max(lo, hi)
        elif match := re.search(r'(?:under|below|less than|no more than|up to)\s+\$?(\d[\d,]*(?:\.\d+)?)\s*([km]?)', query, re.I):
            filters['price_max'] = self._parse_number(match.group(1), match.group(2))
        elif match := re.search(r'(?:over|above|more than|at least|starting at)\s+\$?(\d[\d,]*(?:\.\d+)?)\s*([km]?)(?!\s*(?:bed|br|bath|ba|sqft|sq\s*ft|acre))', query, re.I):
            filters['price_min'] = self._parse_number(match.group(1), match.group(2))

        # --- Bedrooms ---
        if match := re.search(r'(\d+)\s*(?:to|-)\s*(\d+)\s*(?:bed|br|bedroom)s?', query, re.I):
            filters['bedrooms_min'], filters['bedrooms_max'] = int(match.group(1)), int(match.group(2))
        elif match := re.search(r'(\d+)\s*\+\s*(?:bed|br|bedroom)s?', query, re.I):
            filters['bedrooms_min'] = int(match.group(1))
        elif match := re.search(r'at least\s+(\d+)\s*(?:bed|br|bedroom)s?', query, re.I):
            filters['bedrooms_min'] = int(match.group(1))
        elif match := re.search(r'(?:up to|no more than)\s+(\d+)\s*(?:bed|br|bedroom)s?', query, re.I):
            filters['bedrooms_max'] = int(match.group(1))
        elif match := re.search(r'(\d+)\s*(?:bed|br|bedroom)s?', query, re.I):
            filters['bedrooms'] = int(match.group(1))

        # --- Bathrooms ---
        if match := re.search(r'(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*(?:bath|ba)s?\b', query, re.I):
            filters['bathrooms_min'], filters['bathrooms_max'] = float(match.group(1)), float(match.group(2))
        elif match := re.search(r'(\d+(?:\.\d+)?)\s*\+\s*(?:bath|ba)s?\b', query, re.I):
            filters['bathrooms_min'] = float(match.group(1))
        elif match := re.search(r'at least\s+(\d+(?:\.\d+)?)\s*(?:bath|ba)s?\b', query, re.I):
            filters['bathrooms_min'] = float(match.group(1))
        elif match := re.search(r'(?:up to|no more than)\s+(\d+(?:\.\d+)?)\s*(?:bath|ba)s?\b', query, re.I):
            filters['bathrooms_max'] = float(match.group(1))
        elif match := re.search(r'(\d+(?:\.\d+)?)\s*(?:bath|ba)s?\b', query, re.I):
            filters['bathrooms'] = float(match.group(1))

        # --- Square footage ---
        if match := re.search(r'between\s+(\d[\d,]*)\s*and\s+(\d[\d,]*)\s*(?:sq\s*\.?\s*ft|sqft|square feet)', query, re.I):
            filters['sqft_min'] = int(match.group(1).replace(',', ''))
            filters['sqft_max'] = int(match.group(2).replace(',', ''))
        elif match := re.search(r'(?:over|above|more than|at least)\s+(\d[\d,]*)\s*(?:sq\s*\.?\s*ft|sqft|square feet)', query, re.I):
            filters['sqft_min'] = int(match.group(1).replace(',', ''))
        elif match := re.search(r'(?:under|below|less than|up to)\s+(\d[\d,]*)\s*(?:sq\s*\.?\s*ft|sqft|square feet)', query, re.I):
            filters['sqft_max'] = int(match.group(1).replace(',', ''))

        # --- Year built ---
        if match := re.search(r'(?:built after|newer than|built since)\s+(\d{4})', query, re.I):
            filters['year_built_min'] = int(match.group(1))
        if match := re.search(r'(?:built before|older than)\s+(\d{4})', query, re.I):
            filters['year_built_max'] = int(match.group(1))

        # --- Lot size ---
        if re.search(r'half[- ]acre', query, re.I):
            filters['lot_size_min_acres'] = 0.5
        elif match := re.search(r'(\d+(?:\.\d+)?)\+?\s*acre', query, re.I):
            filters['lot_size_min_acres'] = float(match.group(1))

        # --- Garage / stories ---
        if match := re.search(r'(\d+)[- ]car garage', query, re.I):
            filters['garage_spaces_min'] = int(match.group(1))

        if re.search(r'\b(?:two|2)[- ]stor(?:y|ey)\b', query, re.I):
            filters['stories'] = 2
        elif re.search(r'\b(?:single|one|1)[- ]stor(?:y|ey)\b', query, re.I):
            filters['stories'] = 1

        # --- Property type ---
        if match := re.search(r'\b(single[- ]family|condo(?:minium)?s?|townhouses?|apartments?|duplex(?:es)?|multi[- ]family|houses?)\b', query, re.I):
            filters['property_type'] = self._normalize_property_type(match.group(1))

        # --- City ---
        stopwords = r'under|over|below|above|with|without|near|for|that|having|and|priced|built|up|no|at|between|less|more|within'
        if match := re.search(r'\bin\s+([a-zA-Z][a-zA-Z\s]*?)(?=\s+(?:' + stopwords + r')\b|[,.\!\?]|$)', query, re.I):
            filters['city'] = re.sub(r'\s+', ' ', match.group(1).strip()).title()

        # --- Amenities (positive + negation) ---
        amenity_phrases = [
            'air conditioning', 'central air', 'hardwood floors', 'updated kitchen',
            'walk-in closet', 'granite countertops', 'stainless steel appliances',
            'gated community', 'solar panels', 'pool', 'garage', 'fireplace',
            'basement', 'waterfront', 'view', 'backyard', 'yard', 'deck', 'patio', 'hoa',
        ]
        amenities, exclude_amenities = [], []
        for phrase in amenity_phrases:
            if re.search(r'\b(?:no|without|not)\s+(?:a\s+|an\s+)?' + re.escape(phrase) + r'\b', query, re.I):
                exclude_amenities.append(phrase)
            elif re.search(r'\b' + re.escape(phrase) + r'\b', query, re.I):
                amenities.append(phrase)
        if amenities:
            filters['amenities'] = amenities
        if exclude_amenities:
            filters['exclude_amenities'] = exclude_amenities

        return filters

    def _parse_number(self, num_str, suffix=''):
        value = float(num_str.replace(',', ''))
        suffix = (suffix or '').lower()
        if suffix == 'k':
            value *= 1_000
        elif suffix == 'm':
            value *= 1_000_000
        return int(value) if value.is_integer() else value

    def _normalize_property_type(self, raw):
        ptype = raw.lower().replace(' ', '-')
        if ptype in ('house', 'houses'):
            return 'single-family'
        if ptype in ('condo', 'condos', 'condominium', 'condominiums'):
            return 'condo'
        if ptype in ('townhouse', 'townhouses'):
            return 'townhouse'
        if ptype in ('apartment', 'apartments'):
            return 'apartment'
        if ptype in ('duplex', 'duplexes'):
            return 'duplex'
        return ptype  # single-family, multi-family already normalized

    def to_sql(self, filters):
        conditions = []
        params = []

        if 'price_min' in filters:
            conditions.append('L_SystemPrice >= %s')
            params.append(filters['price_min'])
        if 'price_max' in filters:
            conditions.append('L_SystemPrice <= %s')
            params.append(filters['price_max'])

        if 'bedrooms' in filters:
            conditions.append('L_Keyword2 = %s')
            params.append(filters['bedrooms'])
        if 'bedrooms_min' in filters:
            conditions.append('L_Keyword2 >= %s')
            params.append(filters['bedrooms_min'])
        if 'bedrooms_max' in filters:
            conditions.append('L_Keyword2 <= %s')
            params.append(filters['bedrooms_max'])

        if 'bathrooms' in filters:
            conditions.append('L_Keyword3 = %s')
            params.append(filters['bathrooms'])
        if 'bathrooms_min' in filters:
            conditions.append('L_Keyword3 >= %s')
            params.append(filters['bathrooms_min'])
        if 'bathrooms_max' in filters:
            conditions.append('L_Keyword3 <= %s')
            params.append(filters['bathrooms_max'])

        if 'sqft_min' in filters:
            conditions.append('L_SqFt >= %s')
            params.append(filters['sqft_min'])
        if 'sqft_max' in filters:
            conditions.append('L_SqFt <= %s')
            params.append(filters['sqft_max'])

        if 'year_built_min' in filters:
            conditions.append('L_YearBuilt >= %s')
            params.append(filters['year_built_min'])
        if 'year_built_max' in filters:
            conditions.append('L_YearBuilt <= %s')
            params.append(filters['year_built_max'])

        if 'lot_size_min_acres' in filters:
            conditions.append('L_LotSizeAcres >= %s')
            params.append(filters['lot_size_min_acres'])
        if 'garage_spaces_min' in filters:
            conditions.append('L_GarageSpaces >= %s')
            params.append(filters['garage_spaces_min'])
        if 'stories' in filters:
            conditions.append('L_Stories = %s')
            params.append(filters['stories'])

        if 'property_type' in filters:
            conditions.append('L_Type = %s')
            params.append(filters['property_type'])
        if 'city' in filters:
            conditions.append('L_City = %s')
            params.append(filters['city'])

        # amenities: value (with % wildcards) is a bound parameter, never SQL text
        for amenity in filters.get('amenities', []):
            conditions.append('L_Remarks LIKE %s')
            params.append(f'%{amenity}%')
        for amenity in filters.get('exclude_amenities', []):
            conditions.append('L_Remarks NOT LIKE %s')
            params.append(f'%{amenity}%')

        where_clause = ' AND '.join(conditions) if conditions else '1=1'
        return f"SELECT * FROM rets_property WHERE {where_clause}", params


class SchemaValidator:

    def __init__(self, schema_path='schema.json'):
        resolved_path = self._resolve_path(schema_path)
        with open(resolved_path) as f:
            self.schema = json.load(f)
        self.valid_cities = self._load_valid_cities()

    def _resolve_path(self, schema_path):
        """Look for schema_path as given, then relative to this script's
        own folder (so it works no matter what directory you run
        `python3` from). Raises FileNotFoundError listing every path
        tried if it truly can't be found -- there is no silent fallback."""
        candidates = [
            schema_path,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), schema_path),
        ]
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
        raise FileNotFoundError(
            f"Could not find '{schema_path}'. Looked in:\n  "
            + "\n  ".join(os.path.abspath(c) for c in candidates)
            + "\nMake sure your schema.json is in one of these locations, "
              "or pass the correct path: SchemaValidator(schema_path='/full/path/to/schema.json')"
        )

    def _load_valid_cities(self):
        return {c.lower() for c in self.schema.get('valid_cities', [])}

    def validate_query(self, filters):
        errors = []

        # Check city exists in database
        if 'city' in filters:
            if filters['city'].lower() not in self.valid_cities:
                errors.append(f"City '{filters['city']}' not found in database")

        # Check price range
        price_range = self.schema.get('ranges', {}).get('price', {})
        if 'price_max' in filters and price_range:
            if filters['price_max'] < price_range['min'] or filters['price_max'] > price_range['max']:
                errors.append(f"Price {filters['price_max']} outside typical range")
        if 'price_min' in filters and price_range:
            if filters['price_min'] < price_range['min'] or filters['price_min'] > price_range['max']:
                errors.append(f"Price {filters['price_min']} outside typical range")

        # Check bedroom count
        bed_range = self.schema.get('ranges', {}).get('bedrooms', {})
        for key in ('bedrooms', 'bedrooms_min', 'bedrooms_max'):
            if key in filters and bed_range:
                if filters[key] < bed_range['min'] or filters[key] > bed_range['max']:
                    errors.append(f"Bedroom count {filters[key]} seems invalid")

        # Check property type / amenities against schema
        if 'property_type' in filters:
            valid_types = self.schema.get('valid_property_types', [])
            if valid_types and filters['property_type'] not in valid_types:
                errors.append(f"Property type '{filters['property_type']}' is not recognized")

        valid_amenities = set(self.schema.get('valid_amenities', []))
        for amenity in filters.get('amenities', []) + filters.get('exclude_amenities', []):
            if valid_amenities and amenity not in valid_amenities:
                errors.append(f"Amenity '{amenity}' is not recognized")

        return len(errors) == 0, errors


# ===========================================================================
# Tests (50+ query examples + SQL injection checks)
# ===========================================================================

CASES = [
    ("3 bed under 700k in Irvine", {"bedrooms": 3, "price_max": 700000, "city": "Irvine"}),
    ("homes under $500,000", {"price_max": 500000}),
    ("condos under 400k", {"price_max": 400000, "property_type": "condo"}),
    ("houses over 300k", {"price_min": 300000, "property_type": "single-family"}),
    ("price between 400k and 600k", {"price_min": 400000, "price_max": 600000}),
    ("400k-600k in Seattle", {"price_min": 400000, "price_max": 600000, "city": "Seattle"}),
    ("at least 300k in Austin", {"price_min": 300000, "city": "Austin"}),
    ("no more than 250k", {"price_max": 250000}),
    ("townhouse below 350k", {"price_max": 350000, "property_type": "townhouse"}),
    ("2 bed starting at 250k", {"bedrooms": 2, "price_min": 250000}),
    ("3 bed in Irvine", {"bedrooms": 3, "city": "Irvine"}),
    ("4br house", {"bedrooms": 4, "property_type": "single-family"}),
    ("5 bedroom home", {"bedrooms": 5}),
    ("3+ bed in Denver", {"bedrooms_min": 3, "city": "Denver"}),
    ("at least 4 bed", {"bedrooms_min": 4}),
    ("up to 3 bed", {"bedrooms_max": 3}),
    ("no more than 2 bed", {"bedrooms_max": 2}),
    ("3 to 5 bed", {"bedrooms_min": 3, "bedrooms_max": 5}),
    ("2-4 bedroom condo", {"bedrooms_min": 2, "bedrooms_max": 4, "property_type": "condo"}),
    ("2 bath house", {"bathrooms": 2.0, "property_type": "single-family"}),
    ("3 bed 2 bath in Portland", {"bedrooms": 3, "bathrooms": 2.0, "city": "Portland"}),
    ("2+ bath", {"bathrooms_min": 2.0}),
    ("at least 2 bath in Miami", {"bathrooms_min": 2.0, "city": "Miami"}),
    ("up to 3 bath", {"bathrooms_max": 3.0}),
    ("1.5 bath condo", {"bathrooms": 1.5, "property_type": "condo"}),
    ("2 to 3 bath house", {"bathrooms_min": 2.0, "bathrooms_max": 3.0}),
    ("over 2000 sqft in Dallas", {"sqft_min": 2000, "city": "Dallas"}),
    ("under 1500 sq ft", {"sqft_max": 1500}),
    ("between 1500 and 2500 sqft", {"sqft_min": 1500, "sqft_max": 2500}),
    ("at least 1800 square feet", {"sqft_min": 1800}),
    ("built after 2000 in Chicago", {"year_built_min": 2000, "city": "Chicago"}),
    ("built before 1990", {"year_built_max": 1990}),
    ("newer than 2010", {"year_built_min": 2010}),
    ("older than 1980", {"year_built_max": 1980}),
    ("half acre lot in Nashville", {"lot_size_min_acres": 0.5, "city": "Nashville"}),
    ("1 acre lot", {"lot_size_min_acres": 1.0}),
    ("2 car garage", {"garage_spaces_min": 2}),
    ("single story home", {"stories": 1}),
    ("two story house", {"stories": 2, "property_type": "single-family"}),
    ("3 bed with pool in Phoenix", {"bedrooms": 3, "amenities": ["pool"], "city": "Phoenix"}),
    ("house with garage and fireplace", {"amenities": ["garage", "fireplace"], "property_type": "single-family"}),
    ("condo with hardwood floors", {"amenities": ["hardwood floors"], "property_type": "condo"}),
    ("waterfront view home", {"amenities": ["waterfront", "view"]}),
    ("3 bed no pool", {"bedrooms": 3, "exclude_amenities": ["pool"]}),
    ("house without garage", {"exclude_amenities": ["garage"], "property_type": "single-family"}),
    ("not gated community", {"exclude_amenities": ["gated community"]}),
    ("single family home in Raleigh", {"property_type": "single-family", "city": "Raleigh"}),
    ("multi-family in Columbus", {"property_type": "multi-family", "city": "Columbus"}),
    ("apartment under 200k", {"property_type": "apartment", "price_max": 200000}),
    ("duplex in Tampa", {"property_type": "duplex", "city": "Tampa"}),
    ("3 bed 2 bath under 700k in Irvine with pool", {
        "bedrooms": 3, "bathrooms": 2.0, "price_max": 700000, "city": "Irvine", "amenities": ["pool"],
    }),
    ("4+ bed house over 500k in Seattle with garage no basement", {
        "bedrooms_min": 4, "property_type": "single-family", "price_min": 500000,
        "city": "Seattle", "amenities": ["garage"], "exclude_amenities": ["basement"],
    }),
    ("condo 2 bath between 300k and 450k built after 2005", {
        "property_type": "condo", "bathrooms": 2.0, "price_min": 300000,
        "price_max": 450000, "year_built_min": 2005,
    }),
    ("2-3 bed townhouse under 600k in Denver with pool and garage", {
        "bedrooms_min": 2, "bedrooms_max": 3, "property_type": "townhouse",
        "price_max": 600000, "city": "Denver", "amenities": ["pool", "garage"],
    }),
    ("single story 3 bed home over 1800 sqft in Austin under 900k", {
        "stories": 1, "bedrooms": 3, "sqft_min": 1800, "city": "Austin", "price_max": 900000,
    }),
]

INJECTION_QUERIES = [
    "3 bed in Irvine'; DROP TABLE rets_property;--",
    "homes in Portland OR 1=1",
    "3 bed under 700k in San Diego' UNION SELECT * FROM users--",
    "house with pool'; DELETE FROM rets_property WHERE '1'='1",
    "3 bed in Chicago\"; DROP TABLE rets_property;--",
]


def _run_case(query, expected):
    result = QueryParser().parse(query)
    for key, value in expected.items():
        assert key in result, f"Missing '{key}' for {query!r} -> got {result}"
        assert result[key] == value, f"Mismatch on '{key}' for {query!r}: expected {value!r}, got {result[key]!r}"


def test_parses_expected_subset():
    for query, expected in CASES:
        _run_case(query, expected)


def test_accuracy_over_90_percent():
    total = correct = 0
    for query, expected in CASES:
        result = QueryParser().parse(query)
        for key, value in expected.items():
            total += 1
            correct += result.get(key) == value
    accuracy = correct / total
    assert accuracy >= 0.90, f"Accuracy {accuracy:.2%} below 90% threshold"


def test_sql_injection_never_reaches_query_text():
    for query in INJECTION_QUERIES:
        filters = QueryParser().parse(query)
        sql, params = QueryParser().to_sql(filters)
        for banned in ("DROP TABLE", "DELETE FROM", "UNION SELECT", "--", ";", "'", '"'):
            assert banned not in sql, f"Unsafe fragment {banned!r} leaked into SQL: {sql}"
        if "city" in filters:
            assert filters["city"] in params


def test_sql_uses_only_parameterized_placeholders():
    filters = QueryParser().parse("3 bed 2 bath under 700k in Irvine with pool")
    sql, params = QueryParser().to_sql(filters)
    for op_match in re.finditer(r"(=|<=|>=|<|>|LIKE|NOT LIKE)\s+(\S+)", sql):
        assert op_match.group(2) == "%s", f"Operator not followed by placeholder: {op_match.group(0)!r}"
    assert sql.count("%s") == len(params)


# --- test fixture: a real schema.json written to a temp file, since
#     SchemaValidator no longer has a built-in default to fall back on ---
import tempfile

_TEST_SCHEMA = {
    "valid_cities": ["Irvine", "Portland", "Seattle", "Denver", "Austin", "Miami"],
    "valid_property_types": ["single-family", "condo", "townhouse", "apartment", "duplex", "multi-family"],
    "valid_amenities": ["pool", "garage", "fireplace", "basement", "waterfront", "view",
                         "hardwood floors", "gated community"],
    "ranges": {
        "price": {"min": 100000, "max": 10000000},
        "bedrooms": {"min": 1, "max": 10},
        "bathrooms": {"min": 1, "max": 10},
    },
}


def _write_test_schema():
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(_TEST_SCHEMA, f)
    return path


def test_schema_validator_rejects_unknown_city():
    path = _write_test_schema()
    try:
        validator = SchemaValidator(schema_path=path)
        valid, errors = validator.validate_query({"city": "Nowhereville"})
        assert not valid
        assert any("Nowhereville" in e for e in errors)
    finally:
        os.remove(path)


def test_schema_validator_accepts_known_city():
    path = _write_test_schema()
    try:
        validator = SchemaValidator(schema_path=path)
        valid, errors = validator.validate_query({"city": "irvine"})
        assert valid
        assert errors == []
    finally:
        os.remove(path)


def test_full_pipeline_example():
    path = _write_test_schema()
    try:
        parser = QueryParser()
        validator = SchemaValidator(schema_path=path)

        filters = parser.parse("3 bed under 700k in Irvine")
        valid, errors = validator.validate_query(filters)
        assert valid, errors

        sql, params = parser.to_sql(filters)
        assert "L_SystemPrice <= %s" in sql
        assert "L_Keyword2 = %s" in sql
        assert "L_City = %s" in sql
        assert 700000 in params and 3 in params and "Irvine" in params
    finally:
        os.remove(path)


def test_schema_validator_raises_clear_error_when_missing():
    try:
        SchemaValidator(schema_path="definitely_does_not_exist_12345.json")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError as e:
        assert "Could not find" in str(e)
        assert "definitely_does_not_exist_12345.json" in str(e)


if __name__ == "__main__":
    passed = failed = 0
    for query, expected in CASES:
        try:
            _run_case(query, expected)
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {e}")
    print(f"\n{passed}/{passed + failed} cases passed ({passed / (passed + failed):.1%})")

    test_sql_injection_never_reaches_query_text()
    test_sql_uses_only_parameterized_placeholders()
    test_schema_validator_rejects_unknown_city()
    test_schema_validator_accepts_known_city()
    test_full_pipeline_example()
    test_schema_validator_raises_clear_error_when_missing()
    print("SQL safety + validation + pipeline tests: OK")

    # Usage example matching the original sample.
    # This uses YOUR schema.json -- put it next to this script (or pass
    # SchemaValidator(schema_path='/full/path/to/schema.json')).
    parser = QueryParser()
    try:
        validator = SchemaValidator()  # looks for ./schema.json, then <script_dir>/schema.json
    except FileNotFoundError as e:
        print(e)
    else:
        filters = parser.parse("3 bed in Portland under 500k")
        valid, errors = validator.validate_query(filters)
        if not valid:
            print(f"Query validation errors: {errors}")
        else:
            sql, params = parser.to_sql(filters)
            print(sql)
            print(params)