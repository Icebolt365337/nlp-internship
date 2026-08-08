from __future__ import annotations

import random
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score


class QueryIntentClassifier:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(max_features=500, ngram_range=(1, 2))
        self.model = LogisticRegression(max_iter=1000)
        self.labels = [
            'browsing',
            'researching',
            'high_intent_inquiry'
        ]

    def train(self, queries, labels):
        X = self.vectorizer.fit_transform(queries)
        self.model.fit(X, labels)

    def predict(self, query):
        X = self.vectorizer.transform([query])
        probas = self.model.predict_proba(X)[0]
        classes = self.model.classes_
        best_idx = probas.argmax()
        intent = classes[best_idx]
        confidence = probas.max()
        return intent, confidence

    def predict_with_scores(self, query):
        X = self.vectorizer.transform([query])
        probas = self.model.predict_proba(X)[0]
        classes = self.model.classes_
        scores = dict(zip(classes, probas))
        best_idx = probas.argmax()
        return classes[best_idx], probas.max(), scores

    def classify_and_parse(self, query, query_parser=None):
        intent, confidence = self.predict(query)
        filters = {}
        if query_parser is None:
            try:
                from query_parser import QueryParser
                query_parser = QueryParser()
            except ImportError:
                query_parser = None
        if query_parser is not None:
            filters = query_parser.parse(query)
        return {
            'query': query,
            'intent': intent,
            'confidence': float(confidence),
            'filters': filters,
        }


CITIES = ["San Diego", "Irvine", "Beverly Hills", "Austin", "Denver", "Seattle",
          "Portland", "Miami", "Chicago", "Raleigh", "Nashville", "Tampa"]
PRICES = ["500k", "700k", "900k", "1.2m", "1.5m", "2m"]

BROWSING_TEMPLATES = [
    "show me homes in {city}",
    "homes with pools in {city}",
    "luxury homes in {city}",
    "browse listings in {city}",
    "what homes are available in {city}",
    "houses for sale in {city}",
    "condos in {city}",
    "apartments in {city}",
    "nice houses in {city}",
    "homes with a view in {city}",
    "waterfront homes in {city}",
    "big houses in {city}",
    "homes with a garage in {city}",
    "family homes in {city}",
    "townhomes in {city}",
    "show me some houses",
    "any nice homes around {city}",
    "homes for sale near me",
    "cool houses in {city}",
    "just looking at homes in {city}",
]

RESEARCHING_TEMPLATES = [
    "condos near UC Irvine with low HOA",
    "areas in {city} with low property taxes",
    "best neighborhoods in {city} for families",
    "average home price in {city}",
    "school district ratings in {city}",
    "is now a good time to buy in {city}",
    "real estate market trends in {city}",
    "property tax rates in {city}",
    "cost of living comparison {city} vs {city2}",
    "how much do homes appreciate in {city}",
    "walkability score for neighborhoods in {city}",
    "crime rate by neighborhood in {city}",
    "best school districts near {city}",
    "HOA fees comparison in {city}",
    "housing market forecast for {city}",
    "difference between renting and buying in {city}",
    "what is the median home price in {city}",
    "which neighborhoods in {city} are up and coming",
    "how do property taxes work in {city}",
    "is {city} a buyer's market right now",
]

HIGH_INTENT_TEMPLATES = [
    "move-in ready homes in {city} under {price}",
    "homes available this weekend with open houses",
    "new listings in {city} under {price} with seller financing",
    "schedule a tour for homes in {city}",
    "homes in {city} under {price} ready to close",
    "open houses this weekend in {city}",
    "contact agent about homes in {city}",
    "pre-approved buyer looking for homes in {city} under {price}",
    "must see homes in {city} before they're gone",
    "how do I make an offer on a home in {city}",
    "motivated seller homes in {city}",
    "homes in {city} that close quickly",
    "ready to buy a home in {city} under {price}",
    "book a showing for homes in {city}",
    "new listings this week in {city}",
    "homes in {city} under {price} with no HOA, need to move fast",
    "urgent: need a home in {city} under {price} by next month",
    "homes with seller financing available now in {city}",
    "schedule a walkthrough for {city} listings",
    "get me in touch with a realtor in {city}",
]


def _generate_dataset(seed=13):
    rng = random.Random(seed)
    dataset = []

    for template in BROWSING_TEMPLATES:
        for city in CITIES:
            dataset.append((template.format(city=city), 'browsing'))

    for template in RESEARCHING_TEMPLATES:
        for city in CITIES:
            city2 = rng.choice([c for c in CITIES if c != city])
            dataset.append((template.format(city=city, city2=city2), 'researching'))

    for template in HIGH_INTENT_TEMPLATES:
        for city in CITIES:
            price = rng.choice(PRICES)
            dataset.append((template.format(city=city, price=price), 'high_intent_inquiry'))

    rng.shuffle(dataset)
    return dataset


LABELED_DATASET = _generate_dataset()

