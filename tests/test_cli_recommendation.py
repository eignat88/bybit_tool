from typer.testing import CliRunner

from app.cli.commands import app


def test_analyze_has_recommend_option():
    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "--recommend" in result.stdout


def test_recommend_has_intervals_option():
    runner = CliRunner()
    result = runner.invoke(app, ["recommend", "--help"])
    assert result.exit_code == 0
    assert "--intervals" in result.stdout
