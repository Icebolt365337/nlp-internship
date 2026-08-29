from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections import defaultdict, deque
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

# ===========================================================================
# Logging
# ===========================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("real_estate_nlp_api")


# ===========================================================================
# Optional module imports -- each NLP capability degrades gracefully if
# its module (or heavy deps like sentence-transformers/torch) isn't
# available in this deployment.
# ===========================================================================

MODULES_LOADED = {}

try:
    from query_parser import QueryParser, SchemaValidator
    MODULES_LOADED['query_parser'] = True
except ImportError as e:
    logger.warning(f"query_parser not available: {e}")
    MODULES_LOADED['query_parser'] = False

try:
    from entity_extractor import EntityExtractor
    MODULES_LOADED['entity_extractor'] = True
except ImportError as e:
    logger.warning(f"entity_extractor not available: {e}")
    MODULES_LOADED['entity_extractor'] = False

try:
    from signal_extractor import SignalExtractor
    MODULES_LOADED['signal_extractor'] = True
except ImportError as e:
    logger.warning(f"signal_extractor not available: {e}")
    MODULES_LOADED['signal_extractor'] = False

try:
    from listing_summarizer import ListingSummarizer, AnswerabilityChecker
    MODULES_LOADED['listing_summarizer'] = True
except ImportError as e:
    logger.warning(f"listing_summarizer not available: {e}")
    MODULES_LOADED['listing_summarizer'] = False

try:
    from compliance_checker import ComplianceChecker
    MODULES_LOADED['compliance_checker'] = True
except ImportError as e:
    logger.warning(f"compliance_checker not available: {e}")
    MODULES_LOADED['compliance_checker'] = False

try:
    from query_intent_classifier import QueryIntentClassifier, LABELED_DATASET
    MODULES_LOADED['query_intent_classifier'] = True
except ImportError as e:
    logger.warning(f"query_intent_classifier not available: {e}")
    MODULES_LOADED['query_intent_classifier'] = False

try:
    from semantic_search import SemanticSearcher, HashingEmbedder
    MODULES_LOADED['semantic_search'] = True
except ImportError as e:
    logger.warning(f"semantic_search not available: {e}")
    MODULES_LOADED['semantic_search'] = False


# ===========================================================================
# Caching -- tries Redis, falls back to an in-memory TTL cache. Same
# injectable/graceful-degradation pattern used throughout this project.
# ===========================================================================

class InMemoryTTLCache:
    def __init__(self):
        self._store: dict[str, tuple[float, Any]] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key):
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del self._store[key]
            self.misses += 1
            return None
        self.hits += 1
        return value

    def set(self, key, value, ttl=60):
        self._store[key] = (time.time() + ttl, value)

    def stats(self):
        total = self.hits + self.misses
        return {
            'backend': 'in-memory',
            'entries': len(self._store),
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': round(self.hits / total, 3) if total else 0.0,
        }


class RedisCache:
    def __init__(self, client):
        self.client = client
        self.hits = 0
        self.misses = 0

    def get(self, key):
        raw = self.client.get(key)
        if raw is None:
            self.misses += 1
            return None
        self.hits += 1
        return json.loads(raw)

    def set(self, key, value, ttl=60):
        self.client.setex(key, ttl, json.dumps(value))

    def stats(self):
        total = self.hits + self.misses
        return {
            'backend': 'redis',
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': round(self.hits / total, 3) if total else 0.0,
        }


def _build_cache():
    redis_url = os.environ.get('REDIS_URL')
    if redis_url:
        try:
            import redis
            client = redis.from_url(redis_url, socket_connect_timeout=1)
            client.ping()
            logger.info("Connected to Redis for response caching.")
            return RedisCache(client)
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}); falling back to in-memory cache.")
    return InMemoryTTLCache()


cache = _build_cache()


def cache_key(endpoint: str, payload: dict) -> str:
    raw = endpoint + json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def cached_response(endpoint: str, payload: dict, compute_fn, ttl=60):
    key = cache_key(endpoint, payload)
    hit = cache.get(key)
    if hit is not None:
        return hit, True
    result = compute_fn()
    cache.set(key, result, ttl=ttl)
    return result, False


