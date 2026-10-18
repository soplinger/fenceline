import json
import math
import pathlib

import pytest

import fenceline

ROOT = pathlib.Path(__file__).resolve().parent.parent

SIMPLE = """\
units m
height 1.0
buried 0.5
spacing 2.0
rails 1
stock 2.0
waste 0
run a 6.0
"""


def plan_for(text):
    site, errors, _ = fenceline.parse_site(text)
    assert errors == []
    return fenceline.build_plan(site)


def test_bays_and_posts_for_plain_run():
    plan = plan_for(SIMPLE)
    run = plan["runs"][0]
    assert run["bays"] == 3
    assert run["posts"] == 4
    assert run["net_length"] == pytest.approx(6.0)


def test_gate_adds_posts_and_removes_length():
    text = "units m\nheight 1\nspacing 2.4\nstock 2.4\nrails 0\nrun north 12.0 gate 1.0@4.0\n"
    plan = plan_for(text)
    run = plan["runs"][0]
    assert run["posts"] == 7
    assert run["bays"] == 5
    assert run["net_length"] == pytest.approx(11.0)


def test_rail_pieces_pack_onto_stock_boards():
    plan = plan_for(SIMPLE)
    assert plan["totals"]["rail_pieces"] == 3
    assert plan["totals"]["boards_needed"] == 3
    assert plan["totals"]["boards_ordered"] == 3


def test_waste_allowance_rounds_board_order_up():
    text = SIMPLE.replace("waste 0", "waste 10")
    plan = plan_for(text)
    assert plan["totals"]["boards_needed"] == 3
    assert plan["totals"]["boards_ordered"] == 4


def test_pickets_count_from_width_and_gap():
    text = SIMPLE.replace("rails 1", "rails 0\npickets 0.10 0.02").replace("run a 6.0", "run a 4.0")
    plan = plan_for(text)
    run = plan["runs"][0]
    assert run["bays"] == 2
    assert run["picket_pieces"] == 32


def test_concrete_bags_come_from_buried_depth():
    plan = plan_for(SIMPLE)
    totals = plan["totals"]
    assert totals["concrete_m3"] == pytest.approx(4 * math.pi * 0.15 ** 2 * 0.5)
    assert totals["bags"] == 12


def test_feet_units_are_converted_to_metres():
    text = ("units ft\nheight 3\nburied 2\nspacing 8\nrails 0\nstock 8\n"
            "run a 20\n")
    plan = plan_for(text)
    assert plan["totals"]["post_length"] == pytest.approx(5 * 0.3048)
    assert plan["runs"][0]["bays"] == 3
    assert plan["runs"][0]["posts"] == 4


def test_sample_site_post_count_is_exact():
    site, errors, _ = fenceline.parse_site((ROOT / "garden.fence").read_text(encoding="utf-8"))
    assert errors == []
    plan = fenceline.build_plan(site)
    assert plan["totals"]["posts"] == 24
    assert [run["posts"] for run in plan["runs"]] == [7, 5, 6, 6]


def test_errors_carry_line_numbers():
    text = ("units m\nheight 1\nbogus 3\nspacing 2\nstock 2\n"
            "run a 5 gate 2@1 gate 1@2\n")
    _, errors, _ = fenceline.parse_site(text)
    assert (3, "unknown directive 'bogus'") in errors
    assert (6, "gates overlap") in errors


def test_missing_required_directive_is_a_file_error():
    text = "units m\nheight 1\nspacing 2\nrun a 5\n"
    _, errors, _ = fenceline.parse_site(text)
    assert (0, "missing required directive 'stock'") in errors


def test_gate_past_end_is_rejected():
    text = "units m\nheight 1\nspacing 2\nstock 2\nrun a 5 gate 2@4\n"
    _, errors, _ = fenceline.parse_site(text)
    assert any(line == 5 and "past the end" in message for line, message in errors)


def test_duplicate_directive_points_at_first_occurrence():
    text = "units m\nheight 1\nheight 2\nspacing 2\nstock 2\nrun a 5\n"
    _, errors, _ = fenceline.parse_site(text)
    assert (3, "duplicate height (first on line 2)") in errors


def test_buried_depth_warning_under_one_third_height():
    text = "units m\nheight 1.2\nburied 0.2\nspacing 2\nstock 2\nrun a 5\n"
    _, errors, warnings = fenceline.parse_site(text)
    assert errors == []
    assert any("third of the height" in message for _, message in warnings)


def test_pack_boards_first_fit_decreasing():
    pieces = [("x", 1.5), ("x", 1.0), ("x", 0.5), ("x", 1.0)]
    boards = fenceline.pack_boards(pieces, 2.0, 0.0)
    assert len(boards) == 2
    assert sum(length for board in boards for _, length in board["cuts"]) == pytest.approx(4.0)


def test_check_command_passes_on_sample(capsys):
    assert fenceline.main(["check", str(ROOT / "garden.fence")]) == 0
    assert "OK" in capsys.readouterr().out


def test_plan_json_output_is_valid(capsys):
    assert fenceline.main(["plan", str(ROOT / "garden.fence"), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["totals"]["posts"] == 24
    assert data["units"] == "m"
    assert len(data["runs"]) == 4
