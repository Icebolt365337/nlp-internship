"""
app.py

End-to-end demo UI for the Real Estate NLP API (main.py).

Demo flow (Search tab): natural language query -> parsed filters ->
semantic search results -> per-listing summaries.

Also includes:
- Side-by-side comparison: NLP/semantic search vs. naive keyword-only
  search (a client-side stand-in for "basic SQL search", since that's
  exactly what a plain `WHERE remarks LIKE '%word%'` query amounts to)
  over the same demo listings, to make the value-add visible.
- A metrics dashboard: query volume, latency (from the API's own timing
  where available), and a "satisfaction proxy" -- thumbs up/down on each
  search, since real user satisfaction isn't measurable in a demo.

Run:  streamlit run app.py
Then point it at a running `main.py` API (default http://localhost:8000).

Run tests:  pytest -v app.py   (uses streamlit.testing.v1.AppTest)
"""

import time

import requests
import streamlit as st

# ===========================================================================
# Config
# ===========================================================================

DEFAULT_API_URL = "http://localhost:8000"

# Mirrors main.py's DEMO_LISTINGS so the "keyword-only" comparison has
# something to search against without needing its own API endpoint.
DEMO_LISTINGS = [
    {"id": 1, "city": "Irvine", "remarks": "Charming home with a pool and updated kitchen.", "price": 750000},
    {"id": 2, "city": "Portland", "remarks": "Craftsman with hardwood floors and a fireplace.", "price": 620000},
    {"id": 3, "city": "Denver", "remarks": "Waterfront property with mountain views and a garage.", "price": 910000},
    {"id": 4, "city": "Austin", "remarks": "Contemporary home with solar panels and granite countertops.", "price": 540000},
    {"id": 5, "city": "Seattle", "remarks": "Modern condo with panoramic city views and a balcony.", "price": 480000},
]


# ===========================================================================
# API helpers
# ===========================================================================

def call_api(api_url, endpoint, payload, timeout=15):
    """POSTs to the API and returns (data, latency_ms, error_message)."""
    start = time.perf_counter()
    try:
        resp = requests.post(f"{api_url}{endpoint}", json=payload, timeout=timeout)
        latency_ms = (time.perf_counter() - start) * 1000
        if resp.status_code == 200:
            return resp.json(), latency_ms, None
        return None, latency_ms, f"{resp.status_code}: {resp.json().get('detail', resp.text)}"
    except requests.exceptions.RequestException as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return None, latency_ms, f"Could not reach API at {api_url}: {e}"


def get_api(api_url, endpoint, timeout=10):
    try:
        resp = requests.get(f"{api_url}{endpoint}", timeout=timeout)
        if resp.status_code == 200:
            return resp.json(), None
        return None, f"{resp.status_code}: {resp.text}"
    except requests.exceptions.RequestException as e:
        return None, f"Could not reach API at {api_url}: {e}"


def naive_keyword_search(query, listings, top_k=10):
    """Stand-in for 'basic SQL search': a plain WHERE remarks LIKE
    '%word%' OR city LIKE '%word%' style match -- no understanding of
    price ranges, bed/bath counts, or synonyms. This is what a keyword
    search actually does, on purpose, to make the NLP comparison fair
    and concrete rather than a strawman."""
    words = [w.strip(".,!?").lower() for w in query.split() if len(w) > 2]
    results = []
    for listing in listings:
        haystack = f"{listing['remarks']} {listing['city']}".lower()
        matches = sum(1 for w in words if w in haystack)
        if matches > 0:
            results.append({**listing, "keyword_matches": matches})
    results.sort(key=lambda r: r["keyword_matches"], reverse=True)
    return results[:top_k]


# ===========================================================================
# Session state (demo metrics)
# ===========================================================================

def init_state():
    if "query_count" not in st.session_state:
        st.session_state.query_count = 0
    if "latencies_ms" not in st.session_state:
        st.session_state.latencies_ms = []
    if "satisfaction_up" not in st.session_state:
        st.session_state.satisfaction_up = 0
    if "satisfaction_down" not in st.session_state:
        st.session_state.satisfaction_down = 0


def record_query(latency_ms):
    st.session_state.query_count += 1
    st.session_state.latencies_ms.append(latency_ms)


# ===========================================================================
# App
# ===========================================================================

