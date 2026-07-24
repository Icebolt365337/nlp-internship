import csv
import json
import re

AMENITY_PHRASES = [
    'air conditioning', 'central air', 'hardwood floors', 'updated kitchen',
    'walk-in closet', 'granite countertops', 'stainless steel appliances',
    'gated community', 'solar panels', 'pool', 'garage', 'fireplace',
    'basement', 'waterfront', 'view', 'backyard', 'yard', 'deck', 'patio', 'hoa',
]

PROPERTY_TYPE_KEYWORDS = {
    'single-family': ['single family', 'single-family'],
    'condo': ['condo'],
    'townhouse': ['townhouse', 'town house'],
    'apartment': ['apartment'],
    'duplex': ['duplex'],
    'multi-family': ['multi family', 'multi-family'],
}


def build_schema(csv_path):
    cities = set()
    prices, beds, baths = [], [], []
    amenities_found = set()
    property_types_found = set()

    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            city = (row.get('L_City') or '').strip()
            if city:
                cities.add(city)

            for value, bucket, caster in (
                (row.get('price'), prices, float),
                (row.get('beds'), beds, float),
                (row.get('baths'), baths, float),
            ):
                if value not in (None, ''):
                    try:
                        bucket.append(caster(value))
                    except ValueError:
                        pass

            text = ' '.join([
                row.get('remarks_cleaned') or '',
                row.get('remarks') or '',
            ]).lower()

            for phrase in AMENITY_PHRASES:
                if re.search(r'\b' + re.escape(phrase) + r'\b', text):
                    amenities_found.add(phrase)

            for ptype, keywords in PROPERTY_TYPE_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    property_types_found.add(ptype)

    def range_with_padding(values, floor=None, pad_ratio=0.0, round_to=1):
        if not values:
            return {"min": 0, "max": 0}
        lo, hi = min(values), max(values)
        pad = (hi - lo) * pad_ratio
        lo, hi = lo - pad, hi + pad
        if floor is not None:
            lo = max(lo, floor)
        lo = round(lo / round_to) * round_to
        hi = round(hi / round_to) * round_to
        return {"min": int(lo) if float(lo).is_integer() else lo,
                "max": int(hi) if float(hi).is_integer() else hi}

    schema = {
        "valid_cities": sorted(cities),
        "valid_property_types": sorted(property_types_found) or list(PROPERTY_TYPE_KEYWORDS.keys()),
        "valid_amenities": sorted(amenities_found) or AMENITY_PHRASES,
        "ranges": {
            "price": range_with_padding(prices, floor=0, pad_ratio=0.1, round_to=1000),
            "bedrooms": range_with_padding(beds, floor=0, round_to=1),
            "bathrooms": range_with_padding(baths, floor=0, round_to=0.5),
        },
    }
    return schema


if __name__ == "__main__":
    csv_path = 'data/processed/listing_sample.csv'
    out_path = "data/schema.json"

    schema = build_schema(csv_path)
    with open(out_path, "w") as f:
        json.dump(schema, f, indent=2)

    print(f"Wrote {out_path}")
    print(f"  cities: {len(schema['valid_cities'])}")
    print(f"  property types: {schema['valid_property_types']}")
    print(f"  amenities: {schema['valid_amenities']}")
    print(f"  price range: {schema['ranges']['price']}")
    print(f"  bedroom range: {schema['ranges']['bedrooms']}")
    print(f"  bathroom range: {schema['ranges']['bathrooms']}")