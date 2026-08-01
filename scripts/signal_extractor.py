from __future__ import annotations

import re
import json
import os

from entity_extractor import EntityExtractor


DEFAULT_TAXONOMY = {
    "condition": {
        "updated": ["updated", "remodeled", "renovated"],
        "new": ["new construction", "brand new", "newly built"],
        "move_in_ready": ["move-in ready", "move in ready", "turnkey"],
        "needs_work": ["fixer-upper", "needs tlc", "as-is", "handyman special"],
        "well_maintained": ["well-maintained", "well maintained", "pristine condition"],
        "original_condition": ["original condition", "original charm", "untouched"],
    },
    "financing": {
        "seller_financing": ["seller financing", "owner financing", "owner will carry"],
        "assumable_loan": ["assumable loan", "assumable mortgage"],
        "lease_to_own": ["lease to own", "rent to own"],
        "no_money_down": ["no money down", "zero down"],
        "va_approved": ["va approved", "va eligible"],
        "fha_approved": ["fha approved", "fha eligible"],
        "cash_only": ["cash only", "cash buyers only"],
    },
    "location_features": {
        "cul_de_sac": ["cul-de-sac", "cul de sac"],
        "corner_lot": ["corner lot"],
        "near_schools": ["near schools", "walking distance to school", "top rated school district"],
        "near_shopping": ["close to shopping", "near shopping", "walking distance to shops"],
        "quiet_street": ["quiet street", "quiet neighborhood"],
        "near_park": ["near park", "adjacent to park", "steps from the park"],
        "freeway_access": ["freeway access", "easy freeway access", "near the highway"],
        "walkable": ["walkable neighborhood", "walk score", "walkable"],
    },
}


class SignalExtractor:
    def __init__(self, taxonomy=None, entity_extractor=None):
        self.taxonomy = taxonomy if taxonomy is not None else DEFAULT_TAXONOMY
        self.extractor = entity_extractor if entity_extractor is not None else EntityExtractor()

    def extract_signals(self, listing_record):
        remarks = (
            listing_record.get('L_Remarks')
            or listing_record.get('remarks_cleaned')
            or listing_record.get('remarks')
            or ''
        )

        entities = self.extractor.extract_all(remarks)
        amenities = entities.get('amenities', [])

        condition_keywords = self._match_category(remarks, 'condition')
        financing_terms = self._match_category(remarks, 'financing')
        location_features = self._match_category(remarks, 'location_features')

        listing_id = listing_record.get('L_ListingID') or listing_record.get('id')

        return {
            'listing_id': listing_id,
            'entities': entities,
            'amenities': amenities,
            'condition_keywords': condition_keywords,
            'financing_terms': financing_terms,
            'location_features': location_features,
            'keywords': sorted(set(amenities + condition_keywords + financing_terms + location_features)),
        }

    def _match_category(self, remarks, category):
        matched = []
        if not remarks:
            return matched
        text = remarks.lower()
        for tag, phrases in self.taxonomy.get(category, {}).items():
            if any(re.search(r'\b' + re.escape(p) + r'\b', text) for p in phrases):
                matched.append(tag)
        return matched

    def process_table(self, records, output_dir='processed', filename='signals.jsonl'):
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, filename)
        n_written = 0
        with open(out_path, 'w') as f:
            for record in records:
                signals = self.extract_signals(record)
                f.write(json.dumps(signals) + '\n')
                n_written += 1
        return out_path, n_written

    def process_csv(self, csv_path, output_dir='processed', filename='signals.jsonl'):
        import pandas as pd

        df = pd.read_csv(csv_path)
        records = df.to_dict('records')
        return self.process_table(records, output_dir=output_dir, filename=filename)