def main():
    st.set_page_config(page_title="Real Estate Intelligent Search", layout="wide")
    init_state()

    st.sidebar.header("Settings")
    api_url = st.sidebar.text_input("API base URL", DEFAULT_API_URL).rstrip("/")

    health, health_err = get_api(api_url, "/health")
    if health:
        st.sidebar.success("API connected")
        with st.sidebar.expander("Modules loaded"):
            for module, loaded in health["modules_loaded"].items():
                st.write(("✅ " if loaded else "❌ ") + module)
    else:
        st.sidebar.error(f"API unreachable: {health_err}")

    st.title("🏠 Real Estate Intelligent Search")
    st.caption("Natural language query → parsed filters → semantic results → summaries")

    tab_search, tab_compare, tab_metrics = st.tabs(
        ["🔍 Search", "⚖️ NLP vs Keyword", "📊 Metrics Dashboard"]
    )

    # -----------------------------------------------------------------
    # Tab 1: Search (the core demo flow)
    # -----------------------------------------------------------------
    with tab_search:
        query = st.text_input(
            "What are you looking for?",
            "3 bed 2 bath under 700k in Irvine with a pool",
            key="search_query",
        )

        if st.button("Search", type="primary"):
            total_start = time.perf_counter()

            # Step 1: parse the query into structured filters
            parsed, parse_latency, parse_err = call_api(api_url, "/parse-query", {"query": query})
            if parse_err:
                st.error(f"parse-query failed: {parse_err}")
            else:
                st.subheader("1. Parsed filters")
                st.json(parsed["filters"])

            # Step 2: classify intent (bonus signal beyond the base spec)
            intent, intent_latency, intent_err = call_api(api_url, "/classify-intent", {"query": query})
            if intent:
                st.caption(f"Detected intent: **{intent['intent']}** (confidence {intent['confidence']:.0%})")

            # Step 3: semantic search
            search_result, search_latency, search_err = call_api(
                api_url, "/search", {"query": query, "top_k": 10}
            )

            total_latency = (time.perf_counter() - total_start) * 1000
            record_query(total_latency)

            if search_err:
                st.error(f"search failed: {search_err}")
            else:
                st.subheader(f"2. Results ({search_result['count']} found)")
                for listing in search_result["results"]:
                    with st.container(border=True):
                        st.markdown(f"**{listing['city']}** — ${listing['price']:,.0f}  "
                                    f"·  relevance score {listing['score']:.2f}")
                        st.write(listing["remarks"])

                        # Step 4: summarize this specific listing
                        summary_payload = {
                            "remarks": listing["remarks"],
                            "city": listing["city"],
                            "price": listing["price"],
                        }
                        summary, _sum_latency, sum_err = call_api(api_url, "/summarize", summary_payload)
                        if summary:
                            st.info(f"**Summary:** {summary['summary']}")
                        elif sum_err:
                            st.caption(f"(summary unavailable: {sum_err})")

                st.caption(f"Total round-trip: {total_latency:.0f}ms "
                           f"(parse {parse_latency:.0f}ms, search {search_latency:.0f}ms)")

                st.write("Was this helpful?")
                col_up, col_down, _ = st.columns([1, 1, 6])
                if col_up.button("👍", key="up"):
                    st.session_state.satisfaction_up += 1
                    st.success("Thanks for the feedback!")
                if col_down.button("👎", key="down"):
                    st.session_state.satisfaction_down += 1
                    st.info("Thanks — we'll use this to improve results.")

    # -----------------------------------------------------------------
    # Tab 2: NLP vs keyword-only comparison
    # -----------------------------------------------------------------
    with tab_compare:
        st.write(
            "Same query, two approaches: the NLP pipeline (query parsing + "
            "semantic search) vs. a naive keyword match — the equivalent of "
            "a plain `WHERE remarks LIKE '%word%'` SQL search."
        )
        compare_query = st.text_input(
            "Query to compare",
            "3 bed 2 bath under 700k in Irvine with a pool",
            key="compare_query",
        )

        if st.button("Compare"):
            col_nlp, col_keyword = st.columns(2)

            with col_nlp:
                st.subheader("🧠 NLP search")
                nlp_result, nlp_latency, nlp_err = call_api(
                    api_url, "/search", {"query": compare_query, "top_k": 10}
                )
                if nlp_err:
                    st.error(nlp_err)
                else:
                    st.caption(f"{nlp_result['count']} results in {nlp_latency:.0f}ms "
                               f"· filters understood: {nlp_result['filters']}")
                    for listing in nlp_result["results"]:
                        st.write(f"**{listing['city']}** — ${listing['price']:,.0f}")
                        st.caption(listing["remarks"])

            with col_keyword:
                st.subheader("🔤 Keyword-only search")
                kw_start = time.perf_counter()
                kw_results = naive_keyword_search(compare_query, DEMO_LISTINGS)
                kw_latency = (time.perf_counter() - kw_start) * 1000
                st.caption(f"{len(kw_results)} results in {kw_latency:.1f}ms "
                           f"· no understanding of price/bed/bath constraints")
                for listing in kw_results:
                    # a plain keyword match has no idea "$750k" violates
                    # "under 700k" -- it'll happily return over-budget homes
                    st.write(f"**{listing['city']}** — ${listing['price']:,.0f} "
                             f"({listing['keyword_matches']} word matches)")
                    st.caption(listing["remarks"])

                if kw_results and nlp_result and not nlp_err:
                    over_budget = [
                        l for l in kw_results
                        if "price_max" in nlp_result["filters"]
                        and l["price"] > nlp_result["filters"]["price_max"]
                    ]
                    if over_budget:
                        st.warning(
                            f"⚠️ Keyword search returned {len(over_budget)} listing(s) "
                            f"over budget that NLP search correctly filtered out."
                        )

    # -----------------------------------------------------------------
    # Tab 3: Metrics dashboard
    # -----------------------------------------------------------------
    with tab_metrics:
        st.subheader("Demo session metrics")

        col1, col2, col3 = st.columns(3)
        col1.metric("Queries run", st.session_state.query_count)

        avg_latency = (
            sum(st.session_state.latencies_ms) / len(st.session_state.latencies_ms)
            if st.session_state.latencies_ms else 0
        )
        col2.metric("Avg latency", f"{avg_latency:.0f}ms")

        total_votes = st.session_state.satisfaction_up + st.session_state.satisfaction_down
        satisfaction_pct = (
            st.session_state.satisfaction_up / total_votes * 100 if total_votes else None
        )
        col3.metric(
            "Satisfaction (proxy)",
            f"{satisfaction_pct:.0f}%" if satisfaction_pct is not None else "no votes yet",
        )

        if st.session_state.latencies_ms:
            st.write("Latency per query (this session)")
            st.line_chart(st.session_state.latencies_ms)

        st.caption(
            "Note: 'satisfaction' here is a thumbs-up/down proxy collected "
            "during this demo session, not a measure of real user "
            "satisfaction -- that would require production usage data."
        )

        cache_stats, cache_err = get_api(api_url, "/cache-stats")
        if cache_stats:
            st.write("API response cache stats")
            st.json(cache_stats)
        elif cache_err:
            st.caption(f"(cache stats unavailable: {cache_err})")


