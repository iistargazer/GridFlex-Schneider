"""Guards for the two artefacts that face a judge: the dashboard and the docs.

The page a judge opens is a build output, so it must come from the same writer as
the local copy, and the numbers the docs quote must still be the numbers in
`outputs/results.json`. Both guards fail loudly instead of drifting quietly.
"""
import json
import pathlib

import pytest

from gridflex.report import make_dashboard

ROOT = pathlib.Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "outputs" / "dashboard.html"
SITE = ROOT / "outputs" / "site" / "index.html"
RESULTS = ROOT / "outputs" / "results.json"


def test_dashboard_writer_emits_identical_local_and_publishable_page(tmp_path):
    main = tmp_path / "dashboard.html"
    site = tmp_path / "site" / "index.html"
    make_dashboard({"meta": {"site": "test"}, "scenarios": {}}, str(main), str(site))

    assert main.read_bytes() == site.read_bytes()
    text = main.read_text(encoding="utf-8")
    assert '"site": "test"' in text                       # payload embedded
    assert '<script src=' not in text                     # library inlined, not linked
    assert not (tmp_path / "chart.umd.min.js").exists()   # no sidecar to upload by mistake
    assert not (site.parent / "chart.umd.min.js").exists()


def test_committed_site_copy_is_the_same_file_as_the_dashboard():
    assert DASHBOARD.exists() and SITE.exists(), "both pages are committed artefacts"
    assert DASHBOARD.read_bytes() == SITE.read_bytes(), (
        "outputs/site/index.html has diverged from outputs/dashboard.html; "
        "regenerate both with make_dashboard instead of copying by hand"
    )


def _load_results():
    if not RESULTS.exists():
        return None
    return json.loads(RESULTS.read_text(encoding="utf-8"))


RES = _load_results()


def _cases():
    """(value quoted in a doc, doc path) pairs computed from the built results.

    Each string is deliberately specific - a headline with its CI or its unit -
    so an edit that changes one occurrence but leaves the number quoted
    elsewhere cannot pass as a silent discrepancy.
    """
    if RES is None:
        return []
    ci, econ, sizing = RES["ci"], RES["economics"], RES["sizing"]

    def trio(mode):
        c = ci[mode]["outage_hours_per_day"]
        return f'{c["mean"]:.2f}** [{c["lo"]:.2f}, {c["hi"]:.2f}]'

    hi, lo = ci["mpc_full"], ci["grid_only"]
    lifeline = [p for p in sizing["points"] if p["fee_scheme"] == "lifeline"]
    cheapest = min(p["net_cost_low_income_per_hh_month_inr"] for p in lifeline)
    first_action = RES["discom"]["dr_actions"][0]["credit_inr"]
    bill = ci["mpc_full"]["bill_inr_per_hh_month"]["mean"]
    bill_delta = abs(econ["bill_saving_vs_pv_battery_per_hh_month_inr"])
    return [
        (trio("mpc_full"), "README.md"),
        (trio("grid_only"), "README.md"),
        (trio("pv_batt_naive"), "README.md"),
        (f'{hi["outage_hours_per_day"]["mean"]:.2f} h/day', "README.md"),
        (f'**{bill:.0f}**', "README.md"),
        (f'{econ["net_value_per_hh_month_inr"]:.1f}**', "docs/WRITEUP.md"),
        (f'{econ["outage_value_per_hh_month_inr"]:.1f}', "docs/WRITEUP.md"),
        (f'{cheapest:.1f}**', "docs/DECK.md"),
        (f'{first_action:.0f}/day', "docs/DECK.md"),
        (f'{lo["outage_hours_per_day"]["mean"]:.2f} → '
         f'{ci["pv_batt_naive"]["outage_hours_per_day"]["mean"]:.2f} → '
         f'**{hi["outage_hours_per_day"]["mean"]:.2f}**', "docs/SUBMISSION_GUIDE.md"),
        (f'₹{bill_delta:.1f}', "docs/SUBMISSION_GUIDE.md"),
    ]


def test_results_json_exists():
    assert RESULTS.exists(), (
        "outputs/results.json is committed evidence: the docs and dashboard quote it, "
        "so it must stay in the repository"
    )


@pytest.mark.parametrize("value,doc", _cases())
def test_docs_quote_the_current_numbers(value, doc):
    text = (ROOT / doc).read_text(encoding="utf-8")
    assert value in text, (
        f"{value} from outputs/results.json is not in {doc}; the docs have drifted from "
        "the built results - update the doc (or rerun everything) deliberately"
    )
