#!/usr/bin/env python3
"""Fenceline: offline fence planner driven by one plain-text site file.

Describes fence runs, gates, rails, pickets and prices, then works out posts,
bays, concrete, a board cut plan and the cost. Standard library only.
"""

import argparse
import json
import math
import sys

FT_TO_M = 0.3048
EPS = 1e-9
PACK_TOL = 1e-6
PRICE_KINDS = ("post", "board", "bag")
DIRECTIVES = ("units", "height", "buried", "spacing", "rails", "pickets",
              "hole", "bag", "stock", "kerf", "waste", "price", "run")
REQUIRED = ("height", "spacing", "stock")
DEFAULTS = {"buried": 0.0, "hole": 0.30, "bag": 0.0125, "kerf": 0.0,
            "waste": 5.0, "rails": 0}

EXAMPLE = """\
# Back-garden fence. Lengths use the units line; comments start with #.
units m
height 1.2
buried 0.6
spacing 2.4
rails 3
pickets 0.10 0.02
stock 2.4
kerf 0.003
hole 0.30
bag 0.0125
waste 5

price post 14.50
price board 7.80
price bag 6.20

run north 12.0 gate 1.0@4.0
run east 9.0
run south 12.0
run west 9.0 gate 1.2@3.0
"""


class Site:
    """Parsed site file. Lengths are stored in metres; bag volume in m3."""

    def __init__(self, units):
        self.units = units
        self.factor = FT_TO_M if units == "ft" else 1.0
        self.values = {}
        self.pickets = None
        self.prices = {}
        self.runs = []

    def value(self, key):
        return self.values[key][0] if key in self.values else DEFAULTS[key]


def _number(token):
    try:
        value = float(token)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _parse_run(site, number, args, names, errors):
    if len(args) < 2:
        errors.append((number, "run needs a name and a length"))
        return
    name, length = args[0], _number(args[1])
    if name in names:
        errors.append((number, f"duplicate run name '{name}'"))
    names.add(name)
    if length is None or length <= 0:
        errors.append((number, "run length must be a positive number"))
        return
    gates, ok, index = [], True, 2
    while index < len(args):
        if args[index].lower() != "gate" or index + 1 >= len(args):
            errors.append((number, "expected 'gate WIDTH@POSITION'"))
            return
        parts = args[index + 1].split("@")
        width = _number(parts[0]) if len(parts) == 2 else None
        start = _number(parts[1]) if len(parts) == 2 else None
        if width is None or start is None or width <= 0 or start < 0:
            errors.append((number, f"bad gate '{args[index + 1]}', use WIDTH@POSITION"))
            ok = False
        else:
            gates.append((start, width))
        index += 2
    gates.sort()
    for (s1, w1), (s2, _) in zip(gates, gates[1:]):
        if s1 + w1 > s2 + EPS:
            errors.append((number, "gates overlap"))
            ok = False
    if any(s + w > length + EPS for s, w in gates):
        errors.append((number, "a gate runs past the end of the run"))
        ok = False
    if ok:
        factor = site.factor
        site.runs.append({"name": name, "length": length * factor, "line": number,
                          "gates": [(s * factor, w * factor) for s, w in gates]})


