import re
import json
import pandas as pd
import math


class EntityExtractor:
    AMENITY_TAXONOMY = [
        # parking / structure
        "two car garage", "three car garage", "attached garage", "detached garage",
        "covered parking", "garage", "carport",
        # outdoor
        "in-ground pool", "swimming pool", "pool", "spa", "sauna", "hot tub",
        "deck", "patio", "rooftop deck", "fenced yard", "sprinkler system",
        "gated community", "waterfront", "lake view", "mountain view", "cul-de-sac",
        "corner lot", "guest house",
        # interior finishes
        "hardwood floors", "granite countertops", "stainless steel appliances",
        "vaulted ceilings", "walk-in closet", "walk-in pantry", "open floor plan",
        "gourmet kitchen", "renovated kitchen", "updated bathroom", "master suite",
        "wine cellar", "fireplace", "crown molding", "bay window",
        # systems
        "air conditioning", "central air", "solar panels", "security system",
        "smart home", "energy efficient", "new roof", "new construction",
        # rooms
        "finished basement", "basement", "home office", "bonus room", "mud room",
        "laundry room", "in-law suite", "great room", "family room",
        # building amenities
        "elevator", "doorman", "concierge",
        # financial / association
        "homeowners association", "washer/dryer",
    ]

    def __init__(self, taxonomy_path='data/processed/taxonomy.json'):
        self.amenity_taxonomy = self._load_amenity_taxonomy(taxonomy_path)

    def _load_amenity_taxonomy(self, taxonomy_path):
        terms = list(self.AMENITY_TAXONOMY)
        try:
            with open(taxonomy_path) as f:
                data = json.load(f)
            extra = data.get('amenities')
            if extra:
                terms.extend(t for t in extra if t not in terms)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        # longest-first so multi-word phrases are checked before their
        # shorter substrings during iteration (see extract_amenities)
        return sorted(set(terms), key=len, reverse=True)

    def extract_bedrooms(self, text):
        patterns = [
            r'(\d+)\s*(?:bed|br|bedroom)s?',
            r'(\d+)bd'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return int(match.group(1))
        return None

    def extract_price(self, text):
        # Assumes cleaned text from Week 2
        match = re.search(r'\$?(\d{5,})', text)
        return int(match.group(1)) if match else None

    def extract_bathrooms(self, text):
        patterns = [
            r'(\d+)\s*(?:ba|bth|bathroom)s?',
            r'(\d+)ba'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return int(match.group(1))
        return None

    def extract_sqft(self, text):
        patterns = [
            r'(\d+)\s*(?:sqft|sq ft|square feet)s?',
            r'(\d+)sqft'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return int(match.group(1))
        return None

    def extract_amenities(self, text):
        if text is None or (isinstance(text, float) and pd.isna(text)):
            return []
        text = str(text)
        found = []
        for term in self.amenity_taxonomy:
            pattern = r'\b' + re.escape(term) + r'\b'
            if re.search(pattern, text, re.I):
                found.append(term)
        return found

    def extract_all(self, text):
        return {
            'bedrooms': self.extract_bedrooms(text),
            'bathrooms': self.extract_bathrooms(text),
            'price': self.extract_price(text),
            'sqft': self.extract_sqft(text),
            'amenities': self.extract_amenities(text)
        }

def is_nan_or_null(val):
    # Check for None (null)
    if val is None:
        return True
    
    # Check for NaN (only applies to float types)
    if isinstance(val, float) and math.isnan(val):
        return True
        
    return False

def process_val(val):
    if is_nan_or_null(val):
        return None
    else:
        return int(val)

if __name__ == "__main__":
    df = pd.read_csv('data/processed/listing_sample_cleaned.csv')
    extractor = EntityExtractor()
    bedroom_pass = 0
    total_bedroom = 0
    bathroom_pass = 0
    total_bathroom = 0
    price_pass = 0
    total_price = 0
    for _, listing in df.iterrows():
        entities = extractor.extract_all(listing['remarks_cleaned'])
        if not is_nan_or_null(entities['bedrooms']):
            total_bedroom += 1
            if process_val(entities['bedrooms']) == process_val(listing['beds']):
                bedroom_pass += 1
        if not is_nan_or_null(entities['bathrooms']):
            total_bathroom += 1
            if process_val(entities['bathrooms']) == process_val(listing['baths']):
                bathroom_pass += 1
        if not is_nan_or_null(entities['price']):
            total_price += 1
            if process_val(entities['price']) == process_val(listing['price']):
                price_pass += 1
    print(bedroom_pass/total_bedroom)
    print(bathroom_pass/total_bathroom)
    print(price_pass/total_price)