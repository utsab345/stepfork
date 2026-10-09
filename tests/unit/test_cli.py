from typer.testing import CliRunner

from stepfork import __version__
from stepfork.cli.main import app

runner = CliRunner()


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Behavioral regression testing for AI agents." in result.stdout


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert f"stepfork {__version__}" in result.stdout


def test_cli_without_command_shows_help() -> None:
    result = runner.invoke(app)

    assert result.exit_code == 0
    assert "Behavioral regression testing for AI agents." in result.stdout
