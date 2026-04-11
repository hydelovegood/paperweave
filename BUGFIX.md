# PaperLab Bug Fix Report

## P0 - Must Fix

### 1. `extract_json_object` / `extract_json_array` crash on non-JSON LLM output

**File**: `src/paperlab/llm/client.py:53-55` and `:76-78`

**Problem**: `str.index("{")` raises `ValueError` when the string contains no `{`. If the LLM returns plain text (common in real usage), the entire summary/qa pipeline crashes with an unhelpful error.

```python
# current code - will crash
start = stripped.index("{")
end = stripped.rindex("}") + 1
return json.loads(stripped[start:end])
```

**Fix**: Add error handling that raises a clear error message instead of a raw `ValueError`.

```python
try:
    start = stripped.index("{")
    end = stripped.rindex("}") + 1
    return json.loads(stripped[start:end])
except (ValueError, json.JSONDecodeError) as exc:
    raise ValueError(f"Failed to extract JSON object from LLM response: {stripped[:200]!r}") from exc
```

Same pattern for `extract_json_array`.

---

### 2. Redundant `if doi` inside already-doi-guarded condition

**File**: `src/paperlab/enrich/forward_citations.py:280-281`

**Problem**: The inner `if doi:` is always True because the outer condition already checks `doi`. This is likely a leftover from refactoring and may indicate a missing intended check.

```python
# current code
if settings.citations.download_oa_only and not is_oa and doi and settings.secrets.unpaywall_email:
    if doi:  # <-- always True, redundant
        ua_result = unpaywall.check_oa(doi, settings.secrets.unpaywall_email)
```

**Fix**: Remove the inner `if doi:`. If something else was intended (e.g. checking `ua_result` before calling), investigate and fix accordingly.

---

## P1 - Security / Privacy

### 3. API keys visible in conversation context

**File**: `.env`

**Problem**: `.env` contains real API keys for DeepXiv and ZhipuAI. Although `.env` is in `.gitignore`, the keys have been exposed in AI conversation logs. If this project is shared or conversations are stored, keys are compromised.

**Fix**:
- Rotate both `DEEPXIV_TOKEN` and `OPENAI_API_KEY` immediately.
- Add a `.env.example` note warning users not to share their `.env` file.
- Consider adding `.env` to a global gitignore as a safety net.

---

### 4. LLM logs contain full paper analysis

**File**: `data/logs/llm/*.txt` (18 files)

**Problem**: Every LLM response (full summary JSON, full QA) is written to disk in `data/logs/llm/`. While `data/` is gitignored, these files are locally accessible and contain complete analysis of all papers.

**Fix**: This is a design decision, but consider:
- Adding a `llm.log_retention_days` config option to auto-clean old logs.
- Documenting that these logs exist and contain sensitive content.

---

## P2 - Logic / UX Issues

### 5. `_resolve()` early returns prevent cross-source ID enrichment

**File**: `src/paperlab/enrich/forward_citations.py:123-171`

**Problem**: The function returns as soon as ANY single source succeeds. This means:
- If OpenAlex succeeds, we never try S2 for `s2_id`
- If S2 succeeds, we never try OpenAlex for `openalex_id`
- If OpenAlex citation fetching fails later (rate limit, timeout), we don't fall back to S2

**Fix**: Accumulate results from all sources instead of early return, or at minimum try a second source if the first returns only partial data.

```python
def _resolve(paper: dict, email: str, s2_key: str) -> dict | None:
    result: dict = {}

    # Try all sources, accumulate IDs
    if paper.get("doi"):
        oa = openalex.resolve_by_doi(paper["doi"], mailto=email)
        if oa:
            result.update(oa)

    if paper.get("title") and not result.get("openalex_id"):
        oa = openalex.resolve_by_title(paper["title"], mailto=email)
        if oa:
            result.update(oa)

    if paper.get("arxiv_id") and not result.get("s2_id"):
        s2r = s2.resolve_by_arxiv(paper["arxiv_id"], api_key=s2_key)
        if s2r:
            result.update(s2r)

    # ... continue for all sources

    return result or None
```

