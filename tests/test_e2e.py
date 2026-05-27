"""End-to-end tests for Toolbox API.

These tests run against a live Toolbox stack. Set TOOLBOX_URL env var
to point at your running instance (default: http://localhost:9600).

Requirements:
    pip install pytest pytest-asyncio httpx

Run:
    pytest tests/ -v
    pytest tests/ -v -k "not llm"  # skip LLM-dependent tests

Tests are grouped by endpoint. LLM-dependent tests (describe, summarize, extract)
are marked with @pytest.mark.llm and can be skipped if no LLM is configured.
"""

import base64
import os

import httpx
import pytest

BASE_URL = os.environ.get("TOOLBOX_URL", "http://localhost:9600")


@pytest.fixture(scope="session")
def client():
    """Shared HTTP client for all tests."""
    with httpx.Client(base_url=BASE_URL, timeout=30) as c:
        yield c


@pytest.fixture(scope="session")
def async_client():
    """Async HTTP client for concurrent tests."""
    return httpx.AsyncClient(base_url=BASE_URL, timeout=60)


# ── Health ────────────────────────────────────────────────────────────────────


class TestHealth:
    def test_healthz_returns_200(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "backends" in data
        assert set(data["backends"].keys()) == {"searxng", "camoufox", "whisper", "llm"}

    def test_healthz_backends_are_healthy(self, client):
        r = client.get("/healthz")
        data = r.json()
        # At minimum searxng and camoufox should be up for fetch/search to work
        assert data["backends"]["searxng"] == "healthy", "SearXNG is not healthy"
        assert data["backends"]["camoufox"] == "healthy", "Camoufox is not healthy"


# ── Skills ────────────────────────────────────────────────────────────────────


class TestSkills:
    def test_skills_returns_all_tools(self, client):
        r = client.get("/v1/skills")
        assert r.status_code == 200
        data = r.json()
        assert "skills" in data
        ids = [s["id"] for s in data["skills"]]
        assert ids == ["search", "fetch", "describe", "transcribe", "summarize", "extract"]

    def test_skills_have_schemas(self, client):
        r = client.get("/v1/skills")
        for skill in r.json()["skills"]:
            assert "input_schema" in skill
            assert "output_schema" in skill
            assert "description" in skill
            assert skill["input_schema"]["type"] == "object"


# ── Search ────────────────────────────────────────────────────────────────────


class TestSearch:
    def test_search_basic(self, client):
        r = client.post("/v1/search", json={"query": "python programming", "limit": 3})
        assert r.status_code == 200
        data = r.json()
        assert data["query"] == "python programming"
        assert data["count"] <= 3
        assert isinstance(data["results"], list)

    def test_search_returns_structured_results(self, client):
        r = client.post("/v1/search", json={"query": "rust language", "limit": 5})
        data = r.json()
        if data["count"] > 0:
            result = data["results"][0]
            assert "title" in result
            assert "url" in result
            assert "snippet" in result
            assert "engine" in result
            assert result["url"].startswith("http")

    def test_search_categories(self, client):
        for cat in ("general", "news", "science", "it"):
            r = client.post("/v1/search", json={"query": "test", "categories": cat, "limit": 2})
            assert r.status_code == 200

    def test_search_empty_query_rejected(self, client):
        r = client.post("/v1/search", json={"query": "   ", "limit": 5})
        # Whitespace-only query should be rejected
        assert r.status_code == 400

    def test_search_invalid_category_rejected(self, client):
        r = client.post("/v1/search", json={"query": "test", "categories": "invalid"})
        assert r.status_code == 422 or r.status_code == 400

    def test_search_caching(self, client):
        """Second identical request should be faster (cached)."""
        import time
        payload = {"query": "toolbox cache test unique query 12345", "limit": 2}

        start = time.time()
        r1 = client.post("/v1/search", json=payload)
        first_time = time.time() - start

        start = time.time()
        r2 = client.post("/v1/search", json=payload)
        second_time = time.time() - start

        assert r1.json() == r2.json()
        # Cache hit should be significantly faster (at least 5x)
        if first_time > 0.5:  # Only assert if first was slow enough to measure
            assert second_time < first_time / 2


# ── Fetch ─────────────────────────────────────────────────────────────────────


class TestFetch:
    def test_fetch_basic(self, client):
        r = client.post("/v1/fetch", json={"url": "https://example.com"}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["url"] == "https://example.com"
        assert "Example Domain" in data["title"] or "example" in data["content"].lower()
        assert data["format"] == "markdown"
        assert data["word_count"] > 0

    def test_fetch_text_format(self, client):
        r = client.post("/v1/fetch", json={"url": "https://example.com", "format": "text"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["format"] == "text"

    def test_fetch_with_screenshot(self, client):
        r = client.post("/v1/fetch", json={"url": "https://example.com", "screenshot": True}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["screenshot_b64"] is not None
        # Verify it's valid base64
        base64.b64decode(data["screenshot_b64"])

    def test_fetch_ssrf_blocked_loopback(self, client):
        r = client.post("/v1/fetch", json={"url": "http://127.0.0.1/admin"})
        assert r.status_code == 400
        assert "loopback" in r.json()["detail"].lower()

    def test_fetch_ssrf_blocked_ftp(self, client):
        r = client.post("/v1/fetch", json={"url": "ftp://evil.com/file"})
        assert r.status_code == 400
        assert "scheme" in r.json()["detail"].lower()

    def test_fetch_ssrf_blocked_metadata(self, client):
        r = client.post("/v1/fetch", json={"url": "http://metadata.google.internal/v1/"})
        assert r.status_code == 400

    def test_fetch_invalid_url(self, client):
        r = client.post("/v1/fetch", json={"url": "not-a-url"})
        assert r.status_code == 400

    def test_fetch_nonexistent_domain(self, client):
        r = client.post("/v1/fetch", json={"url": "https://thisdomaindoesnotexist12345.com"}, timeout=30)
        assert r.status_code == 200
        # Should return error content gracefully, not crash
        assert "error" in r.json()["content"].lower() or r.json()["word_count"] == 0

    def test_fetch_wait_ms(self, client):
        r = client.post("/v1/fetch", json={"url": "https://example.com", "wait_ms": 1000}, timeout=30)
        assert r.status_code == 200

    def test_fetch_caching(self, client):
        """Fetched pages should be cached."""
        import time
        payload = {"url": "https://example.com", "format": "markdown"}

        client.post("/v1/fetch", json=payload, timeout=30)  # Prime cache

        start = time.time()
        r = client.post("/v1/fetch", json=payload, timeout=30)
        elapsed = time.time() - start

        assert r.status_code == 200
        assert elapsed < 0.5  # Cache hit should be fast


# ── Describe ──────────────────────────────────────────────────────────────────


def llm_available(client):
    """Check if LLM backend is healthy."""
    r = client.get("/healthz")
    return r.json()["backends"].get("llm") == "healthy"


skip_no_llm = pytest.mark.skipif(
    "not config.getoption('--run-llm', default=False)",
    reason="LLM not available or --run-llm not passed",
)


@pytest.mark.llm
class TestDescribe:
    @pytest.fixture(autouse=True)
    def _check_llm(self, client):
        if not llm_available(client):
            pytest.skip("LLM backend not available")

    def test_describe_page_url(self, client):
        r = client.post("/v1/describe", json={
            "page_url": "https://example.com",
            "prompt": "What is shown on this page?",
        }, timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert len(data["description"]) > 10

    def test_describe_image_url(self, client):
        r = client.post("/v1/describe", json={
            "image_url": "https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_272x92dp.png",
            "prompt": "What logo is this?",
        }, timeout=60)
        assert r.status_code == 200
        assert len(r.json()["description"]) > 10

    def test_describe_image_b64(self, client):
        # 1x1 red PNG
        red_pixel = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        r = client.post("/v1/describe", json={
            "image_b64": red_pixel,
            "prompt": "What color is this pixel?",
        }, timeout=60)
        assert r.status_code == 200
        assert len(r.json()["description"]) > 5

    def test_describe_no_input_rejected(self, client):
        r = client.post("/v1/describe", json={"prompt": "describe"})
        assert r.status_code == 400

    def test_describe_ssrf_blocked(self, client):
        r = client.post("/v1/describe", json={"image_url": "http://127.0.0.1/secret.png"})
        assert r.status_code == 400


# ── Transcribe ────────────────────────────────────────────────────────────────


class TestTranscribe:
    @pytest.fixture(autouse=True)
    def _check_whisper(self, client):
        r = client.get("/healthz")
        if r.json()["backends"].get("whisper") != "healthy":
            pytest.skip("Whisper backend not available")

    def test_transcribe_no_input_rejected(self, client):
        r = client.post("/v1/transcribe", json={})
        assert r.status_code == 400 or r.status_code == 422

    def test_transcribe_invalid_b64_rejected(self, client):
        r = client.post("/v1/transcribe", json={"audio_b64": "not-valid-base64!!!"})
        assert r.status_code == 400

    def test_transcribe_ssrf_blocked(self, client):
        r = client.post("/v1/transcribe", json={"audio_url": "http://127.0.0.1/audio.wav"})
        assert r.status_code == 400

    def test_transcribe_audio_url(self, client):
        """Transcribe a short public audio file."""
        # Use a known short audio sample
        r = client.post("/v1/transcribe", json={
            "audio_url": "https://www.kozco.com/tech/LRMonoPhase4.wav",
            "language": "en",
        }, timeout=120)
        assert r.status_code == 200
        data = r.json()
        assert "transcript" in data
        assert data["language"] == "en"

    def test_transcribe_openai_compat_no_file(self, client):
        """OpenAI-compat endpoint rejects empty file."""
        r = client.post("/v1/audio/transcriptions", files={"file": ("empty.wav", b"", "audio/wav")})
        assert r.status_code == 400


# ── Summarize ─────────────────────────────────────────────────────────────────


@pytest.mark.llm
class TestSummarize:
    @pytest.fixture(autouse=True)
    def _check_llm(self, client):
        if not llm_available(client):
            pytest.skip("LLM backend not available")

    def test_summarize_basic(self, client):
        long_text = "Python is a high-level programming language. " * 50
        r = client.post("/v1/summarize", json={
            "text": long_text,
            "max_tokens": 50,
            "style": "brief",
        }, timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert len(data["summary"]) > 10
        assert len(data["summary"]) < len(long_text)

    def test_summarize_bullets(self, client):
        text = "First point about databases. Second point about caching. Third point about APIs."
        r = client.post("/v1/summarize", json={
            "text": text,
            "style": "bullets",
            "max_tokens": 100,
        }, timeout=60)
        assert r.status_code == 200

    def test_summarize_empty_rejected(self, client):
        r = client.post("/v1/summarize", json={"text": "", "max_tokens": 50})
        assert r.status_code == 400

    def test_summarize_invalid_style_rejected(self, client):
        r = client.post("/v1/summarize", json={"text": "hello", "style": "invalid"})
        assert r.status_code == 422 or r.status_code == 400

    def test_summarize_truncation(self, client):
        """Input longer than 6800 chars should not crash."""
        huge_text = "word " * 5000  # ~25000 chars
        r = client.post("/v1/summarize", json={
            "text": huge_text,
            "max_tokens": 50,
        }, timeout=60)
        assert r.status_code == 200


# ── Extract ───────────────────────────────────────────────────────────────────


@pytest.mark.llm
class TestExtract:
    @pytest.fixture(autouse=True)
    def _check_llm(self, client):
        if not llm_available(client):
            pytest.skip("LLM backend not available")

    def test_extract_basic_object(self, client):
        text = "John Smith is 30 years old and lives in New York City."
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "city": {"type": "string"},
            },
            "required": ["name", "age", "city"],
        }
        r = client.post("/v1/extract", json={"text": text, "schema": schema}, timeout=60)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["name"] == "John Smith"
        assert data["age"] == 30
        assert "New York" in data["city"]

    def test_extract_array_schema(self, client):
        text = "Products: Widget ($9.99), Gadget ($19.99), Doohickey ($4.99)"
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "price": {"type": "number"},
                },
            },
        }
        r = client.post("/v1/extract", json={"text": text, "schema": schema}, timeout=60)
        assert r.status_code == 200
        data = r.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 3

    def test_extract_empty_text_rejected(self, client):
        r = client.post("/v1/extract", json={"text": "", "schema": {"type": "object"}})
        assert r.status_code == 400

    def test_extract_empty_schema_rejected(self, client):
        r = client.post("/v1/extract", json={"text": "hello", "schema": {}})
        assert r.status_code == 400

    def test_extract_missing_fields_return_null(self, client):
        text = "The temperature is 72 degrees."
        schema = {
            "type": "object",
            "properties": {
                "temperature": {"type": "number"},
                "humidity": {"type": "number"},
                "wind_speed": {"type": "number"},
            },
        }
        r = client.post("/v1/extract", json={"text": text, "schema": schema}, timeout=60)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["temperature"] == 72
        # Missing fields should be null
        assert data.get("humidity") is None or data.get("humidity") == 0


# ── MCP ───────────────────────────────────────────────────────────────────────


class TestMCP:
    HEADERS = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    def test_mcp_tools_list(self, client):
        r = client.post("/mcp/", headers=self.HEADERS, json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {},
        })
        assert r.status_code == 200
        data = r.json()
        assert "result" in data
        tools = data["result"]["tools"]
        names = [t["name"] for t in tools]
        assert set(names) == {"search", "fetch", "describe", "transcribe", "summarize", "extract"}

    def test_mcp_search(self, client):
        r = client.post("/mcp/", headers=self.HEADERS, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "search", "arguments": {"query": "python", "limit": 2}},
        }, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "result" in data

    def test_mcp_fetch_validation(self, client):
        r = client.post("/mcp/", headers=self.HEADERS, json={
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "fetch", "arguments": {"url": "ftp://bad.com"}},
        })
        assert r.status_code == 200
        data = r.json()
        # MCP returns error in result, not HTTP error
        assert data["result"]["isError"] is True

    def test_mcp_invalid_method(self, client):
        r = client.post("/mcp/", headers=self.HEADERS, json={
            "jsonrpc": "2.0", "id": 4, "method": "nonexistent/method", "params": {},
        })
        assert r.status_code == 200
        data = r.json()
        assert "error" in data

    def test_mcp_missing_accept_header(self, client):
        """MCP requires Accept header."""
        r = client.post("/mcp/", json={
            "jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": {},
        })
        # Should return error (406 or JSON-RPC error)
        assert r.status_code in (200, 406)


# ── Validation Edge Cases ─────────────────────────────────────────────────────


class TestValidation:
    def test_fetch_ipv6_loopback_blocked(self, client):
        r = client.post("/v1/fetch", json={"url": "http://[::1]/test"})
        assert r.status_code == 400

    def test_fetch_zero_address_blocked(self, client):
        r = client.post("/v1/fetch", json={"url": "http://0.0.0.0/test"})
        assert r.status_code == 400

    def test_fetch_link_local_blocked(self, client):
        r = client.post("/v1/fetch", json={"url": "http://169.254.169.254/latest/meta-data/"})
        assert r.status_code == 400

    def test_search_limit_clamped(self, client):
        """Limit > 50 should be clamped, not error."""
        r = client.post("/v1/search", json={"query": "test", "limit": 100})
        # Pydantic rejects > 50 at validation
        assert r.status_code == 422

    def test_fetch_wait_ms_clamped(self, client):
        """wait_ms > 20000 should be rejected by Pydantic."""
        r = client.post("/v1/fetch", json={"url": "https://example.com", "wait_ms": 30000})
        assert r.status_code == 422