# ===========================================================================
# Rate limiting -- 10 requests/second per IP, in-process token bucket.
# For multi-instance deployments behind a load balancer, swap this for a
# shared store (Redis) keyed the same way; the interface stays the same.
# ===========================================================================

RATE_LIMIT_PER_SECOND = 10


class RateLimiter:
    def __init__(self, limit_per_second: int):
        self.limit = limit_per_second
        self.requests: dict[str, deque] = defaultdict(deque)

    def allow(self, client_ip: str) -> bool:
        now = time.time()
        window = self.requests[client_ip]
        while window and now - window[0] > 1.0:
            window.popleft()
        if len(window) >= self.limit:
            return False
        window.append(now)
        return True


rate_limiter = RateLimiter(RATE_LIMIT_PER_SECOND)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.allow(client_ip):
            logger.warning(f"Rate limit exceeded for {client_ip} on {request.url.path}")
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded: {RATE_LIMIT_PER_SECOND} requests/second per IP."},
            )
        return await call_next(request)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        client_ip = request.client.host if request.client else "unknown"
        logger.info(
            f'{client_ip} "{request.method} {request.url.path}" '
            f'{response.status_code} {elapsed_ms:.1f}ms'
        )
        return response


# ===========================================================================
# App setup
# ===========================================================================

app = FastAPI(
    title="Real Estate NLP API",
    description="Search, query parsing, entity extraction, summarization, "
                 "and Fair Housing compliance checking for real estate listings.",
    version="1.0.0",
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(LoggingMiddleware)


# Lazily-initialized singletons for stateful modules (avoid re-training /
# re-encoding on every request).
_state: dict[str, Any] = {}


def get_query_parser():
    if 'query_parser' not in _state:
        _state['query_parser'] = QueryParser()
    return _state['query_parser']


def get_entity_extractor():
    if 'entity_extractor' not in _state:
        _state['entity_extractor'] = EntityExtractor()
    return _state['entity_extractor']


def get_signal_extractor():
    if 'signal_extractor' not in _state:
        _state['signal_extractor'] = SignalExtractor()
    return _state['signal_extractor']


def get_summarizer():
    if 'summarizer' not in _state:
        _state['summarizer'] = ListingSummarizer()
    return _state['summarizer']


def get_compliance_checker():
    if 'compliance_checker' not in _state:
        _state['compliance_checker'] = ComplianceChecker()
    return _state['compliance_checker']


def get_intent_classifier():
    if 'intent_classifier' not in _state:
        clf = QueryIntentClassifier()
        queries = [q for q, _ in LABELED_DATASET]
        labels = [l for _, l in LABELED_DATASET]
        clf.train(queries, labels)
        _state['intent_classifier'] = clf
    return _state['intent_classifier']


DEMO_LISTINGS = [
    {"id": 1, "city": "Irvine", "remarks": "Charming home with a pool and updated kitchen.", "price": 750000},
    {"id": 2, "city": "Portland", "remarks": "Craftsman with hardwood floors and a fireplace.", "price": 620000},
    {"id": 3, "city": "Denver", "remarks": "Waterfront property with mountain views and a garage.", "price": 910000},
    {"id": 4, "city": "Austin", "remarks": "Contemporary home with solar panels and granite countertops.", "price": 540000},
    {"id": 5, "city": "Seattle", "remarks": "Modern condo with panoramic city views and a balcony.", "price": 480000},
]


def get_semantic_searcher():
    if 'semantic_searcher' not in _state:
        try:
            searcher = SemanticSearcher()  # real SentenceTransformer, if reachable
        except Exception as e:
            logger.warning(f"Falling back to HashingEmbedder for search ({e}).")
            searcher = SemanticSearcher(model=HashingEmbedder(dim=384))
        searcher.build_index([l["remarks"] for l in DEMO_LISTINGS])
        _state['semantic_searcher'] = searcher
    return _state['semantic_searcher']


def _unavailable(module_name: str):
    raise HTTPException(
        status_code=503,
        detail=f"'{module_name}' module is not available in this deployment. "
               f"Check GET / for currently loaded modules.",
    )


# ===========================================================================
# Pydantic models
# ===========================================================================

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, examples=["3 bed under 700k in Irvine with a pool"])
    top_k: int = Field(default=10, ge=1, le=50)