def parse_site(text):
    """Return (site, errors, warnings). Each entry is (line, message); line 0 = whole file."""
    errors, warnings = [], []
    lines = []
    for number, raw in enumerate(text.splitlines(), start=1):
        tokens = raw.split("#", 1)[0].split()
        if tokens:
            lines.append((number, tokens))

    units, units_line = "m", None
    for number, tokens in lines:
        if tokens[0].lower() != "units":
            continue
        if units_line is not None:
            errors.append((number, f"duplicate units (first on line {units_line})"))
        elif len(tokens) != 2 or tokens[1].lower() not in ("m", "ft"):
            errors.append((number, "units must be 'm' or 'ft'"))
        else:
            units, units_line = tokens[1].lower(), number

    site = Site(units)
    seen, names = {}, set()
    for number, tokens in lines:
        key, args = tokens[0].lower(), tokens[1:]
        if key == "units":
            continue
        if key not in DIRECTIVES:
            errors.append((number, f"unknown directive '{tokens[0]}'"))
            continue
        if key == "run":
            _parse_run(site, number, args, names, errors)
            continue
        if key == "price":
            if len(args) != 2 or args[0].lower() not in PRICE_KINDS:
                errors.append((number, "price needs 'post', 'board' or 'bag' and an amount"))
                continue
            amount = _number(args[1])
            kind = args[0].lower()
            if amount is None or amount < 0:
                errors.append((number, "price must be zero or more"))
            elif kind in site.prices:
                errors.append((number, f"duplicate price {kind} (first on line {site.prices[kind][1]})"))
            else:
                site.prices[kind] = (amount, number)
            continue
        if key in seen:
            errors.append((number, f"duplicate {key} (first on line {seen[key]})"))
            continue
        seen[key] = number
        _apply_setting(site, key, number, args, errors)

    for key in REQUIRED:
        if key not in seen:
            errors.append((0, f"missing required directive '{key}'"))
    if not names:
        errors.append((0, "no runs defined"))

    _cross_checks(site, seen, errors, warnings)
    return site, errors, warnings


def _apply_setting(site, key, number, args, errors):
    factor = site.factor
    if key == "units":
        return
    if key == "pickets":
        if len(args) != 2:
            errors.append((number, "pickets needs WIDTH and GAP"))
            return
        width, gap = _number(args[0]), _number(args[1])
        if width is None or width <= 0 or gap is None or gap < 0:
            errors.append((number, "picket width must be positive and gap zero or more"))
            return
        site.pickets = (width * factor, gap * factor)
        return
    if len(args) != 1:
        errors.append((number, f"{key} needs exactly one value"))
        return
    value = _number(args[0])
    if value is None:
        errors.append((number, f"{key} must be a number"))
        return
    rules = {
        "height": (True, factor), "spacing": (True, factor), "stock": (True, factor),
        "hole": (True, factor), "buried": (False, factor), "kerf": (False, factor),
        "bag": (True, 1.0), "waste": (False, 1.0),
    }
    if key == "rails":
        if value < 0 or value != int(value):
            errors.append((number, "rails must be a whole number, zero or more"))
            return
        site.values[key] = (int(value), number)
        return
    strictly_positive, scale = rules[key]
    if value < 0 or (strictly_positive and value == 0):
        errors.append((number, f"{key} must be {'positive' if strictly_positive else 'zero or more'}"))
        return
    site.values[key] = (value * scale, number)


def _cross_checks(site, seen, errors, warnings):
    if "height" in site.values and "stock" in site.values:
        height, stock = site.values["height"][0], site.values["stock"][0]
        if site.pickets and height > stock + EPS:
            errors.append((site.values["height"][1],
                           "picket length (height) is longer than the stock board"))
        if "kerf" in site.values and site.values["kerf"][0] >= stock:
            errors.append((site.values["kerf"][1], "kerf must be smaller than the stock board"))
        buried = site.value("buried")
        if buried < height / 3 - EPS:
            line = seen.get("buried", 0)
            warnings.append((line, "buried depth is under a third of the height; posts may rock"))
    if site.value("waste") == 0:
        warnings.append((seen.get("waste", 0), "waste is 0; boards are ordered with no spare"))
    if site.pickets is None and "rails" in seen and site.value("rails") == 0:
        warnings.append((seen["rails"], "no rails and no pickets; the fence is posts only"))


def run_segments(run):
    """Split a run into (start, end) stretches between its gates, in metres."""
    segments, cursor = [], 0.0
    for start, width in run["gates"]:
        segments.append((cursor, start))
        cursor = start + width
    segments.append((cursor, run["length"]))
    return segments


def split_length(length, stock):
    """Cut one length into equal pieces no longer than the stock board."""
    pieces = max(1, math.ceil(round(length / stock, 9)))
    return [length / pieces] * pieces


