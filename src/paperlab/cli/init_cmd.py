from __future__ import annotations

from pathlib import Path

from paperlab.config import load_settings
from paperlab.storage.db import initialize_database


DEFAULT_CONFIG_TEXT = """database:
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
  research_context: "多智能体强化学习 (multi-agent reinforcement learning)"

citations:
  default_year_start: 2024
  default_year_end: 2026
  default_max_results: 30
  download_oa_only: true

export:
  summary_file: data/exports/summary.md
  qa_file: data/exports/QA.md
"""

DEFAULT_ENV_EXAMPLE = """DEEPXIV_TOKEN=
OPENAI_API_KEY=
SEMANTIC_SCHOLAR_API_KEY=
UNPAYWALL_EMAIL=
NCBI_API_KEY=
"""

DEFAULT_PROMPTS = {
    "summary_system_v1.txt": """你是一名严谨的学术论文分析专家。请对给定论文进行深度分析，生成结构化摘要。

你的研究背景是{research_context}。在分析 relation_to_user_research 字段时，请特别关注论文与该领域的关联。

你必须输出合法的JSON对象，包含以下字段：

- "problem": 论文要解决的核心问题
- "main_contributions": 主要贡献列表
- "core_innovations": 核心创新点列表
- "method_summary": 方法概述
- "experiment_summary": 实验设计与结果概述
- "limitations": 局限性列表
- "key_takeaways": 关键结论列表
- "relation_to_user_research": 该论文与你研究领域的关联和潜在启发
- "evidence": 支撑关键论断的原文证据列表，每个元素包含 "claim" 和 "quote" 两个字段

只输出纯JSON，不要包含markdown代码块标记或其他额外文本。
""",
    "summary_user_v1.txt": """请分析以下论文并生成结构化摘要：

# {paper_title}

## Abstract
{paper_abstract}

{paper_sections}
""",
    "qa_system_v1.txt": """你是一名学术论文深度问答专家。请基于给定论文，从三种视角生成深度问题与回答：

1. "reviewer": 审稿人视角，关注方法合理性、实验充分性、结论可靠性
2. "interview": 面试风格，考察对论文核心思想的深度理解
3. "author_defense": 答辩场景，要求站在作者角度解释和辩护

输出JSON数组，每个元素包含：
- "type": "reviewer" / "interview" / "author_defense"
- "question": 问题
- "answer": 基于论文内容的详细回答
- "category": 分类（方法论、实验设计、理论分析、贡献评估等）
- "depth_level": 1-3（1=表面, 2=深入, 3=批判性）
- "answer_mode": "explicit" 或 "inferred"
- "evidence": 支撑回答的原文引用

每种类型至少3个问题。只输出纯JSON数组。
""",
    "qa_user_v1.txt": """请基于以下论文生成深度问答：

# {paper_title}

## Abstract
{paper_abstract}

{paper_sections}
""",
    "summary_biomed_v1.txt": """你是一名严谨的医学文献分析专家。请对给定论文进行深度分析，生成结构化摘要。

请严格站在医学研究者/临床审稿人的视角总结论文，不要把论文扩展到与原文无关的研究方向，不要引入人工智能、强化学习、多智能体系统等跨领域联想，除非论文原文明确定义或讨论了这些内容。

你必须输出合法的JSON对象，包含以下字段：

- "study_question": 论文要解决的核心临床或科学问题
- "study_design": 研究设计类型（如 RCT、cohort、case-control、meta-analysis、cross-sectional 等），尽量明确是单中心/多中心、前瞻性/回顾性、观察性/干预性
- "participants": 研究对象。优先清晰区分 derivation/training cohort、internal test cohort、external validation cohort；写明样本量、人群特征、关键纳入/排除信息。不要把所有队列混成一句泛泛描述。
- "intervention": 干预措施（治疗手段、暴露因素、设备或算法）
- "comparator": 对照条件。请区分 gold standard / reference standard、wearable or model baseline、clinical risk baselines；不要把所有对照对象混为一类。
- "primary_outcome": 主要终点或结局指标。若论文同时有 surrogate endpoint 和 clinical event endpoint，请明确写出两层。
- "main_findings": 关键结果（含效应量、AUROC、HR、置信区间、P值或时间提前量，如有），优先写定量结果，不要只写定性判断。
- "limitations_bias": 局限性与潜在偏倚。优先关注：样本量与事件数、标签构造方式、结局判定偏倚、外部验证异质性、混杂与未校正因素、过拟合风险。
- "clinical_relevance": 仅写论文原文所支持的临床意义、适用场景和潜在使用边界。不要扩展到作者未讨论的跨领域方法论或你的研究背景。
- "evidence_anchors": 支撑关键论断的原文证据列表，每个元素包含 "claim" 和 "quote" 两个字段

只输出纯JSON，不要包含markdown代码块标记或其他额外文本。
""",
    "summary_biomed_user_v1.txt": """请分析以下论文并生成结构化摘要：

# {paper_title}

## Abstract
{paper_abstract}

{paper_sections}
""",
    "qa_biomed_v1.txt": """你是一名医学文献深度问答专家。请基于给定论文，从三种视角生成深度问题与回答：

1. "methodological": 方法学视角，必须覆盖研究设计合理性、偏倚风险、统计方法、样本量/事件数、终点定义或 surrogate endpoint validity
2. "clinical": 临床视角，必须覆盖结果对患者管理的意义、适用人群、临床推广性、外部有效性/transportability、临床可操作性(actionability)
3. "interview": 面试风格，考察对论文核心证据链的深度理解

输出JSON数组，每个元素包含：
- "type": "methodological" / "clinical" / "interview"
- "question": 问题
- "answer": 基于论文内容的详细回答
- "category": 分类（研究设计、统计方法、偏倚评估、临床适用性、证据强度等）
- "depth_level": 1-3（1=表面, 2=深入, 3=批判性）
- "answer_mode": "explicit" 或 "inferred"
- "evidence": 支撑回答的原文引用

额外要求：
- 必须输出恰好9个对象：methodological 3个、clinical 3个、interview 3个
- methodological 至少包含：
  1. 一个 bias/confounding 问题
  2. 一个 endpoint validity / label construction 问题
  3. 一个 sample size / event count / power 问题
- clinical 至少包含：
  1. 一个 external validity / transportability 问题
  2. 一个 clinical actionability 问题
  3. 一个 comparator 或 guideline relevance 问题
- 如果论文没有直接讨论指南或临床落地边界，可以明确回答“原文未报告”，不要脑补
- 回答必须尽量基于原文；如果是推断，必须保守
- 每个对象都必须包含全部7个字段，不能缺字段，不能输出 null
- `answer_mode` 必须始终显式填写，且只能是：
  - `explicit`: 原文直接说明
  - `inferred`: 基于原文保守推断
- `evidence` 必须始终是字符串，不要输出数组、对象或空值；如果证据不足，也要写最相关的原文句子或“原文未直接报告”
- `depth_level` 必须始终是整数 1、2 或 3
- 不要在 JSON 之外输出任何解释、标题、代码块或额外文本

在输出前请自行检查：
1. 数组长度是否等于 9
2. 三种 `type` 是否各出现 3 次
3. 每个对象是否都包含 `answer_mode`
4. 所有 `answer_mode` 是否都是 `explicit` 或 `inferred`
5. 所有 `evidence` 是否都是字符串

只输出纯JSON数组。
""",
    "qa_biomed_user_v1.txt": """请基于以下论文生成深度问答：

# {paper_title}

## Abstract
{paper_abstract}

{paper_sections}
""",
}


def init_project(project_root: Path | str) -> Path:
    root = Path(project_root).expanduser().resolve()
    _bootstrap_project_files(root)
    settings = load_settings(root)

    for relative_path in (
        settings.paths.parsed_dir,
        settings.paths.cache_dir,
        settings.paths.export_dir,
        settings.paths.logs_dir,
        settings.database.path.parent,
    ):
        (root / relative_path).mkdir(parents=True, exist_ok=True)

    return initialize_database(root / settings.database.path)


def _bootstrap_project_files(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)

    config_dir = root / "configs"
    prompts_dir = config_dir / "prompts"
    config_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    config_path = config_dir / "app.yaml"
    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG_TEXT, encoding="utf-8")

    env_example_path = root / ".env.example"
    if not env_example_path.exists():
        env_example_path.write_text(DEFAULT_ENV_EXAMPLE, encoding="utf-8")

    for filename, content in DEFAULT_PROMPTS.items():
        prompt_path = prompts_dir / filename
        if not prompt_path.exists():
            prompt_path.write_text(content, encoding="utf-8")