class SearchResult(BaseModel):
    listing_id: int
    remarks: str
    city: str
    price: float
    score: float


class SearchResponse(BaseModel):
    query: str
    filters: dict
    results: list[SearchResult]
    count: int
    cached: bool


class ParseQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)


class ParseQueryResponse(BaseModel):
    query: str
    filters: dict
    sql: Optional[str] = None
    params: Optional[list] = None
    cached: bool


class ExtractEntitiesRequest(BaseModel):
    text: str = Field(..., min_length=1)


class ExtractEntitiesResponse(BaseModel):
    text: str
    entities: dict
    cached: bool


class ExtractSignalsRequest(BaseModel):
    listing_id: Optional[int] = None
    remarks: str = Field(..., min_length=1)
    city: Optional[str] = None


class ExtractSignalsResponse(BaseModel):
    signals: dict
    cached: bool


class SummarizeRequest(BaseModel):
    remarks: str = Field(..., min_length=1)
    city: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    price: Optional[float] = None
    amenities: list[str] = Field(default_factory=list)


class SummarizeResponse(BaseModel):
    summary: str
    cached: bool


class ComplianceRequest(BaseModel):
    text: str = Field(..., min_length=1)


class ComplianceResponse(BaseModel):
    compliant: bool
    errors: list[dict]
    warnings: list[dict]
    info: list[dict]
    cached: bool


class IntentRequest(BaseModel):
    query: str = Field(..., min_length=1)


class IntentResponse(BaseModel):
    query: str
    intent: str
    confidence: float
    cached: bool


class HealthResponse(BaseModel):
    status: str
    modules_loaded: dict
    cache_backend: str


# ===========================================================================
# Endpoints
# ===========================================================================

@app.get("/", tags=["meta"])
async def root():
    return {
        "name": "Real Estate NLP API",
        "version": "1.0.0",
        "modules_loaded": MODULES_LOADED,
        "endpoints": [
            "GET  /", "GET  /health", "GET  /cache-stats",
            "POST /search", "POST /parse-query", "POST /extract-entities",
            "POST /extract-signals", "POST /summarize", "POST /check-compliance",
            "POST /classify-intent",
        ],
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthResponse, tags=["meta"])
async def health():
    return HealthResponse(
        status="ok",
        modules_loaded=MODULES_LOADED,
        cache_backend=cache.stats().get('backend', 'unknown'),
    )


@app.get("/cache-stats", tags=["meta"])
async def cache_stats():
    return cache.stats()


@app.post("/parse-query", response_model=ParseQueryResponse, tags=["nlp"])
async def parse_query(request: ParseQueryRequest):
    if not MODULES_LOADED['query_parser']:
        _unavailable('query_parser')

    def compute():
        parser = get_query_parser()
        filters = parser.parse(request.query)
        sql, params = parser.to_sql(filters)
        return {"query": request.query, "filters": filters, "sql": sql, "params": params}

    result, was_cached = cached_response("parse-query", request.model_dump(), compute)
    return ParseQueryResponse(**result, cached=was_cached)


@app.post("/extract-entities", response_model=ExtractEntitiesResponse, tags=["nlp"])
async def extract_entities(request: ExtractEntitiesRequest):
    if not MODULES_LOADED['entity_extractor']:
        _unavailable('entity_extractor')

    def compute():
        entities = get_entity_extractor().extract_all(request.text)
        return {"text": request.text, "entities": entities}

    result, was_cached = cached_response("extract-entities", request.model_dump(), compute)
    return ExtractEntitiesResponse(**result, cached=was_cached)


@app.post("/extract-signals", response_model=ExtractSignalsResponse, tags=["nlp"])
async def extract_signals(request: ExtractSignalsRequest):
    if not MODULES_LOADED['signal_extractor']:
        _unavailable('signal_extractor')

    def compute():
        listing_record = {
            "L_ListingID": request.listing_id,
            "L_City": request.city,
            "L_Remarks": request.remarks,
        }
        signals = get_signal_extractor().extract_signals(listing_record)
        return {"signals": signals}

    result, was_cached = cached_response("extract-signals", request.model_dump(), compute)
    return ExtractSignalsResponse(**result, cached=was_cached)


