"""`hancom_style.py`가 **교차검증이 잡은 여섯 결함을 실제로 막는지** 잰다.

    python hancom_style_selftest.py

되돌아오는 값: 0 전부 통과 · 1 하나라도 실패

왜 있나
───────
2026-08-22에 교차검증(Codex + agy)이 첫 판에서 여섯 결함을 찾았다. **전부 조용히
실패하는 종류**라 고친 뒤에도 «정말 고쳐졌나»를 눈으로는 확인할 수 없었다 —
이 저장소가 *"항상 통과하는 검사를 만들어 놓고 통과했다고 보고한"* 전례가 있어
**깨뜨려 보는 시험**을 함께 둔다.

각 시험은 **고치기 전 코드에서 실제로 실패하던 것**이다.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

import hancom_style as H  # noqa: E402

MIME = "application/hwp+zip"

HEADER = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" version="1.4" secCnt="1">
<hh:refList><hh:fontfaces itemCnt="1"><hh:fontface lang="HANGUL" fontCnt="1">
<hh:font id="0" face="{face}" type="TTF" isEmbedded="0"/>
</hh:fontface></hh:fontfaces></hh:refList></hh:head>"""


def _cell(col: int, row: int, w: int, h: int, text: str, reorder: bool = False) -> str:
    """셀 하나 — `reorder`면 속성 순서를 뒤집어 넣는다(한컴이 그렇게 저장할 수 있다)."""
    if reorder:
        sz = '<hp:cellSz height="%d" width="%d"/>' % (h, w)
        addr = '<hp:cellAddr rowAddr="%d" colAddr="%d"/>' % (row, col)
        margin = '<hp:cellMargin top="0" bottom="0" left="170" right="170" />'
    else:
        sz = '<hp:cellSz width="%d" height="%d"/>' % (w, h)
        addr = '<hp:cellAddr colAddr="%d" rowAddr="%d"/>' % (col, row)
        margin = '<hp:cellMargin left="170" right="170" top="0" bottom="0"/>'
    return (
        '<hp:tc hasMargin="0"><hp:subList><hp:p id="%d"><hp:run><hp:t>%s</hp:t></hp:run>'
        "</hp:p></hp:subList>%s<hp:cellSpan colSpan=\"1\" rowSpan=\"1\"/>%s%s</hp:tc>"
        % (row * 10 + col, text, addr, sz, margin)
    )


def _table(cells_per_row: list[list[str]], width: int, sz_reorder: bool = False) -> str:
    col_cnt = len(cells_per_row[0])
    sz = (
        '<hp:sz widthRelTo="ABSOLUTE" width="%d" height="2000"/>' % width
        if sz_reorder
        else '<hp:sz width="%d" height="2000"/>' % width
    )
    rows = "".join("<hp:tr>%s</hp:tr>" % "".join(r) for r in cells_per_row)
    return (
        '<hp:tbl id="1" rowCnt="%d" colCnt="%d">%s'
        '<hp:inMargin left="0" right="0" top="0" bottom="0"/>%s</hp:tbl>'
        % (len(cells_per_row), col_cnt, sz, rows)
    )


def _make(section_body: str, face: str = "함초롬돋움") -> Path:
    """작은 hwpx 하나를 만든다."""
    tmpdir = Path(tempfile.mkdtemp())
    path = tmpdir / "test.hwpx"
    section = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
        'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">%s</hs:sec>' % section_body
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", MIME, compress_type=zipfile.ZIP_STORED)
        z.writestr("Contents/header.xml", HEADER.format(face=face))
        z.writestr("Contents/section0.xml", section)
    return path