---

### 6. Inconsistent exception handling between summarize and qa batch loops

**File**: `src/paperlab/cli/summarize_cmd.py:46` vs `src/paperlab/cli/qa_cmd.py:46`

**Problem**:
- `summarize_cmd.py` catches bare `except Exception` — swallows all errors, hides real bugs
- `qa_cmd.py` catches only `(FileNotFoundError, ValueError, json.JSONDecodeError)` — won't catch `openai.APIConnectionError` or network timeouts, causing the entire batch to abort on first network failure

Both approaches have problems. The batch loop should catch expected errors and continue, but let truly unexpected errors propagate.

**Fix**: Use consistent error handling in both files. Catch the union of expected error types:

```python
except (FileNotFoundError, ValueError, json.JSONDecodeError, openai.APIError) as exc:
    print(f"Failed to process paper {pid}: {exc}")
```

---

### 7. `qa_export.py:37` opens a new DB connection per paper in loop

**File**: `src/paperlab/export/qa_export.py:37`

**Problem**: The `for paper_id, title in papers:` loop creates a new `sqlite3.connect(db)` for each paper. Wasteful when exporting many papers.

**Fix**: Move the connection outside the loop.

```python
# before
for paper_id, title in papers:
    with sqlite3.connect(db) as conn:
        items = conn.execute(...)

# after
with sqlite3.connect(db) as conn:
    for paper_id, title in papers:
        items = conn.execute(...)
```

---

## P3 - Architecture / Consistency

### 8. `graph_status` vs `citation_status` dual field confusion

**Files involved**: `schema.py`, `status.py`, `forward_citations.py`, `registry.py`, multiple test files

**Problem**: The `papers` table has both `graph_status` and `citation_status`. It's unclear which is authoritative:
- `forward_citations.py` updates `citation_status`
- `select_papers_for_citations()` checks `citation_status`
- `mark_downstream_stale()` sets both to `stale`
- Most tests only INSERT `graph_status` and rely on `citation_status` DEFAULT 'pending'

**Fix**: Decide on one field. If `citation_status` replaces `graph_status`:
1. Remove `graph_status` from schema
2. Update all tests to use `citation_status`
3. Update `mark_downstream_stale()` to only set `citation_status`
4. Add migration in `_ensure_papers_columns()` for existing DBs

---

### 9. 6 places catch bare `except Exception` (violates project coding rules)

| File | Line | Context | Recommendation |
|------|------|---------|----------------|
| `summarize_cmd.py` | 46 | batch loop | Narrow to expected exceptions (see #6) |
| `citations_cmd.py` | 36 | batch loop | Narrow to `(FileNotFoundError, openai.APIError)` |
| `doctor_cmd.py` | 48 | import check | Change to `except ImportError` |
| `forward_citations.py` | 82 | main flow | Acceptable: marks failed + re-raises |
| `llm/summary.py` | 102 | mark failed + re-raise | Acceptable: state machine correctness |
| `llm/qa.py` | 101 | mark failed + re-raise | Acceptable: state machine correctness |

The last three are acceptable patterns (catch -> update status -> re-raise). The first three should be narrowed.

---

### 10. `deepxiv-sdk` as required dependency in pyproject.toml

**File**: `pyproject.toml:14`

**Problem**: `deepxiv-sdk>=0.2.3` is listed as a required dependency. If this package is not on PyPI (likely, it's niche), `pip install -e .` fails. The code already handles its absence gracefully via `try: import deepxiv_sdk`.

**Fix**: Move to optional dependencies:

```toml
[project.optional-dependencies]
deepxiv = ["deepxiv-sdk>=0.2.3"]
```

---

### 11. `download_oa_only` config name is misleading

**File**: `configs/app.yaml:26`, `src/paperlab/enrich/forward_citations.py:275-300`

**Problem**: The name suggests "only store OA links", but non-OA papers still get `landing_page` links (DOI redirect). The flag actually controls whether to check Unpaywall for hidden OA status.

**Fix**: Rename to something more accurate, e.g. `check_unpaywall_for_oa` or keep the name but add a comment in the config.