@app.post("/summarize", response_model=SummarizeResponse, tags=["nlp"])
async def summarize(request: SummarizeRequest):
    if not MODULES_LOADED['listing_summarizer']:
        _unavailable('listing_summarizer')

    def compute():
        listing_record = {"L_City": request.city, "L_Remarks": request.remarks}
        entities = {
            "bedrooms": request.bedrooms, "bathrooms": request.bathrooms,
            "price": request.price, "amenities": request.amenities,
        }
        summary = get_summarizer().summarize(listing_record, entities)
        return {"summary": summary}

    result, was_cached = cached_response("summarize", request.model_dump(), compute)
    return SummarizeResponse(**result, cached=was_cached)


@app.post("/check-compliance", response_model=ComplianceResponse, tags=["nlp"])
async def check_compliance(request: ComplianceRequest):
    if not MODULES_LOADED['compliance_checker']:
        _unavailable('compliance_checker')

    def compute():
        result = get_compliance_checker().check_listing(request.text)
        return {
            "compliant": result["compliant"],
            "errors": result["errors"],
            "warnings": result["warnings"],
            "info": result["info"],
        }

    result, was_cached = cached_response("check-compliance", request.model_dump(), compute)
    return ComplianceResponse(**result, cached=was_cached)


@app.post("/classify-intent", response_model=IntentResponse, tags=["nlp"])
async def classify_intent(request: IntentRequest):
    if not MODULES_LOADED['query_intent_classifier']:
        _unavailable('query_intent_classifier')

    def compute():
        intent, confidence = get_intent_classifier().predict(request.query)
        return {"query": request.query, "intent": intent, "confidence": float(confidence)}

    result, was_cached = cached_response("classify-intent", request.model_dump(), compute)
    return IntentResponse(**result, cached=was_cached)


@app.post("/search", response_model=SearchResponse, tags=["nlp"])
async def search_listings(request: SearchRequest):
    if not MODULES_LOADED['semantic_search']:
        _unavailable('semantic_search')

    def compute():
        filters = {}
        if MODULES_LOADED['query_parser']:
            filters = get_query_parser().parse(request.query)

        searcher = get_semantic_searcher()
        raw_results, _elapsed = searcher.search(request.query, top_k=request.top_k)

        results = []
        for remarks_text, score in raw_results:
            listing = next((l for l in DEMO_LISTINGS if l["remarks"] == remarks_text), None)
            if listing:
                if "city" in filters and listing["city"] != filters["city"]:
                    continue
                if "price_max" in filters and listing["price"] > filters["price_max"]:
                    continue
                if "price_min" in filters and listing["price"] < filters["price_min"]:
                    continue
                results.append({
                    "listing_id": listing["id"], "remarks": listing["remarks"],
                    "city": listing["city"], "price": listing["price"], "score": score,
                })

        return {"query": request.query, "filters": filters, "results": results, "count": len(results)}

    result, was_cached = cached_response("search", request.model_dump(), compute)
    return SearchResponse(**result, cached=was_cached)


# ===========================================================================
# Tests
# ===========================================================================

def _make_client():
    from fastapi.testclient import TestClient
    # Reset rate limiter state between tests -- TestClient reuses the same
    # fake client host ("testclient") for every call in-process, so without
    # this, an earlier test's requests would count against a later test's
    # rate limit budget.
    rate_limiter.requests.clear()
    return TestClient(app)


def test_root_lists_modules():
    client = _make_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert "modules_loaded" in resp.json()


def test_health_endpoint():
    client = _make_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_openapi_docs_generated():
    client = _make_client()
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert "/search" in schema["paths"]
    assert "/parse-query" in schema["paths"]


