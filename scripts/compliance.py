from __future__ import annotations
import re

PATTERN_LIBRARY = {
    "familial_status": [
        ("no children", "error", "Direct familial status exclusion."),
        ("no kids", "error", "Direct familial status exclusion."),
        ("adults only", "error", "Familial status exclusion."),
        ("adults preferred", "error", "Familial status preference/exclusion."),
        ("childless", "error", "Familial status exclusion."),
        ("perfect for singles", "warning", "Can imply familial status steering; review context."),
        ("ideal for couples", "warning", "Can imply familial status steering; review context."),
        ("empty nesters", "warning", "Can imply familial status preference; review context."),
        ("mature community", "warning", "Can imply age/familial status preference; review context."),
        ("no daycares", "error", "Familial status exclusion."),
    ],
    "disability": [
        ("no wheelchairs", "error", "Direct disability exclusion."),
        ("must be able-bodied", "error", "Disability exclusion."),
        ("able bodied only", "error", "Disability exclusion."),
        ("no handicapped", "error", "Disability exclusion."),
        ("not wheelchair accessible", "info", "Factual accessibility statement; usually fine, but review phrasing."),
        ("no service animals", "error", "Disability accommodation violation."),
        ("do not allow service animals", "error", "Disability accommodation violation."),
        ("does not allow service animals", "error", "Disability accommodation violation."),
        ("must be physically fit", "warning", "Can imply disability exclusion; review context."),
        ("sound mind required", "error", "Mental disability exclusion."),
        ("of sound mind", "error", "Mental disability exclusion."),
    ],
    "race_color": [
        ("whites only", "error", "Direct race exclusion."),
        ("white neighborhood", "error", "Race steering."),
        ("blacks only", "error", "Direct race exclusion."),
        ("no minorities", "error", "Race exclusion."),
        ("ethnic", "warning", "Vague racial/ethnic descriptor; review context and intent."),
        ("diverse area", "warning", "Can function as coded racial steering; review context."),
        ("integrated neighborhood", "warning", "HUD-flagged coded racial language; review context."),
        ("exclusive neighborhood", "warning", "Can imply racial/class exclusion; review context."),
        ("gated and secure from outsiders", "warning", "Can imply exclusionary intent; review context."),
    ],
    "religion": [
        ("christian community", "error", "Religious preference/steering."),
        ("jewish neighborhood", "error", "Religious steering."),
        ("no muslims", "error", "Direct religious exclusion."),
        ("church-going family", "error", "Religious preference."),
        ("walking distance to church", "warning", "Can imply religious steering; review context."),
        ("near synagogue", "warning", "Can imply religious steering; review context."),
        ("near mosque", "warning", "Can imply religious steering; review context."),
        ("bible study nearby", "warning", "Can imply religious preference; review context."),
    ],
    "national_origin": [
        ("no foreigners", "error", "National origin exclusion."),
        ("americans only", "error", "National origin exclusion."),
        ("must speak english", "error", "National origin discrimination (language requirement)."),
        ("legal citizens only", "error", "National origin/citizenship exclusion."),
        ("english speaking preferred", "error", "National origin discrimination."),
    ],
    "sex": [
        ("male only", "error", "Sex-based exclusion."),
        ("female only", "error", "Sex-based exclusion."),
        ("men preferred", "error", "Sex-based preference."),
        ("women preferred", "error", "Sex-based preference."),
        ("bachelor pad", "info", "Gendered framing; usually fine as a style description, but review context."),
    ],
    "steering_general": [
        ("safe neighborhood", "info", "Common HUD-flagged coded phrase; frequently legitimate, but be aware."),
        ("desirable neighborhood", "info", "Common HUD-flagged coded phrase; frequently legitimate, but be aware."),
        ("up and coming area", "info", "Can carry coded meaning about neighborhood demographics; review context."),
        ("traditional neighborhood", "info", "HUD-flagged coded phrase; review context."),
        ("prestigious area", "info", "Can imply exclusionary intent; review context."),
    ],
}