# A small, hand-written "clean" eval set separate from the generated
# training data -- these paraphrase the categories using DIFFERENT
# wording than the templates above, so accuracy on these is a better
# signal of generalization than accuracy on held-out generated queries.
HAND_LABELED_EVAL = [
    ("browse houses for sale in Irvine", "browsing"),
    ("show me some nice condos", "browsing"),
    ("what's out there in San Diego right now", "browsing"),
    ("looking at homes with a pool", "browsing"),
    ("houses in Denver with a big yard", "browsing"),
    ("what's the going rate for homes in Austin", "researching"),
    ("which Seattle neighborhoods have the best schools", "researching"),
    ("comparing property taxes between Tampa and Miami", "researching"),
    ("is Portland a good market to invest in", "researching"),
    ("how competitive is the Raleigh housing market", "researching"),
    ("I need to see this house today", "high_intent_inquiry"),
    ("can I book a viewing for tomorrow", "high_intent_inquiry"),
    ("ready to make an offer on a home in Nashville", "high_intent_inquiry"),
    ("please connect me with an agent asap", "high_intent_inquiry"),
    ("looking to close on a home in Chicago this month", "high_intent_inquiry"),
]

assert len(LABELED_DATASET) >= 200, f"only {len(LABELED_DATASET)} generated"


def test_train_and_predict_basic():
    queries = [q for q, _ in LABELED_DATASET]
    labels = [l for _, l in LABELED_DATASET]
    clf = QueryIntentClassifier()
    clf.train(queries, labels)

    intent, confidence = clf.predict("homes with open houses this weekend")
    assert intent in clf.labels
    assert 0.0 <= confidence <= 1.0


def test_dataset_has_200_plus_labeled_queries():
    assert len(LABELED_DATASET) >= 200


def test_dataset_covers_all_three_labels():
    labels_present = {label for _, label in LABELED_DATASET}
    assert labels_present == {'browsing', 'researching', 'high_intent_inquiry'}


def test_held_out_accuracy_over_80_percent():
    queries = [q for q, _ in LABELED_DATASET]
    labels = [l for _, l in LABELED_DATASET]

    X_train, X_test, y_train, y_test = train_test_split(
        queries, labels, test_size=0.2, random_state=42, stratify=labels
    )

    clf = QueryIntentClassifier()
    clf.train(X_train, y_train)

    predictions = [clf.predict(q)[0] for q in X_test]
    accuracy = accuracy_score(y_test, predictions)
    assert accuracy >= 0.80, f"held-out accuracy {accuracy:.1%} below 80% target"


def test_generalization_on_hand_labeled_eval_set():
    """Accuracy on differently-worded, hand-labeled queries -- a stricter,
    more honest check of generalization than held-out generated queries."""
    queries = [q for q, _ in LABELED_DATASET]
    labels = [l for _, l in LABELED_DATASET]
    clf = QueryIntentClassifier()
    clf.train(queries, labels)

    eval_queries = [q for q, _ in HAND_LABELED_EVAL]
    eval_labels = [l for _, l in HAND_LABELED_EVAL]
    predictions = [clf.predict(q)[0] for q in eval_queries]
    accuracy = accuracy_score(eval_labels, predictions)
    print(f"\n  hand-labeled eval accuracy: {accuracy:.1%}")
    assert accuracy >= 0.50, f"generalization accuracy {accuracy:.1%} suspiciously low"


def test_confidence_scores_sum_to_one_across_classes():
    queries = [q for q, _ in LABELED_DATASET]
    labels = [l for _, l in LABELED_DATASET]
    clf = QueryIntentClassifier()
    clf.train(queries, labels)

    _, _, scores = clf.predict_with_scores("homes in Irvine under 900k with seller financing")
    total = sum(scores.values())
    assert abs(total - 1.0) < 1e-6


def test_clear_high_intent_query_gets_high_intent_label():
    queries = [q for q, _ in LABELED_DATASET]
    labels = [l for _, l in LABELED_DATASET]
    clf = QueryIntentClassifier()
    clf.train(queries, labels)

    intent, confidence = clf.predict("move-in ready homes in San Diego under 1.2m, need to close this month")
    assert intent == 'high_intent_inquiry'


def test_classify_and_parse_integration_degrades_gracefully_without_parser():
    """If query_parser.py isn't importable, classify_and_parse should
    still return intent/confidence with empty filters, not crash."""
    queries = [q for q, _ in LABELED_DATASET]
    labels = [l for _, l in LABELED_DATASET]
    clf = QueryIntentClassifier()
    clf.train(queries, labels)

    result = clf.classify_and_parse("3 bed under 700k in Irvine")
    assert 'intent' in result and 'confidence' in result and 'filters' in result
    assert isinstance(result['filters'], dict)


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

    print("\n=== Example usage ===")
    queries = [q for q, _ in LABELED_DATASET]
    labels = [l for _, l in LABELED_DATASET]
    classifier = QueryIntentClassifier()
    classifier.train(queries, labels)

    for q in [
        "show me homes in San Diego",
        "condos near UC Irvine with low HOA",
        "move-in ready homes in San Diego under 1.2m",
        "homes with open houses this weekend",
    ]:
        intent, confidence = classifier.predict(q)
        print(f"  {q!r} -> {intent} ({confidence:.2f})")