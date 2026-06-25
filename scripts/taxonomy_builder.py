import json
import nltk
from collections import Counter
from nltk.util import ngrams
import pandas as pd

df = pd.read_csv('data/processed/listing_sample.csv')

# Extract bigrams from remarks
all_text = ' '.join(df['remarks'].dropna().str.lower())
tokens = nltk.word_tokenize(all_text)
bigrams = list(ngrams(tokens, 2))
freq = Counter(bigrams)

# Top 200 bigrams become taxonomy seed
top_bigrams = freq.most_common(200)

terms = [
    {"id": i, "term": " ".join(bigram), "count": count}
    for i, (bigram, count) in enumerate(top_bigrams)
]

for entry in terms:
    print(f"{entry['term']}: {entry['count']}")

taxonomy = {"terms": terms}

with open('data/processed/taxonomy.json', 'w') as f:
    json.dump(taxonomy, f, indent=2)

print(f"\nSaved {len(terms)} taxonomy terms to data/processed/taxonomy.json")