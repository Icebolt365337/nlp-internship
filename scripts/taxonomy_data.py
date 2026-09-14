"""
taxonomy_data.py
------------------
Curated real-estate taxonomy: 208 terms across 8 categories, built from
domain knowledge (not corpus bigram frequency -- see taxonomy.py docstring
for why that distinction matters).

Imported by taxonomy.py. Edit this file to add/remove/rename terms or
categories; taxonomy.py's logic and tests don't need to change.
"""

TAXONOMY = {
    "property_types": [
        "single family home", "condominium", "townhouse", "duplex", "triplex",
        "multi-family", "co-op", "mobile home", "manufactured home", "farm",
        "ranch", "bungalow", "colonial", "victorian", "craftsman", "cape cod",
        "split-level", "contemporary", "mid-century modern", "tudor",
        "mediterranean", "industrial loft", "high-rise", "low-rise",
        "penthouse", "studio", "in-law suite", "guest house",
        "new construction", "vacant land",
    ],
    "rooms_and_spaces": [
        "bedroom", "bathroom", "bath", "kitchen", "living room", "dining room",
        "family room", "great room", "master suite", "primary suite",
        "primary bedroom", "home office", "den", "sitting area",
        "library", "sunroom", "sun room", "mudroom", "laundry room",
        "laundry area", "walk-in closet", "walk-in pantry", "basement",
        "finished basement", "attic", "loft", "storage room",
        "bonus room", "game room", "media room", "wine cellar", "workshop",
        "recreation room",
        "garage", "carport", "foyer", "powder room", "breakfast nook",
        "dining area", "living area", "living space",
    ],
    "amenities_and_features": [
        "swimming pool", "pool", "hot tub", "sauna", "fireplace", "deck", "patio",
        "balcony", "rooftop deck", "garden", "fenced yard",
        "sprinkler system", "security system", "smart home", "solar panels",
        "central air", "elevator", "wheelchair accessible",
        "gated community", "tennis court", "playground", "clubhouse", "gym",
        "doorman", "concierge", "storage unit", "guest parking",
        "covered parking", "ev charging station", "outdoor kitchen",
        "outdoor living", "outdoor space", "outdoor dining", "outdoor shower",
        "wet bar",
    ],
    "finishes_and_materials": [
        "hardwood floors", "granite countertops", "marble countertops",
        "quartz countertops", "stainless steel appliances", "tile flooring",
        "carpet", "crown molding", "vaulted ceilings", "exposed beams",
        "exposed brick", "bay window", "french doors", "sliding glass doors",
        "custom cabinetry", "built-in shelving", "recessed lighting",
        "skylight", "wainscoting", "stone fireplace", "coffered ceiling",
        "farmhouse sink", "shiplap", "board and batten", "subway tile",
    ],
    "financial_and_legal": [
        "homeowners association", "hoa fees", "property taxes", "escrow",
        "closing costs", "earnest money", "mortgage", "pre-approval",
        "contingency", "title insurance", "deed", "easement", "zoning",
        "variance", "lien", "appraisal", "listing agreement",
        "buyer's agent", "seller's agent", "commission", "short sale",
        "foreclosure", "as-is", "disclosure", "survey", "covenant",
        "capital gains", "1031 exchange", "special assessment", "quitclaim deed",
    ],
    "location_and_neighborhood": [
        "waterfront", "lakefront", "oceanfront", "mountain view", "view",
        "cul-de-sac", "corner lot", "walkable", "school district",
        "near transit", "downtown", "suburban", "rural", "private drive",
        "golf course community", "quiet street", "flood zone", "backyard",
        "freeway access", "main floor", "first floor", "second floor",
        "ground floor", "main level",
        "historic district", "master-planned community", "commuter friendly",
        "cul-de-sac lot", "greenbelt", "adjacent to park",
    ],
    "condition_and_style": [
        "move-in ready", "fixer-upper", "newly renovated", "updated",
        "remodeled", "turnkey", "pristine condition", "needs tlc",
        "original condition", "historic", "charming", "modern", "luxury",
        "custom-built", "energy efficient", "eco-friendly", "spacious",
        "private", "floor plan", "open floor plan", "split floor plan",
        "vintage character",
        "as-built", "well maintained", "recently painted",
    ],
    "systems_and_utilities": [
        "central air conditioning", "forced air heating", "radiant heat",
        "heat pump", "tankless water heater", "septic system", "well water",
        "public sewer", "natural gas", "solar water heater", "generator",
        "water softener", "sump pump", "hvac", "ductwork",
        "smart thermostat", "fiber internet", "backup generator",
        "irrigation system",
    ],
}