def pack_boards(pieces, stock, kerf):
    """First-fit-decreasing pack of (label, length) pieces; each cut costs one kerf."""
    capacity = stock + kerf
    boards = []
    for label, length in sorted(pieces, key=lambda piece: -piece[1]):
        item = length + kerf
        for board in boards:
            if board["free"] + PACK_TOL >= item:
                board["cuts"].append((label, length))
                board["free"] -= item
                break
        else:
            boards.append({"cuts": [(label, length)], "free": capacity - item})
    return boards


def build_plan(site):
    height = site.value("height")
    spacing = site.value("spacing")
    stock = site.values["stock"][0]
    kerf = site.value("kerf")
    waste = site.value("waste")
    rails = site.value("rails")
    buried = site.value("buried")
    hole = site.value("hole")
    bag_volume = site.value("bag")
    hole_area = math.pi * (hole / 2) ** 2

    runs, pieces = [], []
    for run in site.runs:
        points, bays, net = set(), [], 0.0
        for start, end in run_segments(run):
            if end - start <= EPS:
                points.add(round(start, 6))
                continue
            net += end - start
            count = max(1, math.ceil(round((end - start) / spacing, 9)))
            width = (end - start) / count
            bays.extend([width] * count)
            points.update(round(start + i * width, 6) for i in range(count + 1))
        rail_pieces = picket_pieces = 0
        for bay in bays:
            for _ in range(rails):
                for part in split_length(bay, stock):
                    pieces.append((f"{run['name']} rail", part))
                    rail_pieces += 1
            if site.pickets:
                picket_width, gap = site.pickets
                for _ in range(math.floor((bay + gap) / (picket_width + gap) + EPS)):
                    pieces.append((f"{run['name']} picket", height))
                    picket_pieces += 1
        runs.append({"name": run["name"], "length": run["length"], "net_length": net,
                     "gates": len(run["gates"]), "posts": len(points), "bays": len(bays),
                     "rail_pieces": rail_pieces, "picket_pieces": picket_pieces})

    boards = pack_boards(pieces, stock, kerf)
    boards_ordered = math.ceil(len(boards) * (1 + waste / 100) - EPS) if boards else 0
    posts = sum(run["posts"] for run in runs)
    concrete = posts * hole_area * buried
    bags = math.ceil(concrete / bag_volume - EPS) if concrete > 0 else 0

    prices = {kind: site.prices.get(kind, (0.0, 0))[0] for kind in PRICE_KINDS}
    costs = {"posts": round(posts * prices["post"], 2),
             "boards": round(boards_ordered * prices["board"], 2),
             "bags": round(bags * prices["bag"], 2)}
    totals = {"posts": posts, "bays": sum(run["bays"] for run in runs),
              "rail_pieces": sum(run["rail_pieces"] for run in runs),
              "picket_pieces": sum(run["picket_pieces"] for run in runs),
              "post_length": height + buried, "concrete_m3": concrete,
              "bags": bags, "boards_needed": len(boards), "boards_ordered": boards_ordered,
              "costs": costs, "total_cost": round(sum(costs.values()), 2)}
    return {"units": site.units, "factor": site.factor, "stock": stock, "waste": waste,
            "runs": runs, "boards": boards, "totals": totals, "prices": prices}


def _len(metres, plan):
    return f"{metres / plan['factor']:.2f} {plan['units']}"