if __name__ == "__main__":
    main()


# ===========================================================================
# Tests (streamlit.testing.v1.AppTest -- runs the real script, no browser)
# ===========================================================================

def test_app_loads_without_exception():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(__file__)
    at.run()
    assert not at.exception


def test_search_tab_has_expected_widgets():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(__file__)
    at.run()
    assert len(at.text_input) >= 1
    assert len(at.button) >= 1


def test_naive_keyword_search_ignores_price_constraint():
    """Demonstrates exactly the gap the comparison tab is built to show:
    keyword search has no notion of 'under 700k' and will return an
    over-budget listing purely on word overlap."""
    results = naive_keyword_search("home under 700k with a pool", DEMO_LISTINGS)
    irvine = next((r for r in results if r["city"] == "Irvine"), None)
    assert irvine is not None
    assert irvine["price"] == 750000  # over the stated budget, but keyword search doesn't know that


def test_naive_keyword_search_finds_relevant_listings():
    results = naive_keyword_search("pool", DEMO_LISTINGS)
    assert any(r["city"] == "Irvine" for r in results)


def test_call_api_handles_connection_error_gracefully():
    data, latency_ms, error = call_api("http://localhost:1", "/parse-query", {"query": "test"}, timeout=1)
    assert data is None
    assert error is not None
    assert latency_ms >= 0


def test_call_api_against_real_backend_if_available():
    """If a real main.py instance is running at DEFAULT_API_URL, exercise
    the actual integration path instead of just the error-handling path."""
    health, err = get_api(DEFAULT_API_URL, "/health")
    if health is None:
        return  # skip: no live backend in this environment
    data, latency_ms, error = call_api(DEFAULT_API_URL, "/parse-query", {"query": "3 bed in Irvine"})
    assert error is None
    assert data["filters"].get("bedrooms") == 3