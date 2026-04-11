<p align="center">
  <img src="logo.png" alt="PaperWeave logo" width="300">
</p>

# PaperWeave（溯源文库）

> Local-first CLI for building a structured paper library with parsing, summaries, deep Q&A, and forward-citation tracking.

PaperWeave（溯源文库）是一个面向研究者的本地论文工作流工具。  
它不是传统的“只管存 PDF”的文献管理器，而是一个把论文转化为**可积累、可更新、可导出**研究资产的 CLI 系统。

你可以用它：

- 导入指定目录下的 PDF
- 解析论文正文与章节结构
- 生成结构化 Summary
- 生成 reviewer / interview / author-defense 三类 QA
- 追踪经典论文在近年的 forward citations
- 导出 `summary.md` 和 `QA.md`

项目当前强调：

- local-first
- single-user
- explicit-path ingestion
- SQLite as source of truth
- Markdown as export layer only



## Why This Project Exists

Research workflows often break down in the same places:

- PDFs accumulate, but insights do not
- summaries are scattered across notes, chats, and folders
- deep questions about a paper are never systematically captured
- tracking what cited a classic paper still takes manual effort
- exported reading material and structured data drift apart

PaperWeave tries to fix that by treating papers as **structured research assets**, not just files.



## Current Features

### 1. Project Initialization

- create project directories
- initialize SQLite database
- prepare parsed/export/log folders

### 2. Explicit PDF Ingestion

- ingest a single PDF or a specific folder
- optional recursive scanning
- SHA256-based file deduplication
- stale-state propagation when file contents change

### 3. Unified Parsing Pipeline

- direct arXiv IDs use `DeepXiv`
- PDFs with front-page arXiv IDs prefer `DeepXiv`
- recoverable DeepXiv failures fall back to `PyMuPDF`
- parsed output normalizes into a shared `CanonicalPaper` shape
- parsed JSON and section rows are persisted locally

### 4. Structured Summary Generation

- generates structured summaries via LLM
- stores both JSON and rendered Markdown
- supports incremental reruns
- records raw LLM output logs

### 5. Deep QA Generation

- reviewer-style questions
- interview-style questions
- author-defense questions
- replaces stale QA cleanly on rerun

### 6. Forward Citation Tracking

- find recent citing papers for designated classic papers
- persist citation edges and paper stubs
- store OA PDF links when available
- store landing-page / DOI links for non-OA papers

### 7. Markdown Export

- export `summary.md`
- export `QA.md`
- export uses stored state only and does not re-run analysis

### 8. Doctor Command

- check config presence
- check prompt files
- check database existence
- check core runtime dependencies
- optionally run a live LLM connectivity probe

---

## Architecture

```text
PDF / arXiv ID / query
        ↓
      ingest
        ↓
      parse
        ↓
CanonicalPaper + sections
        ↓
summary / qa / citations
        ↓
SQLite + parsed JSON + logs
        ↓
summary.md / QA.md
```

Design principles:

- SQLite is the system of record
- Markdown is an export layer
- deterministic processing and LLM processing are separated
- everything is incremental by default

---

## Project Layout

```text
paperlab/
├─ pyproject.toml
├─ README.md
├─ .env.example
├─ configs/
│  ├─ app.yaml
│  └─ prompts/
├─ data/
│  ├─ parsed/
│  ├─ cache/
│  ├─ exports/
│  │  ├─ summary.md
│  │  └─ QA.md
│  └─ logs/
├─ db/
│  └─ papers.db
├─ src/paperlab/
│  ├─ cli/
│  ├─ config/
│  ├─ storage/
│  ├─ ingest/
│  ├─ parsing/
│  ├─ enrich/
│  ├─ llm/
│  ├─ export/
│  └─ utils/
└─ tests/
```

---

## Installation

### Conda

```bash
conda create -n paperweave python=3.10
conda activate paperweave
git clone https://github.com/hydelovegood/paperweave
cd paperlab
pip install -e .
```

### Or venv

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

---

## Configuration

Copy `.env.example` to `.env`:

```env
DEEPXIV_TOKEN=
OPENAI_API_KEY=
SEMANTIC_SCHOLAR_API_KEY=
UNPAYWALL_EMAIL=
```

Then edit `configs/app.yaml`.

Example:

```yaml
database:
  path: db/papers.db

paths:
  parsed_dir: data/parsed
  cache_dir: data/cache
  export_dir: data/exports
  logs_dir: data/logs

parsing:
  prefer_deepxiv_for_arxiv: true
  pymupdf_section_split: true

llm:
  base_url: https://open.bigmodel.cn/api/coding/paas/v4
  summary_model: glm-5.1
  qa_model: glm-5.1
  lang: zh
  max_retries: 2
  research_context: "multi-agent reinforcement learning"

citations:
  default_year_start: 2024
  default_year_end: 2026
  default_max_results: 30
  download_oa_only: true

export:
  summary_file: data/exports/summary.md
  qa_file: data/exports/QA.md
```

