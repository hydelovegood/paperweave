from paperlab.cli.main import build_parser


def test_all_commands_are_registered():
    parser = build_parser()

    # init
    args = parser.parse_args(["init", "/tmp/proj"])
    assert args.command == "init"

    # ingest
    args = parser.parse_args(["ingest", "/tmp/proj", "/tmp/pdfs"])
    assert args.command == "ingest"

    # summarize
    args = parser.parse_args(["summarize", "/tmp/proj"])
    assert args.command == "summarize"

    # qa
    args = parser.parse_args(["qa", "/tmp/proj"])
    assert args.command == "qa"

    # citations forward
    args = parser.parse_args(["citations", "forward", "/tmp/proj"])
    assert args.command == "citations"
    assert args.cit_command == "forward"

    # export summary
    args = parser.parse_args(["export", "summary", "/tmp/proj"])
    assert args.command == "export"
    assert args.export_type == "summary"

    # export qa
    args = parser.parse_args(["export", "qa", "/tmp/proj"])
    assert args.command == "export"
    assert args.export_type == "qa"


def test_ingest_accepts_recursive():
    parser = build_parser()
    args = parser.parse_args(["ingest", "/tmp/proj", "/tmp/pdfs", "--recursive"])
    assert args.recursive is True


def test_summarize_accepts_paper_ids():
    parser = build_parser()
    args = parser.parse_args(["summarize", "/tmp/proj", "--paper-ids", "1", "2", "3"])
    assert args.paper_ids == [1, 2, 3]


def test_citations_forward_accepts_year_range():
    parser = build_parser()
    args = parser.parse_args(["citations", "forward", "/tmp/proj", "--year-start", "2023", "--year-end", "2025", "--max-results", "15"])
    assert args.year_start == 2023
    assert args.year_end == 2025
    assert args.max_results == 15


def test_summarize_accepts_changed_all_and_force():
    parser = build_parser()
    args = parser.parse_args(["summarize", "/tmp/proj", "--all", "--force"])
    assert args.all is True
    assert args.force is True


def test_qa_accepts_changed_all_and_force():
    parser = build_parser()
    args = parser.parse_args(["qa", "/tmp/proj", "--changed", "--force"])
    assert args.changed is True
    assert args.force is True


def test_doctor_is_registered():
    parser = build_parser()
    args = parser.parse_args(["doctor", "/tmp/proj", "--check-llm"])
    assert args.command == "doctor"
    assert args.check_llm is True
