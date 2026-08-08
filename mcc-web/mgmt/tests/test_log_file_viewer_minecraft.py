# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from mgmt.log_file_viewer import parse_log_line


def test_parse_paper_console_line():
    parsed = parse_log_line(
        "[08:33:44 INFO]: [bootstrap] Loading Paper 26.1.2-74"
    )
    assert parsed["level"] == "INFO"
    assert parsed["timestamp"] == "08:33:44"
    assert "bootstrap" in parsed["message"]


def test_parse_paper_warn_and_ansi():
    parsed = parse_log_line(
        "\x1b[33;1m[08:30:41 WARN]: **** SERVER IS RUNNING IN OFFLINE/INSECURE MODE!\x1b[m"
    )
    assert parsed["level"] == "WARNING"
    assert "OFFLINE" in parsed["message"]
    assert "\x1b" not in parsed["raw"]


def test_parse_truncates_jline_spam():
    spam = "> " * 5000
    parsed = parse_log_line(spam)
    assert len(parsed["message"]) < 5000
    assert "truncated" in parsed["message"]


def test_parse_velocity_and_limbo():
    vel = parse_log_line("[10:30:07 INFO]: Booting up Velocity 4.1.0-SNAPSHOT")
    assert vel["level"] == "INFO"
    limbo = parse_log_line("[10:30:14 Info] Loading Limbo Version 2026.0.1-ALPHA\x1b[0m")
    assert limbo["level"] == "INFO"
    assert "Limbo" in limbo["message"]