class ComplianceChecker:
    def __init__(self, pattern_library=None):
        self.pattern_library = pattern_library if pattern_library is not None else PATTERN_LIBRARY
        # kept for structural parity with the original sample (category -> flat term list)
        self.prohibited_patterns = {
            category: [p for p, _, _ in patterns]
            for category, patterns in self.pattern_library.items()
        }

    def check_listing(self, text):
        violations = []
        text_lower = (text or "").lower()

        for category, patterns in self.pattern_library.items():
            for pattern, severity, note in patterns:
                if re.search(r'\b' + re.escape(pattern) + r'\b', text_lower):
                    violations.append({
                        'category': category,
                        'pattern': pattern,
                        'severity': severity,
                        'message': f'Prohibited language: "{pattern}" ({category.replace("_", " ")}) - {note}',
                    })

        errors = [v for v in violations if v['severity'] == 'error']
        warnings = [v for v in violations if v['severity'] == 'warning']
        info = [v for v in violations if v['severity'] == 'info']

        return {
            'compliant': len(errors) == 0,  # errors block publication; warnings/info do not
            'violations': violations,
            'errors': errors,
            'warnings': warnings,
            'info': info,
            'summary': {'errors': len(errors), 'warnings': len(warnings), 'info': len(info)},
        }


# ===========================================================================
# Integration example: listing submission workflow
# ===========================================================================

def submit_listing(listing_text, checker=None, listing_id=None):
    """Example of wiring ComplianceChecker into a listing submission
    endpoint. Errors block publication outright; warnings require a
    human review step before going live; info is logged but doesn't
    block anything."""
    checker = checker or ComplianceChecker()
    result = checker.check_listing(listing_text)

    if result['errors']:
        return {
            'status': 'rejected',
            'listing_id': listing_id,
            'reason': 'Fair Housing Act violation(s) must be fixed before publishing.',
            'errors': [v['message'] for v in result['errors']],
        }

    if result['warnings']:
        return {
            'status': 'pending_review',
            'listing_id': listing_id,
            'reason': 'Listing contains language that requires human review before publishing.',
            'warnings': [v['message'] for v in result['warnings']],
            'info': [v['message'] for v in result['info']],
        }

    return {
        'status': 'published',
        'listing_id': listing_id,
        'info': [v['message'] for v in result['info']],
    }


KNOWN_VIOLATIONS = [
    ("Charming 3 bed home, no children please.", "familial_status"),
    ("Cozy studio, adults only building.", "familial_status"),
    ("This unit is childless and quiet.", "familial_status"),
    ("Perfect for singles looking to start out.", "familial_status"),
    ("Great for empty nesters downsizing.", "familial_status"),
    ("Sorry, no wheelchairs can be accommodated here.", "disability"),
    ("Tenant must be able-bodied to apply.", "disability"),
    ("We do not allow service animals of any kind.", "disability"),
    ("Applicants must be of sound mind to qualify.", "disability"),
    ("Beautiful home in a white neighborhood.", "race_color"),
    ("No minorities will be considered for this rental.", "race_color"),
    ("A very ethnic part of town.", "race_color"),
    ("Truly a diverse area to explore.", "race_color"),
    ("Located in a lovely christian community.", "religion"),
    ("This is a jewish neighborhood through and through.", "religion"),
    ("We prefer a church-going family in this home.", "religion"),
    ("Walking distance to church for Sunday service.", "religion"),
    ("Sorry, no foreigners will be considered.", "national_origin"),
    ("Americans only need apply for this lease.", "national_origin"),
    ("Tenant must speak english fluently.", "national_origin"),
    ("Looking for legal citizens only.", "national_origin"),
    ("This unit is male only, no exceptions.", "sex"),
    ("Female only applicants will be considered.", "sex"),
    ("Men preferred for this shared housing situation.", "sex"),
    ("Located in a very exclusive neighborhood.", "race_color"),
    ("An integrated neighborhood close to downtown.", "race_color"),
]

CLEAN_LISTINGS = [
    "Spacious 3 bed 2 bath home with a large backyard and updated kitchen.",
    "This condo features hardwood floors, a private balcony, and in-unit laundry.",
    "Beautiful craftsman with a cozy fireplace and a two car garage.",
    "Move-in ready home with granite countertops and stainless steel appliances.",
    "Waterfront property with stunning views and a finished basement.",
    "Newly renovated kitchen with custom cabinetry and a large island.",
    "This home includes central air, a fenced yard, and a covered patio.",
    "Located near shopping, parks, and public transit.",
    "Open floor plan with vaulted ceilings and abundant natural light.",
    "Community pool, clubhouse, and fitness center included with HOA.",
    "Freshly painted interior with new carpet throughout.",
    "Solar panels installed in 2022 for energy efficiency.",
    "Quiet cul-de-sac location with mature trees.",
    "Three bedroom townhouse with attached garage and private patio.",
    "Recently updated bathrooms with new fixtures and tile work.",
    "This property offers a gourmet kitchen and a formal dining room.",
    "Convenient access to major highways and the airport.",
    "Large primary suite with a walk-in closet and en-suite bath.",
]