def test_parse_query_endpoint():
    if not MODULES_LOADED['query_parser']:
        return
    client = _make_client()
    resp = client.post("/parse-query", json={"query": "3 bed under 700k in Irvine"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["filters"]["bedrooms"] == 3
    assert body["filters"]["price_max"] == 700000
    assert body["cached"] is False


def test_parse_query_is_cached_on_second_call():
    if not MODULES_LOADED['query_parser']:
        return
    client = _make_client()
    payload = {"query": "unique cache test query 12345"}
    r1 = client.post("/parse-query", json=payload)
    r2 = client.post("/parse-query", json=payload)
    assert r1.json()["cached"] is False
    assert r2.json()["cached"] is True


def test_extract_entities_endpoint():
    if not MODULES_LOADED['entity_extractor']:
        return
    client = _make_client()
    resp = client.post("/extract-entities", json={"text": "3 bed 2 bath home with a pool."})
    assert resp.status_code == 200
    assert resp.json()["entities"]["bedrooms"] == 3


def test_extract_signals_endpoint():
    if not MODULES_LOADED['signal_extractor']:
        return
    client = _make_client()
    resp = client.post("/extract-signals", json={
        "listing_id": 1, "city": "Irvine",
        "remarks": "Seller financing available. Fixer-upper on a corner lot.",
    })
    assert resp.status_code == 200
    signals = resp.json()["signals"]
    assert "financing_terms" in signals


def test_summarize_endpoint():
    if not MODULES_LOADED['listing_summarizer']:
        return
    client = _make_client()
    resp = client.post("/summarize", json={
        "remarks": "Charming home with a pool and updated kitchen.",
        "city": "Irvine", "bedrooms": 3, "bathrooms": 2, "price": 750000,
        "amenities": ["pool", "updated kitchen"],
    })
    assert resp.status_code == 200
    summary = resp.json()["summary"]
    assert "Irvine" in summary and "3" in summary


def test_check_compliance_endpoint_flags_violation():
    if not MODULES_LOADED['compliance_checker']:
        return
    client = _make_client()
    resp = client.post("/check-compliance", json={"text": "No children allowed, adults only."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["compliant"] is False
    assert len(body["errors"]) > 0


def test_check_compliance_endpoint_passes_clean_text():
    if not MODULES_LOADED['compliance_checker']:
        return
    client = _make_client()
    resp = client.post("/check-compliance", json={"text": "Spacious home with a large backyard."})
    assert resp.status_code == 200
    assert resp.json()["compliant"] is True


def test_classify_intent_endpoint():
    if not MODULES_LOADED['query_intent_classifier']:
        return
    client = _make_client()
    resp = client.post("/classify-intent", json={"query": "show me homes in San Diego"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] in ("browsing", "researching", "high_intent_inquiry")
    assert 0.0 <= body["confidence"] <= 1.0


def test_search_endpoint():
    if not MODULES_LOADED['semantic_search']:
        return
    client = _make_client()
    resp = client.post("/search", json={"query": "home with a pool", "top_k": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 0
    assert len(body["results"]) <= 3


def test_missing_module_returns_503_not_crash():
    client = _make_client()
    original = MODULES_LOADED['compliance_checker']
    MODULES_LOADED['compliance_checker'] = False
    try:
        resp = client.post("/check-compliance", json={"text": "test"})
        assert resp.status_code == 503
    finally:
        MODULES_LOADED['compliance_checker'] = original


def test_request_validation_rejects_empty_text():
    client = _make_client()
    resp = client.post("/check-compliance", json={"text": ""})
    assert resp.status_code == 422  # Pydantic validation error, not a 500


def test_rate_limiting_blocks_excess_requests():
    client = _make_client()
    # burst well past the 10/sec limit from a single client
    statuses = [client.get("/health").status_code for _ in range(25)]
    assert 429 in statuses, "expected at least one 429 once the rate limit is exceeded"
    assert statuses.count(200) <= RATE_LIMIT_PER_SECOND + 2  # small buffer for timing jitter


def test_cache_stats_endpoint():
    client = _make_client()
    resp = client.get("/cache-stats")
    assert resp.status_code == 200
    assert "hits" in resp.json() or "backend" in resp.json()


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
            except Exception as e:
                failed += 1
                print(f"  ERROR: {name}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{passed + failed} tests passed")
    print(f"\nModules loaded: {MODULES_LOADED}")
    print("\nTo run the API: uvicorn main:app --reload")
    print("Then visit: http://localhost:8000/docs")