CASES = [
    ({"L_ListingID": 1, "L_Remarks": "Charming home with a pool and 3 bedrooms, 2 baths."},
     {"entities": {"bedrooms": 3, "bathrooms": 2}, "amenities": ["pool"]}),

    ({"L_ListingID": 2, "L_Remarks": "Updated kitchen, hardwood floors, priced at $650000."},
     {"entities": {"price": 650000}, "amenities": ["hardwood floors"], "condition_keywords": ["updated"]}),

    ({"L_ListingID": 3, "L_Remarks": "Waterfront property built in 1998, 1800 sqft, priced at $650000."},
     {"entities": {"sqft": 1800, "price": 650000}, "amenities": ["waterfront"]}),

    ({"L_ListingID": 4, "L_Remarks": "Seller financing available. Cozy fireplace. Move-in ready."},
     {"financing_terms": ["seller_financing"], "amenities": ["fireplace"], "condition_keywords": ["move_in_ready"]}),

    ({"L_ListingID": 5, "L_Remarks": "Fixer-upper on a corner lot, cash only."},
     {"condition_keywords": ["needs_work"], "location_features": ["corner_lot"],
      "financing_terms": ["cash_only"], "amenities": ["corner lot"]}),

    ({"L_ListingID": 6, "L_Remarks": "5 bed 3 bath home on a corner lot."},
     {"entities": {"bedrooms": 5, "bathrooms": 3}, "location_features": ["corner_lot"]}),

    ({"L_ListingID": 7, "L_Remarks": "Brand new construction with solar panels and a two car garage."},
     {"condition_keywords": ["new"], "amenities": ["new construction", "two car garage", "solar panels", "garage"]}),

    ({"L_ListingID": 8, "L_Remarks": "Gated community, near top rated school district."},
     {"amenities": ["gated community"], "location_features": ["near_schools"]}),

    ({"L_ListingID": 9, "L_Remarks": "VA approved, well-maintained ranch with central air."},
     {"financing_terms": ["va_approved"], "condition_keywords": ["well_maintained"], "amenities": ["central air"]}),

    ({"L_ListingID": 10, "L_Remarks": "Asking $1200000 for this 4 bedroom estate with a granite countertops kitchen."},
     {"entities": {"price": 1200000, "bedrooms": 4}, "amenities": ["granite countertops"]}),

    ({"L_ListingID": 11, "L_Remarks": "Quiet street, walkable neighborhood, near park."},
     {"location_features": ["quiet_street", "walkable", "near_park"]}),

    ({"L_ListingID": 12, "L_Remarks": "Original condition home but has a large basement."},
     {"condition_keywords": ["original_condition"], "amenities": ["basement"]}),

    ({"L_ListingID": 13, "L_Remarks": "Lease to own option available on this stainless steel appliances kitchen."},
     {"financing_terms": ["lease_to_own"], "amenities": ["stainless steel appliances"]}),

    ({"L_ListingID": 14, "L_Remarks": "3 bathrooms, easy freeway access, HOA community."},
     {"entities": {"bathrooms": 3}, "location_features": ["freeway_access"]}),

    ({"L_ListingID": 15, "L_Remarks": "Renovated 2 bed condo with a mountain view and a private deck."},
     {"entities": {"bedrooms": 2}, "condition_keywords": ["updated"], "amenities": ["mountain view", "deck"]}),
]


def _accuracy_for_field(field):
    extractor = SignalExtractor()
    total = correct = 0
    for record, expected in CASES:
        if field not in expected:
            continue
        result = extractor.extract_signals(record)
        exp = expected[field]
        if isinstance(exp, dict):
            for key, value in exp.items():
                total += 1
                correct += result[field].get(key) == value
        else:
            for tag in exp:
                total += 1
                correct += tag in result[field]
    return correct, total


def test_structured_field_accuracy_over_90_percent():
    correct, total = _accuracy_for_field('entities')
    accuracy = correct / total
    assert accuracy >= 0.90, f"Structured field accuracy {accuracy:.1%} below 90% ({correct}/{total})"


def test_free_text_field_accuracy_over_75_percent():
    correct = total = 0
    for field in ('amenities', 'condition_keywords', 'financing_terms', 'location_features'):
        c, t = _accuracy_for_field(field)
        correct += c
        total += t
    accuracy = correct / total
    assert accuracy >= 0.75, f"Free text field accuracy {accuracy:.1%} below 75% ({correct}/{total})"


def test_extract_signals_output_schema():
    extractor = SignalExtractor()
    result = extractor.extract_signals(CASES[0][0])
    for key in ('listing_id', 'entities', 'amenities', 'condition_keywords',
                'financing_terms', 'location_features', 'keywords'):
        assert key in result, f"missing key '{key}' in output schema"
    assert result['listing_id'] == 1


def test_amenities_come_from_entity_extractor_not_duplicated():
    extractor = SignalExtractor()
    result = extractor.extract_signals(CASES[0][0])
    assert result['amenities'] == result['entities']['amenities']


def test_custom_taxonomy_and_entity_extractor_are_injectable():
    custom_taxonomy = {"condition": {}, "financing": {}, "location_features": {"beach": ["beach"]}}

    class StubEntityExtractor:
        def extract_all(self, text):
            return {"bedrooms": 1, "bathrooms": 1, "price": None, "sqft": None, "amenities": ["stub_amenity"]}

    extractor = SignalExtractor(taxonomy=custom_taxonomy, entity_extractor=StubEntityExtractor())
    result = extractor.extract_signals({"L_ListingID": 99, "L_Remarks": "Steps from the beach."})
    assert result['amenities'] == ['stub_amenity']
    assert result['location_features'] == ['beach']


def test_process_table_writes_jsonl():
    import tempfile
    out_dir = tempfile.mkdtemp()
    extractor = SignalExtractor()
    records = [record for record, _ in CASES]
    out_path, n_written = extractor.process_table(records, output_dir=out_dir)

    assert n_written == len(records)
    assert os.path.isfile(out_path)
    with open(out_path) as f:
        lines = f.readlines()
    assert len(lines) == len(records)
    first = json.loads(lines[0])
    assert first['listing_id'] == records[0]['L_ListingID']


def test_missing_remarks_field_handled_gracefully():
    extractor = SignalExtractor()
    result = extractor.extract_signals({"L_ListingID": 1})
    assert result['amenities'] == []
    assert result['condition_keywords'] == []


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

    print("\n=== Example output ===")
    extractor = SignalExtractor()
    example = extractor.extract_signals(CASES[9][0])
    print(json.dumps(example, indent=2))

    print("\n=== Processing rets_property table ===")
    csv_path = 'data/processed/listing_sample_cleaned.csv'
    out_path, n_written = extractor.process_csv(csv_path, output_dir='data/processed')
    print(f"Wrote {n_written} listings to {out_path}")