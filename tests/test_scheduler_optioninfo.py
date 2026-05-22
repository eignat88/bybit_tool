import subprocess


def test_scheduler_once_optioninfo_regression() -> None:
    proc = subprocess.run(
        ["python", "main.py", "scheduler", "--symbols", "BTCUSDT,ETHUSDT", "--once"],
        capture_output=True,
        text=True,
    )
    output = f"{proc.stdout}\n{proc.stderr}"
    assert proc.returncode == 0, output
    assert "OptionInfo" not in output
    assert "ProgrammingError" not in output
    assert "cannot adapt type" not in output
    assert "Traceback" not in output
    assert "symbols_processed=2" in output
    assert "intervals_processed=1" in output