def render_text(plan, source):
    totals = plan["totals"]
    out = [f"Fenceline plan: {source} (units: {plan['units']})", "", "Runs"]
    out.append(f"  {'run':<10}{'length':>12}{'net':>12}{'gates':>7}{'posts':>7}"
               f"{'bays':>6}{'rails':>7}{'pickets':>9}")
    for run in plan["runs"]:
        out.append(f"  {run['name']:<10}{_len(run['length'], plan):>12}"
                   f"{_len(run['net_length'], plan):>12}{run['gates']:>7}{run['posts']:>7}"
                   f"{run['bays']:>6}{run['rail_pieces']:>7}{run['picket_pieces']:>9}")
    out += ["", "Totals",
            f"  posts: {totals['posts']} of {_len(totals['post_length'], plan)}",
            f"  bays: {totals['bays']}",
            f"  concrete: {totals['concrete_m3']:.3f} m3 -> {totals['bags']} bag(s)",
            f"  boards: {totals['boards_needed']} needed, {totals['boards_ordered']} ordered "
            f"({_len(plan['stock'], plan)} stock, {plan['waste']:g}% waste allowance)",
            "", "Cost",
            f"  posts   {totals['posts']} x {plan['prices']['post']:.2f} = {totals['costs']['posts']:.2f}",
            f"  boards  {totals['boards_ordered']} x {plan['prices']['board']:.2f} = {totals['costs']['boards']:.2f}",
            f"  bags    {totals['bags']} x {plan['prices']['bag']:.2f} = {totals['costs']['bags']:.2f}",
            f"  total   {totals['total_cost']:.2f}", "", "Cut plan"]
    if not plan["boards"]:
        out.append("  no boards needed")
    for number, board in enumerate(plan["boards"], start=1):
        cuts = " | ".join(f"{label} {_len(length, plan)}" for label, length in board["cuts"])
        offcut = max(0.0, board["free"])
        out.append(f"  board {number}: {cuts} | offcut {_len(offcut, plan)}")
    return "\n".join(out) + "\n"


def plan_to_json(plan, source):
    def units(metres):
        return round(metres / plan["factor"], 4)

    totals = dict(plan["totals"])
    totals["post_length"] = units(totals["post_length"])
    return {
        "file": source, "units": plan["units"], "runs": [
            dict(run, length=units(run["length"]), net_length=units(run["net_length"]))
            for run in plan["runs"]],
        "totals": totals,
        "boards": [{"cuts": [{"part": label, "length": units(length)}
                             for label, length in board["cuts"]],
                    "offcut": units(max(0.0, board["free"]))}
                   for board in plan["boards"]],
    }


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _report_problems(errors, warnings, source):
    for number, message in sorted(errors):
        where = f"{source}:{number}" if number else source
        print(f"{where}: error: {message}", file=sys.stderr)
    for number, message in sorted(warnings):
        where = f"{source}:{number}" if number else source
        print(f"{where}: warning: {message}", file=sys.stderr)


def cmd_plan(args):
    try:
        text = _read(args.file)
    except OSError as error:
        print(f"fenceline: {error}", file=sys.stderr)
        return 2
    site, errors, warnings = parse_site(text)
    if errors:
        _report_problems(errors, warnings, args.file)
        return 1
    plan = build_plan(site)
    if args.json:
        print(json.dumps(plan_to_json(plan, args.file), indent=2))
    else:
        print(render_text(plan, args.file), end="")
    return 0


def cmd_check(args):
    try:
        text = _read(args.file)
    except OSError as error:
        print(f"fenceline: {error}", file=sys.stderr)
        return 2
    _, errors, warnings = parse_site(text)
    _report_problems(errors, warnings, args.file)
    if errors or (args.strict and warnings):
        return 1
    print(f"{args.file}: OK ({len(warnings)} warning(s))")
    return 0


def cmd_example(_args):
    print(EXAMPLE, end="")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="fenceline", description="Offline fence planner for plain-text site files.")
    sub = parser.add_subparsers(dest="command", required=True)

    plan_parser = sub.add_parser("plan", help="plan posts, boards, concrete and cost")
    plan_parser.add_argument("file")
    plan_parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    plan_parser.set_defaults(handler=cmd_plan)

    check_parser = sub.add_parser("check", help="lint a site file (CI exit codes)")
    check_parser.add_argument("file")
    check_parser.add_argument("--strict", action="store_true", help="fail on warnings too")
    check_parser.set_defaults(handler=cmd_check)

    example_parser = sub.add_parser("example", help="print a sample site file")
    example_parser.set_defaults(handler=cmd_example)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
