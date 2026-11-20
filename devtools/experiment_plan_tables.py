"""Fill the tables of the gold-frame experiment plan (GoldFrameCalibration/docs/EXPERIMENT_PLAN_en.md) with the lines
the program plans from the newest configuration of the capillary in configs/.

The numbers in the document are an example for planning the beamtime: on the day, the plan is made again in
GoldFrameCalibration (Measurement plan…) from the configuration in use then.

Usage:  python devtools/experiment_plan_tables.py      then  python devtools/build_guides.py plan
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "src"))

from quickalignment.core.calibration import CalibrationStore  # noqa: E402
from quickalignment.goldframe.cli import plan_issues  # noqa: E402
from quickalignment.goldframe.model import GoldFrame, Setup, sn_point_plan, survey_plan  # noqa: E402

DOC = HERE / "GoldFrameCalibration" / "docs" / "EXPERIMENT_PLAN_en.md"
# measurement order: SRn moves only 120 -> 75 -> 165, then SRz steps at 165
ORDER = [("A", 120.0, 0.0), ("B", 75.0, 0.0), ("B", 165.0, 0.0)] + [("C", 165.0, z) for z in (-25.0, -18.0, -11.0, -4.0, 3.0, 10.0)]


def _deg(z: float) -> str:
    return f"{z:+g}" if z else "0"


def _between(text: str, start: str, end: str, body: str) -> str:
    pattern = re.compile(re.escape(start) + ".*?" + re.escape(end), re.S)
    return pattern.sub(lambda _: f"{start}\n{body}\n{end}", text)


def main() -> int:
    record = CalibrationStore().latest("capillary")
    guide = Setup(record.config, GoldFrame(height=0.05))
    plan = survey_plan(guide)
    issues = plan_issues(plan, guide, record)
    settings, lines = [], []
    for k, (group, srn, srz) in enumerate(ORDER, 1):
        rows = [(p, i) for p, i in zip(plan, issues) if p.group == group and p.srn == srn and p.srz == srz]
        sts = ", ".join(f"{p.st:.3f}" for p, _ in rows)
        p0 = rows[0][0]
        settings.append(f"| S{k} | {group} | {srn:g} | {_deg(srz)} | {p0.sn:.3f} | {len(rows)} | {sts} | "
                        f"{p0.sz_from:.3f} → {p0.sz_to:.3f} |")
        for j, (p, i) in enumerate(rows, 1):
            lines.append(f"| S{k}.{j} | {group} | {srn:g} | {_deg(srz)} | {p.st:.4f} | {p.sn:.4f} | {p.sz_from:.4f} | "
                         f"{p.sz_to:.4f} | {'; '.join(i) or 'ok'} | |")
    points = [f"| P{k} | {p.srn:g} | {_deg(p.srz)} | {p.st:.4f} | {p.sz:.4f} | {p.sn:.4f} | | |"
              for k, p in enumerate(sn_point_plan(guide), 1)]
    head = f"Example placed with the configuration **{record.label}** (`{record.path.name}`), frame at the riser centre, " \
           "gold 0.05 mm above the riser top."
    text = DOC.read_text(encoding="utf-8")
    text = _between(text, "<!-- SETTINGS TABLE -->", "<!-- /SETTINGS TABLE -->", "\n".join([
        head, "", "| setting | group | SRn (°) | SRz (°) | SN (mm) | lines | ST of the lines (mm) | SZ scan (mm) |",
        "|---|---|---|---|---|---|---|---|", *settings]))
    text = _between(text, "<!-- LINES TABLE -->", "<!-- /LINES TABLE -->", "\n".join([
        "| line | group | SRn | SRz | ST | SN | SZ from | SZ to | check | file / done |",
        "|---|---|---|---|---|---|---|---|---|---|", *lines]))
    text = _between(text, "<!-- SN TABLE -->", "<!-- /SN TABLE -->", "\n".join([
        "| point | SRn | SRz | ST start | SZ | expected SN | measured ST | measured SN |",
        "|---|---|---|---|---|---|---|---|", *points]))
    DOC.write_text(text, encoding="utf-8")
    print(DOC.relative_to(HERE), f"({len(lines)} lines, {sum(bool(i) for i in issues)} with problems)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