def _is_flagged(result):
    return len(result['errors']) > 0 or len(result['warnings']) > 0


def _evaluate_recall_precision(checker):
    tp = 0  # known violations correctly flagged
    fn = 0  # known violations missed
    fp = 0  # clean listings incorrectly flagged

    for text, _category in KNOWN_VIOLATIONS:
        result = checker.check_listing(text)
        if _is_flagged(result):
            tp += 1
        else:
            fn += 1

    for text in CLEAN_LISTINGS:
        result = checker.check_listing(text)
        if _is_flagged(result):
            fp += 1

    recall = tp / (tp + fn) if (tp + fn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    return recall, precision, tp, fn, fp


# ===========================================================================
# Tests
# ===========================================================================

def test_recall_is_100_percent_on_known_violations():
    checker = ComplianceChecker()
    recall, precision, tp, fn, fp = _evaluate_recall_precision(checker)
    assert recall == 1.0, f"recall {recall:.1%} below 100% -- missed {fn} known violation(s)"


def test_precision_over_80_percent():
    checker = ComplianceChecker()
    recall, precision, tp, fn, fp = _evaluate_recall_precision(checker)
    assert precision > 0.80, f"precision {precision:.1%} below 80% target (tp={tp}, fp={fp})"


def test_severity_levels_are_multi_tier():
    checker = ComplianceChecker()
    severities_seen = set()
    for text, _ in KNOWN_VIOLATIONS:
        result = checker.check_listing(text)
        for v in result['violations']:
            severities_seen.add(v['severity'])
    for cat, patterns in PATTERN_LIBRARY.items():
        for _, severity, _ in patterns:
            severities_seen.add(severity)
    assert severities_seen == {'error', 'warning', 'info'}


def test_compliant_flag_only_reflects_errors():
    checker = ComplianceChecker()
    # a warning-only text should still report compliant=True (needs
    # review, but isn't an automatic block)
    result = checker.check_listing("Perfect for singles looking to start out.")
    assert result['errors'] == []
    assert len(result['warnings']) > 0
    assert result['compliant'] is True

    # an error-level text must report compliant=False
    result = checker.check_listing("Adults only, no children.")
    assert result['compliant'] is False


def test_case_insensitive_matching():
    checker = ComplianceChecker()
    result = checker.check_listing("NO CHILDREN allowed in this unit.")
    assert result['compliant'] is False


def test_no_false_match_on_substring():
    """'ethnic' should not falsely match inside an unrelated word."""
    checker = ComplianceChecker()
    result = checker.check_listing("This home has authentically designed features.")
    categories_hit = {v['category'] for v in result['violations']}
    assert 'race_color' not in categories_hit


def test_submit_listing_rejects_on_error():
    result = submit_listing("No children allowed, adults only building.", listing_id=1)
    assert result['status'] == 'rejected'
    assert len(result['errors']) > 0


def test_submit_listing_pending_review_on_warning_only():
    result = submit_listing("Perfect for singles, walking distance to church.", listing_id=2)
    assert result['status'] == 'pending_review'
    assert len(result['warnings']) > 0


def test_submit_listing_publishes_clean_text():
    result = submit_listing("Spacious 3 bed home with a large backyard.", listing_id=3)
    assert result['status'] == 'published'


def test_custom_pattern_library_is_injectable():
    custom_library = {"custom_cat": [("no pets allowed under any circumstance", "error", "test")]}
    checker = ComplianceChecker(pattern_library=custom_library)
    result = checker.check_listing("Sorry, no pets allowed under any circumstance.")
    assert result['compliant'] is False
    assert result['violations'][0]['category'] == 'custom_cat'


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

    checker = ComplianceChecker()
    recall, precision, tp, fn, fp = _evaluate_recall_precision(checker)
    print(f"\nRecall: {recall:.1%} (target 100%)")
    print(f"Precision: {precision:.1%} (target >80%)  [tp={tp}, fn={fn}, fp={fp}]")

    print("\n=== Example: listing submission workflow ===")
    examples = [
        ("Charming 3 bed home, no children please.", "clear violation"),
        ("Perfect for singles, walking distance to church.", "warning-level, needs review"),
        ("Spacious 3 bed 2 bath home with a large backyard and updated kitchen.", "clean listing"),
    ]
    for text, label in examples:
        result = submit_listing(text, listing_id=hash(text) % 1000)
        print(f"\n  [{label}] {text!r}")
        print(f"    -> {result}")