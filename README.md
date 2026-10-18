# Fenceline

**Plan a fence from one plain-text file: posts, bays, concrete, a board cut plan and the cost.**

Fenceline reads a small site file that describes your fence runs, gates, rails, pickets and prices, then works out how many posts and bags of concrete you need, how many rail and picket boards to buy, how they pack onto stock lengths, and what it all costs. It runs entirely offline with the Python 3 standard library. There are no accounts, no API keys and no network calls.

## Features

- **One readable site file.** Plain text with `#` comments, one directive per line, and runs described in a single line each.
- **Line-numbered errors.** Every problem is reported as `site.fence:6: error: gates overlap`, so you can jump straight to it.
- **Units in metres or feet.** Set `units ft` and every length is converted exactly; output is shown in the units you chose.
- **Gates anywhere on a run.** `gate 1.0@4.0` places a 1.0-wide opening starting 4.0 along the run. Gate posts are counted automatically, and shared ends are never double-counted.
- **Bay layout to a maximum spacing.** Each stretch is split into the fewest bays that stay within your post spacing, so bays come out even.
- **Post count and post length.** Posts are counted per run, and each post's length is the height plus the buried depth.
- **Concrete from buried depth.** Hole diameter and buried depth give the concrete volume, rounded up to whole bags.
- **Rails cut from stock.** Each bay gets the rails you ask for. Pieces longer than the stock board are split, then packed first-fit-decreasing onto boards.
- **Pickets from width and gap.** Picket count per bay is worked out from picket width and gap. Pickets are cut from the same boards.
- **Saw kerf.** Each cut takes up your blade's kerf, so the board packing reflects what the saw really removes.
- **Waste allowance.** Board orders include a percentage spare on top of the packed count.
- **Cost to the cent.** Posts, boards and bags are priced separately, with a total.
- **Cut plan.** Each board is listed with its cuts and offcut, so you know what to cut from what.
- **Text or JSON output.** `plan --json` prints machine-readable results for other tools.
- **CI-friendly linting.** `check` exits 0 when the file is clean, 1 on errors, and 2 when the file can't be read. `--strict` also fails on warnings.
- **Built-in sample.** `example` prints a working site file to start from.

## Quick start

Fenceline needs Python 3.9 or newer and nothing else.

```sh
python3 fenceline.py example > my-fence.fence   # or use the included garden.fence
python3 fenceline.py check garden.fence         # lint the site file
python3 fenceline.py plan garden.fence          # plan posts, boards, concrete and cost
```

The included `garden.fence` describes a four-run garden with one gate on the north side and one on the west:

```text
units m
height 1.2
buried 0.6
spacing 2.4
rails 3
pickets 0.10 0.02
stock 2.4
kerf 0.003
...
run north 12.0 gate 1.0@4.0
run east 9.0
run south 12.0
run west 9.0 gate 1.2@3.0
```

Running `plan garden.fence` prints a table of runs with their posts, bays, rails and pickets, then totals for posts, concrete bags and boards, a cost breakdown, and a board-by-board cut plan. Posts come to 24 across the four runs.

## Site file reference

| Directive | Meaning |
| --- | --- |
| `units m` or `units ft` | Units for every length (default `m`). |
| `height H` | Fence height above ground (required). |
| `buried D` | Depth each post is set in concrete (default `0`). |
| `spacing S` | Maximum post spacing, centre to centre (required). |
| `rails N` | Rails per bay (default `0`). |
| `pickets W G` | Picket width and gap. Leave out for a fence with no pickets. |
| `stock L` | Length of the board you buy (required). |
| `kerf K` | Saw kerf per cut (default `0`). |
| `hole D` | Post hole diameter, in metres (default `0.30`). |
| `bag V` | Volume of one concrete bag, in cubic metres (default `0.0125`). |
| `waste P` | Percentage of spare boards to order (default `5`). |
| `price post\|board\|bag X` | Unit prices. |
| `run NAME LENGTH [gate W@P ...]` | A fence run. Gates are width and start position from the run's start. |

Rules the checker enforces include: directives may appear only once, picket height must fit the stock board, gates must sit inside their run without overlapping, and at least one run is required. A warning is raised when the buried depth is less than a third of the height.

## Commands

```text
python3 fenceline.py plan FILE [--json]        plan the fence
python3 fenceline.py check FILE [--strict]     lint the site file
python3 fenceline.py example                   print a sample site file
```

Exit codes: `plan` and `check` return `0` on success, `1` when the file has errors (and warnings under `--strict`), and `2` when the file can't be read.

## Running the tests

Install pytest if you don't have it, then run the suite from the project folder:

```sh
python3 -m pip install pytest
python3 -m pytest -q tests
```

The tests cover parsing and line-numbered errors, bay and post counts with gates, rail and picket counts, board packing, waste rounding, concrete bags, feet-to-metre conversion, and the CLI's JSON output and check command.

## Project layout

```text
fenceline.py            the planner and command-line tool (standard library only)
garden.fence            sample site file
tests/conftest.py       puts the project folder on the import path
tests/test_fenceline.py unit and integration tests
```

## Limits

Fenceline plans straight and gated runs. It does not model corners, slopes, stepped fences, gate hardware, or posts that are cut to ground level. It packs boards with a first-fit-decreasing heuristic, which is close to optimal for fence-sized jobs but not guaranteed minimal. Costs are plain sums of your unit prices, with no tax or delivery.
