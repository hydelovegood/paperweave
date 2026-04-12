from click.testing import CliRunner

from paperlab.cli.main import cli


def test_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "PaperWeave" in result.output


def test_init_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--help"])
    assert result.exit_code == 0


def test_ingest_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["ingest", "--help"])
    assert result.exit_code == 0


def test_summarize_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["summarize", "--help"])
    assert result.exit_code == 0


def test_qa_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["qa", "--help"])
    assert result.exit_code == 0


def test_citations_forward_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["citations", "forward", "--help"])
    assert result.exit_code == 0


def test_export_summary_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["export", "summary", "--help"])
    assert result.exit_code == 0


def test_export_qa_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["export", "qa", "--help"])
    assert result.exit_code == 0


def test_doctor_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor", "--help"])
    assert result.exit_code == 0