Note: `download_oa_only: true` does **not** mean non-OA citing papers are discarded.  
PaperWeave still stores landing-page / DOI links for non-OA papers; the flag mainly controls whether it actively probes for OA availability.

---

## Quick Start

### 1. Initialize a Project

```bash
paperctl init C:\research\paperweave
```

### 2. Ingest Papers

Single PDF:

```bash
paperctl ingest C:\research\paperweave "C:\papers\sample.pdf"
```

Whole folder:

```bash
paperctl ingest C:\research\paperweave C:\papers
```

Recursive:

```bash
paperctl ingest C:\research\paperweave C:\papers --recursive
```

### 3. Generate Summaries

Changed or stale papers:

```bash
paperctl summarize C:\research\paperweave --changed
```

All parsed papers:

```bash
paperctl summarize C:\research\paperweave --all
```

Specific papers:

```bash
paperctl summarize C:\research\paperweave --paper-ids 1 2 3
```

Force rerun:

```bash
paperctl summarize C:\research\paperweave --paper-ids 1 2 3 --force
```

### 4. Generate QA

```bash
paperctl qa C:\research\paperweave --changed
```

Or:

```bash
paperctl qa C:\research\paperweave --all
```

Force rerun:

```bash
paperctl qa C:\research\paperweave --paper-ids 1 2 3 --force
```

### 5. Track Forward Citations

```bash
paperctl citations forward C:\research\paperweave --paper-ids 9 --year-start 2024 --year-end 2026
```

Limit result count:

```bash
paperctl citations forward C:\research\paperweave --paper-ids 9 --year-start 2024 --year-end 2026 --max-results 20
```

### 6. Export Results

```bash
paperctl export summary C:\research\paperweave
paperctl export qa C:\research\paperweave
```

### 7. Run Diagnostics

```bash
paperctl doctor C:\research\paperweave
paperctl doctor C:\research\paperweave --check-llm
```

---

## Example Workflow

```bash
paperctl init C:\research\paperweave
paperctl ingest C:\research\paperweave C:\papers --recursive
paperctl summarize C:\research\paperweave --changed
paperctl qa C:\research\paperweave --changed
paperctl citations forward C:\research\paperweave --paper-ids 9 --year-start 2024 --year-end 2026
paperctl export summary C:\research\paperweave
paperctl export qa C:\research\paperweave
```

---

## Incremental Model

PaperWeave is incremental by design.

It tracks:

- file hashes
- prompt versions
- model names
- task input hashes

Core status fields:

- `parse_status`
- `summary_status`
- `qa_status`
- `citation_status`

Typical values:

- `pending`
- `done`
- `failed`
- `stale`

---

## Current State

This project is already usable for real local workflows, especially for:

- small to medium local paper libraries
- structured paper summaries
- deep reviewer/interview/defense QA
- tracking which recent work cites a classic paper
- Markdown export for direct reading

It is currently:

- CLI-first
- single-user
- local-first
- SQLite-backed

---

## Limitations

Current known limitations:

- no GUI
- no background worker / queue system
- forward-citation PDF download is not yet a full closed-loop ingestion workflow
- some non-arXiv PDFs rely entirely on `PyMuPDF`
- citation quality depends on external API coverage and rate limits
- LLM output is more robust now, but still benefits from manual spot checks on high-value papers

---

## Security and Privacy

Please note:

- `.env` contains real API keys and must never be committed
- `data/logs/llm/` stores raw LLM outputs
- `papers.db` stores summaries, QA, and citation metadata
- if you use a shared machine, protect the local project directory accordingly

---

## Roadmap

Potential next steps:

- automatic OA PDF download for citing papers
- stronger DOI / arXiv / OpenAlex reconciliation
- topic and method tagging
- lineage / research-thread generation
- stronger schema-constrained LLM parsing
- richer `doctor` diagnostics
- better large-library batch orchestration

---

## Why PaperWeave（溯源文库）

- **Paper**: the unit of research work
- **Weave**: papers, summaries, QA, and citations are woven into one workflow
- **溯源**: trace ideas and papers back to their source
- **文库**: a growing local library of structured research assets

---

## License

This project is licensed under the MIT License.

See [LICENSE](LICENSE).

---

## Acknowledgements

PaperWeave builds on or integrates with:

- DeepXiv
- PyMuPDF
- OpenAlex
- Semantic Scholar
- Crossref
- Unpaywall
- OpenAI-compatible API clients