def _section_of(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        return z.read("Contents/section0.xml").decode("utf-8")


RESULTS: list[tuple[bool, str]] = []


def ok(cond: bool, what: str) -> None:
    RESULTS.append((bool(cond), what))
    print("  %s %s" % ("PASS" if cond else "FAIL", what))


def main() -> int:
    print("hancom_style 자체 시험 — 교차검증이 잡은 여섯 결함")
    print()

    # ── 1. 중첩 표를 깨뜨리지 않는다 ──────────────────────────────────────
    print("[1] 표 안에 표가 있어도 바깥 표가 안 잘린다")
    inner = _table([[_cell(0, 0, 10000, 1000, "안쪽")]], 10000)
    outer_cell = (
        '<hp:tc hasMargin="0"><hp:subList><hp:p id="99">%s</hp:p></hp:subList>'
        '<hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
        '<hp:cellSz width="42520" height="2000"/>'
        '<hp:cellMargin left="170" right="170" top="0" bottom="0"/></hp:tc>' % inner
    )
    doc = _make(_table([[outer_cell]], 42520))
    before = _section_of(doc)
    got = H.fit_column_widths(doc)
    after = _section_of(doc)
    ok(after.count("<hp:tbl") == before.count("<hp:tbl"), "표 개수가 그대로다")
    ok(after.count("</hp:tbl>") == before.count("</hp:tbl>"), "닫는 태그 수가 그대로다")
    # ★★★ 교차검증 라운드 2 지적 — 위 셋만으로는 **옛 코드도 통과한다.**
    #   «중첩을 알아보고 건너뛰었나»와 «표가 바이트 그대로인가»를 봐야 진짜 시험이다.
    ok(got.get("건너뛴 표(표 안에 표)", 0) == 1, "중첩을 알아보고 건너뛰었다 (%s)" % got)
    ok(got.get("맞춘 표", 0) == 0, "중첩 표를 «맞춘 표»로 세지 않았다")
    ok(after == before, "중첩 표는 **바이트 그대로** 남았다")

    # ★★★★ **옛 방식으로는 실패한다는 것을 여기서 직접 보인다** — 이래야 항등식이 아니다.
    #   `.*?`는 안쪽 표의 닫는 태그에서 끊겨 바깥 표를 잘라 먹는다.
    import re as _re

    old_way = _re.compile(r"<hp:tbl\b.*?</hp:tbl>", _re.S)
    old_cut = old_way.search(before)
    new_cut = H._blocks(before, "tbl")
    ok(
        old_cut is not None and new_cut and len(old_cut.group(0)) < (new_cut[0][1] - new_cut[0][0]),
        "옛 방식(.*?)은 바깥 표를 짧게 잘랐다 — 지금 방식이 더 길다",
    )
    shutil.rmtree(doc.parent)

    # ── 2. 속성 순서가 달라도 찾는다 ──────────────────────────────────────
    print("[2] 속성 순서를 뒤집어 저장한 문서도 고친다")
    doc = _make(
        _table(
            [[_cell(0, 0, 21260, 2000, "가", reorder=True), _cell(1, 0, 21260, 2000, "나나나나", reorder=True)]],
            42520,
        )
    )
    got = H.fix_margins(doc)
    ok(got.get("바꾼 셀 여백", 0) == 2, "순서가 뒤집힌 셀 여백 둘을 바꿨다 (%s)" % got)
    got = H.fit_column_widths(doc)
    ok(got.get("맞춘 표", 0) == 1, "순서가 뒤집힌 표의 너비를 맞췄다 (%s)" % got)
    shutil.rmtree(doc.parent)

    # ── 3. `<hp:sz>`의 width가 뒤에 있어도 읽는다 ─────────────────────────
    print("[3] widthRelTo가 앞에 와도 표 폭을 제대로 읽는다")
    narrow = 20000
    doc = _make(
        _table(
            [[_cell(0, 0, 10000, 2000, "가"), _cell(1, 0, 10000, 2000, "나나나나")]],
            narrow,
            sz_reorder=True,
        )
    )
    H.fit_column_widths(doc)
    after = _section_of(doc)
    widths = [int(m) for m in __import__("re").findall(r'<hp:cellSz width="(\d+)"', after)]
    ok(sum(widths) == narrow, "열 너비 합이 표 폭과 같다 (%d == %d)" % (sum(widths), narrow))
    ok(max(widths) < 42520, "기본 폭(42520)으로 착각하지 않았다")
    shutil.rmtree(doc.parent)

    # ── 4. 글꼴 이름을 XML로 이스케이프한다 ──────────────────────────────
    print("[4] 글꼴 이름에 & 가 있어도 문서가 안 깨진다")
    doc = _make(_table([[_cell(0, 0, 42520, 2000, "가")]], 42520))
    H.set_font(doc, "A&B<C>")
    with zipfile.ZipFile(doc) as z:
        head = z.read("Contents/header.xml").decode("utf-8")
    ok("&amp;" in head and "&lt;" in head, "이스케이프됐다")
    import xml.etree.ElementTree as ET

    try:
        ET.fromstring(head)
        ok(True, "header가 XML로 읽힌다")
    except ET.ParseError as e:
        ok(False, "header가 깨졌다: %s" % e)
    shutil.rmtree(doc.parent)

    # ── 5. 결과가 깨지면 원본을 지킨다 ───────────────────────────────────
    print("[5] 바꾼 결과가 깨지면 원본을 그대로 둔다")
    doc = _make(_table([[_cell(0, 0, 42520, 2000, "가")]], 42520))
    original = doc.read_bytes()

    def wrecker(text: str) -> tuple[str, dict]:
        return "<이건 XML이 아니다", {"바꾼 셀 여백": 1}

    try:
        H._rewrite(doc, wrecker)
        ok(False, "깨진 결과를 막지 못했다")
    except RuntimeError:
        ok(True, "깨진 결과를 막았다")
    ok(doc.read_bytes() == original, "원본이 그대로다")
    ok(not doc.with_suffix(".tmp.hwpx").exists(), "임시 파일을 치웠다")
    shutil.rmtree(doc.parent)

    # ── 6. 아무것도 못 찾으면 알린다 ─────────────────────────────────────
    print("[6] 손댈 것이 없으면 종료코드 1로 알린다")
    doc = _make("<hp:p id=\"1\"><hp:run><hp:t>표가 없는 문서</hp:t></hp:run></hp:p>")
    saved = sys.argv
    sys.argv = ["hancom_style.py", "fix", str(doc)]
    code = H.main()
    sys.argv = saved
    ok(code == 1, "종료코드가 1이다 (실제 %s)" % code)
    shutil.rmtree(doc.parent)

    # ── 7. 병합된 표는 건드리지 않는다 ───────────────────────────────────
    print("[7] 병합된 칸이 있는 표는 손대지 않는다")
    merged = (
        '<hp:tc hasMargin="0"><hp:subList><hp:p id="1"><hp:run><hp:t>병합</hp:t></hp:run>'
        '</hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="0"/>'
        '<hp:cellSpan colSpan="2" rowSpan="1"/><hp:cellSz width="42520" height="2000"/>'
        '<hp:cellMargin left="170" right="170" top="0" bottom="0"/></hp:tc>'
    )
    doc = _make(_table([[merged]], 42520))
    got = H.fit_column_widths(doc)
    ok(got.get("건너뛴 표(병합)", 0) == 1, "병합 표를 건너뛰었다 (%s)" % got)
    ok(got.get("맞춘 표", 0) == 0, "맞춘 표로 세지 않았다")
    shutil.rmtree(doc.parent)

    # ── 8. cellSz가 없는 셀이 있으면 그 표를 건드리지 않는다 ─────────────
    print("[8] `<hp:cellSz>`가 없는 셀이 있으면 그 표를 통째로 건너뛴다")
    # ★★★ 교차검증 라운드 2 지적 — 앞 시험 [7]은 **원래 되던 병합 갈래**만 봐서
    #   이 수정에 대해서는 항등식이었다. 진짜 대상을 여기서 시험한다.
    no_sz = (
        '<hp:tc hasMargin="0"><hp:subList><hp:p id="2"><hp:run><hp:t>크기없음</hp:t></hp:run>'
        '</hp:p></hp:subList><hp:cellAddr colAddr="1" rowAddr="0"/>'
        '<hp:cellSpan colSpan="1" rowSpan="1"/>'
        '<hp:cellMargin left="170" right="170" top="0" bottom="0"/></hp:tc>'
    )
    doc = _make(_table([[_cell(0, 0, 21260, 2000, "가"), no_sz]], 42520))
    before = _section_of(doc)
    got = H.fit_column_widths(doc)
    ok(got.get("건너뛴 표(잴 수 없음)", 0) == 1, "크기 없는 셀이 있는 표를 건너뛰었다 (%s)" % got)
    ok(got.get("맞춘 표", 0) == 0, "«맞춘 표»로 세지 않았다")
    ok(_section_of(doc) == before, "그 표를 바이트 그대로 두었다")
    shutil.rmtree(doc.parent)

    # ── 9. 망가진 표 뒤의 멀쩡한 표를 놓치지 않는다 ──────────────────────
    print("[9] 닫는 태그가 없는 표·자기닫힘 태그 뒤의 표를 놓치지 않는다")
    # ★★★ 교차검증 라운드 2 Codex 12·13번 — 전에는 짝을 못 찾으면 **거기서 멈춰**
    #   뒤에 있는 멀쩡한 표가 조용히 빠졌다.
    ok(
        len(H._blocks("<hp:tbl a>닫는게없다<hp:tbl b>온전</hp:tbl>", "tbl")) == 1,
        "짝 없는 여는 태그 뒤의 표를 찾았다",
    )
    ok(
        len(H._blocks("<hp:tbl a/><hp:tbl b>온전</hp:tbl>", "tbl")) == 1,
        "자기닫힘 태그를 여는 태그로 세지 않았다",
    )
    siblings = H._blocks("<hp:tbl a>A</hp:tbl><hp:tbl b>B</hp:tbl>", "tbl")
    ok(len(siblings) == 2, "나란히 있는 표 둘을 다 찾았다")
    ok(
        len(siblings) == 2 and siblings[0][1] <= siblings[1][0],
        "나란히 있는 표의 범위가 겹치지 않는다",
    )

    print()
    failed = [w for good, w in RESULTS if not good]
    if failed:
        print("실패 %d개:" % len(failed))
        for w in failed:
            print("  - %s" % w)
        return 1
    print("전부 통과 (%d개)" % len(RESULTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
