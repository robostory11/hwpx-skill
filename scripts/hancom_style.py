"""문서를 한글이 만든 것처럼 다듬는다 — 표 셀 여백 · 열 너비 · 글꼴

왜 필요한가 (2026-08-22 신설)
─────────────────────────────
프로그램으로 조립한 표는 **글씨가 셀 벽에 딱 붙는다.** 사장님이 발송 직전에 눈으로
잡으셨다 — *"너가 만든거는 글씨가 표안에 그냥 여유없이 바로 붙어있어. 근데 기본 표
속성은 내부에 어느정도 너비 간격이 존재하거든."*

원인은 여백 두 곳이었다. `md2hwpx.py`·`build_hwpx.py`가 만든 표는
`cellMargin`이 170/170/0/0 이고 `inMargin`이 0/0/0/0 이다.

★★★★ **셀 여백만 고치면 화면이 안 바뀐다.** 셀에 `hasMargin="0"`이 붙어 있으면
한글은 그 셀의 `<hp:cellMargin>`을 **안 보고** 표의 `<hp:inMargin>`을 쓴다.
2026-08-22에 셀 값만 바꿔 놓고 «적용됐다»고 보고했다가 사장님께
*"표 내부 여백 적용된거 맞아?"* 라는 되물음을 받았다 — 안 먹고 있었다.
**그래서 이 도구는 둘 다 바꾼다.** 어느 해석에서든 같은 값이 되어 안전하다.

기본값은 추측하지 않고 **실측했다.** 한컴이 실제로 만든 문서 넷(행정안전부 2025 업무계획 ·
정부 표준 보도자료 · 문제지 양식 · 보고서 양식)에서 cellMargin을 전수로 세었더니:

    left=510  right=510  top=141  bottom=141   → 285회 (압도적 다수)
    left=141  right=141  top=141  bottom=141   →  27회
    left=0    right=0    top=0    bottom=0     →  12회

510 HWPUNIT = 5.1pt (약 1.8mm) · 141 HWPUNIT = 1.41pt (약 0.5mm).

쓰는 법
───────
    python hancom_style.py fix   문서.hwpx              # 여백을 한글 기본으로 (셀+표 둘 다)
    python hancom_style.py fit   문서.hwpx              # 열 너비를 글자 수에 맞춰
    python hancom_style.py font  문서.hwpx              # 글꼴을 맑은 고딕으로
    python hancom_style.py all   문서.hwpx              # 위 셋 다 (권장)
    python hancom_style.py font  문서.hwpx --face 나눔고딕   # 다른 글꼴로
    python hancom_style.py check 문서.hwpx              # 지금 상태만 본다

되돌아오는 값: 0 성공 · 1 손댈 것을 못 찾음(조용한 실패 의심) · 2 쓸 수 없는 입력

왜 맑은 고딕이 기본인가
───────────────────────
한컴 기본 글꼴인 **함초롬돋움·함초롬바탕은 한컴오피스를 깐 PC에만 있다.** 받는 쪽이
한글 없이 뷰어나 다른 프로그램으로 열면 글꼴이 딴것으로 바뀌어 줄이 밀린다.
**맑은 고딕은 윈도우 기본 글꼴**이라 어디서 열어도 같게 보인다 — 밖으로 나가는
문서(발주처·관공서 제출)에는 이쪽이 안전하다.

교차검증이 잡아 준 것 (2026-08-22 · Codex + agy)
────────────────────────────────────────────────
첫 판은 아래 여섯이 열려 있었다. **전부 조용히 실패하는 종류**라 적어 둔다.

1. **중첩 표를 깨뜨렸다** — `<hp:tbl>.*?</hp:tbl>`가 안쪽 표의 닫는 태그에서 끊겨
   바깥 표가 잘렸다. → 지금은 **중첩을 세어 짝을 맞춰** 잘라내고, 안쪽 표가 있으면
   그 표는 **건드리지 않는다.**
2. **속성 순서를 강제했다** — `<hp:cellSz width= height=>`처럼 순서를 못박아,
   `height`가 먼저 오거나 `/>` 앞에 공백이 있으면 **매칭 0인데 초록**이었다.
   → 속성을 하나씩 따로 찾는다.
3. **`<hp:sz width=`가 `widthRelTo`에 밀렸다** — 한컴은 `widthRelTo`를 먼저 쓰기도 한다.
   그러면 폭을 못 읽고 **42520으로 착각**해 좁은 표를 넓혀 버렸다.
4. **글꼴 이름을 XML로 이스케이프하지 않았다** — `&`·`<`가 든 이름을 주면 header가 깨져
   한컴이 문서를 못 연다.
5. **검증 없이 원본을 덮어썼다** — 쓰다 잘못되면 **원본이 사라진다.**
   → 임시 파일을 XML로 파싱하고 필수 엔트리를 확인한 **뒤에만** 바꿔치기한다.
6. **아무것도 못 찾아도 «성공»이었다** — 정규식이 죽으면 0건인데 조용히 0을 반환했다.
   → 손댈 것을 하나도 못 찾으면 **종료코드 1**로 알린다.
"""

from __future__ import annotations

import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

# ★★★ 윈도우 콘솔은 cp949라 한글·기호를 찍다가 UnicodeEncodeError로 **죽는다.**
#   이 스킬의 다른 스크립트(text_extract.py)도 같은 이유로 죽는 것을 2026-08-22에 겪었다.
#   찍을 수 없는 글자는 물음표로 바꿔서라도 **일을 끝내게** 한다 — 표시가 깨지는 것보다
#   도구가 죽어 «아무 일도 안 된 것»이 훨씬 나쁘다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")

# ── 한글 「표 만들기」 기본 여백 (위 머리말의 실측값) ──────────────────────
HANCOM_CELL_MARGIN = {"left": 510, "right": 510, "top": 141, "bottom": 141}

# 본문 폭 — A4 세로에 좌우 30mm 여백일 때. 표에서 폭을 못 읽었을 때만 쓴다
BODY_WIDTH = 42520

# 열 하나가 이보다 좁아지면 글씨가 세로로 쌓여 읽기 어렵다
MIN_COL_WIDTH = 4000

# 밖으로 나가는 문서의 기본 글꼴 — 위 머리말의 까닭 참조
DEFAULT_FACE = "맑은 고딕"

_LINESEG_RE = re.compile(r"<hp:linesegarray>.*?</hp:linesegarray>", re.S)
_FONT_RE = re.compile(r'(<hh:font[^>]*face=")([^"]*)(")')


def _margin_re(tag: str) -> re.Pattern:
    """여백 태그를 **속성 순서에 매이지 않고** 찾는다.

    ★★ 교차검증이 잡은 자리다. `left right top bottom` 순서를 못박으면 한컴이
      다른 순서로 저장한 문서에서 **매칭이 0인데 초록**이 된다.
    """
    return re.compile(r"<hp:%s\b[^>]*/>" % tag)


CELL_MARGIN_RE = _margin_re("cellMargin")
IN_MARGIN_RE = _margin_re("inMargin")

_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def _attrs(tag_text: str) -> dict[str, str]:
    """태그 하나의 속성을 사전으로 — 순서에 매이지 않는다."""
    return dict(_ATTR_RE.findall(tag_text))


def _margin_values(tag_text: str) -> tuple[str, ...]:
    a = _attrs(tag_text)
    return tuple(a.get(k, "") for k in ("left", "right", "top", "bottom"))


def _find_tag(text: str, tag: str) -> re.Match | None:
    """자기닫힘 태그 하나를 찾는다(속성 순서 무관)."""
    return re.search(r"<hp:%s\b[^>]*/>" % tag, text)


def _blocks(text: str, tag: str) -> list[tuple[int, int, bool]]:
    """`<hp:tag …>`부터 짝이 맞는 `</hp:tag>`까지를 잘라 낸다.

    돌려주는 것: (시작, 끝, 안에 같은 태그가 또 있나)

    ★★★ **중첩을 세어 짝을 맞춘다.** `.*?`로 자르면 안쪽 표의 닫는 태그에서 끊겨
      **바깥 표가 잘린다**(교차검증 Codex·agy가 함께 지적). 표 안에 표가 들어가는
      문서는 드물지 않다.
    """
    # * 자기닫힘 태그(<hp:tbl/>)는 여는 태그가 아니다 - 세면 뒤 표를 삼킨다(교차검증 라운드 2)
    opener = re.compile(r"<hp:%s\b(?![^>]*/>)" % tag)
    closer = "</hp:%s>" % tag
    out: list[tuple[int, int, bool]] = []
    pos = 0
    while True:
        m = opener.search(text, pos)
        if m is None:
            return out
        depth = 0
        i = m.start()
        nested = False
        while i < len(text):
            nxt_open = opener.search(text, i + 1)
            nxt_close = text.find(closer, i + 1)
            if nxt_close == -1:
                # ** 짝이 없다 - **그 자리만** 건너뛰고 뒤를 계속 찾는다.
                #   전에는 여기서 통째로 멈춰 **뒤에 있는 멀쩡한 표가 조용히 빠졌다**
                #   (교차검증 라운드 2 Codex 12번).
                pos = m.end()
                break
            if nxt_open is not None and nxt_open.start() < nxt_close:
                depth += 1
                nested = True
                i = nxt_open.start()
                continue
            if depth == 0:
                end = nxt_close + len(closer)
                out.append((m.start(), end, nested))
                pos = end
                break
            depth -= 1
            i = nxt_close
        else:
            pos = m.end()


def _validate(tmp: Path) -> str | None:
    """바꿔치기 전에 **읽을 수 있는 문서인지** 본다. 문제가 있으면 까닭을 돌려준다.

    ★★★★ 교차검증 Codex 지적 — *"The original file is replaced without post-write
      validation … A malformed font value or partial rewrite therefore destroys the
      only source copy."* 원본은 하나뿐이다.
    """
    try:
        with zipfile.ZipFile(tmp) as z:
            broken = z.testzip()
            if broken is not None:
                return "압축이 깨졌습니다: %s" % broken
            names = z.namelist()
            for must in ("mimetype", "Contents/header.xml", "Contents/section0.xml"):
                if must not in names:
                    return "필수 파일이 없습니다: %s" % must
            if names[0] != "mimetype":
                return "mimetype이 첫 항목이 아닙니다"
            for name in names:
                if name.endswith(".xml"):
                    try:
                        ET.fromstring(z.read(name))
                    except ET.ParseError as e:
                        return "XML이 깨졌습니다 (%s): %s" % (name, e)
    except zipfile.BadZipFile as e:
        return "파일을 열 수 없습니다: %s" % e
    return None


def _rewrite(path: Path, changer, entries: tuple[str, ...] | None = None) -> dict:
    """고른 XML만 바꿔 다시 묶는다 — 나머지 엔트리는 바이트 그대로 옮긴다.

    ★ `entries`가 없으면 섹션 전부. 있으면 그 이름들만.
    ★★ **검증을 지난 뒤에만** 원본을 바꿔치기한다.
    """
    src = Path(path)
    tmp = src.with_suffix(".tmp.hwpx")
    stats: dict = {}
    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        if entries is None:
            targets = {
                n
                for n in zin.namelist()
                if n.startswith("Contents/section") and n.endswith(".xml")
            }
        else:
            targets = set(entries)
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename in targets:
                text, got = changer(data.decode("utf-8"))
                for key, val in got.items():
                    stats[key] = stats.get(key, 0) + val
                data = text.encode("utf-8")
            if item.filename == "mimetype":
                zout.writestr(item, data, compress_type=zipfile.ZIP_STORED)
            else:
                zout.writestr(item, data)

    why = _validate(tmp)
    if why is not None:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("바꾼 결과가 성하지 않아 원본을 그대로 두었습니다 — %s" % why)
    shutil.move(str(tmp), str(src))
    return stats


# ── 1. 여백을 한글 기본으로 (셀 + 표 둘 다) ───────────────────────────────
def fix_margins(path: Path) -> dict:
    want = tuple(str(HANCOM_CELL_MARGIN[k]) for k in ("left", "right", "top", "bottom"))
    cell_xml = (
        '<hp:cellMargin left="{left}" right="{right}" top="{top}" bottom="{bottom}"/>'
    ).format(**HANCOM_CELL_MARGIN)
    in_xml = (
        '<hp:inMargin left="{left}" right="{right}" top="{top}" bottom="{bottom}"/>'
    ).format(**HANCOM_CELL_MARGIN)

    def changer(text: str) -> tuple[str, dict]:
        counts = {"바꾼 셀 여백": 0, "이미 기본값": 0, "바꾼 표 안쪽여백": 0}

        def sub_cell(mo: re.Match) -> str:
            if _margin_values(mo.group(0)) == want:
                counts["이미 기본값"] += 1
                return mo.group(0)
            counts["바꾼 셀 여백"] += 1
            return cell_xml

        def sub_in(mo: re.Match) -> str:
            if _margin_values(mo.group(0)) == want:
                return mo.group(0)
            counts["바꾼 표 안쪽여백"] += 1
            return in_xml

        # ★★ 둘 다 바꾼다 — `hasMargin="0"`인 셀은 표의 안쪽 여백을 쓴다(머리말 참조)
        return IN_MARGIN_RE.sub(sub_in, CELL_MARGIN_RE.sub(sub_cell, text)), counts

    return _rewrite(path, changer)


# 옛 이름 — 부르는 곳이 있을 수 있어 남겨 둔다
fix_cell_margins = fix_margins


# ── 2. 열 너비를 글자 수에 맞춰 ───────────────────────────────────────────
def text_width(s: str) -> float:
    """글자 폭을 대략 잰다 — 한글·한자·전각은 1, 그 밖은 0.5로 센다."""
    total = 0.0
    for ch in s:
        total += 1.0 if ord(ch) > 0x2E7F else 0.5
    return total


def fit_column_widths(path: Path) -> dict:
    """표마다 열의 글자 폭을 재어 너비를 나눈다.

    건너뛰는 표 — **건너뛴 수를 결과에 찍으므로 조용히 빠지지 않는다.**
      · 병합된 칸(colSpan·rowSpan > 1)이 있는 표 — 좌표가 어긋나면 통째로 깨진다
      · 표 안에 표가 있는 표 — 안쪽 좌표까지 건드리면 바깥이 어긋난다
      · 폭이나 좌표를 못 읽은 표 — **모르면 손대지 않는다**
      · `<hp:cellSz>`가 없는 셀이 있는 표 — 일부만 바꾸면 행 폭이 표 폭과 어긋난다
    """

    def changer(text: str) -> tuple[str, dict]:
        stats = {
            "맞춘 표": 0,
            "건너뛴 표(병합)": 0,
            "건너뛴 표(표 안에 표)": 0,
            "건너뛴 표(잴 수 없음)": 0,
        }
        out: list[str] = []
        last = 0

        for start, end, nested in _blocks(text, "tbl"):
            out.append(text[last:start])
            last = end
            tbl = text[start:end]

            if nested:
                stats["건너뛴 표(표 안에 표)"] += 1
                out.append(tbl)
                continue

            head = tbl[: tbl.index(">") + 1]
            col_cnt_s = _attrs(head).get("colCnt", "")
            if not col_cnt_s.isdigit() or int(col_cnt_s) < 1:
                stats["건너뛴 표(잴 수 없음)"] += 1
                out.append(tbl)
                continue
            col_cnt = int(col_cnt_s)

            # ★ 표 폭 — 속성 순서에 매이지 않는다(`widthRelTo`가 먼저 올 수 있다)
            sz = _find_tag(tbl, "sz")
            width_s = _attrs(sz.group(0)).get("width", "") if sz else ""
            total = int(width_s) if width_s.isdigit() else BODY_WIDTH

            cells = _blocks(tbl, "tc")
            widest = [0.0] * col_cnt
            skip = None
            for cs, ce, _ in cells:
                cell = tbl[cs:ce]
                span = _find_tag(cell, "cellSpan")
                if span is not None:
                    sa = _attrs(span.group(0))
                    if sa.get("colSpan", "1") != "1" or sa.get("rowSpan", "1") != "1":
                        skip = "건너뛴 표(병합)"
                        break
                if _find_tag(cell, "cellSz") is None:
                    # ★ 일부 셀만 바꾸면 행 폭이 표 폭과 어긋난다(교차검증 Codex 지적)
                    skip = "건너뛴 표(잴 수 없음)"
                    break
                addr = _find_tag(cell, "cellAddr")
                if addr is None:
                    skip = "건너뛴 표(잴 수 없음)"
                    break
                col_s = _attrs(addr.group(0)).get("colAddr", "")
                if not col_s.isdigit() or int(col_s) >= col_cnt:
                    skip = "건너뛴 표(잴 수 없음)"
                    break
                body = "".join(re.findall(r"<hp:t>(.*?)</hp:t>", cell, re.S))
                widest[int(col_s)] = max(widest[int(col_s)], text_width(body))

            if skip is not None or sum(widest) <= 0:
                stats[skip or "건너뛴 표(잴 수 없음)"] += 1
                out.append(tbl)
                continue

            floor = min(MIN_COL_WIDTH, total // col_cnt)
            spare = total - floor * col_cnt
            ratio_sum = sum(widest)
            widths = [floor + int(spare * (w / ratio_sum)) for w in widest]
            widths[-1] += total - sum(widths)  # 반올림 오차를 마지막 열에 몰아 준다

            # 셀을 뒤에서부터 바꾼다 — 앞을 먼저 바꾸면 뒤 좌표가 밀린다
            new_tbl = tbl
            for cs, ce, _ in reversed(cells):
                cell = new_tbl[cs:ce]
                addr = _find_tag(cell, "cellAddr")
                if addr is None:
                    continue
                col = int(_attrs(addr.group(0))["colAddr"])
                szm = _find_tag(cell, "cellSz")
                if szm is None:
                    continue
                height = _attrs(szm.group(0)).get("height", "0")
                cell = (
                    cell[: szm.start()]
                    + '<hp:cellSz width="%d" height="%s"/>' % (widths[col], height)
                    + cell[szm.end() :]
                )
                # ★ 너비가 바뀌면 줄배치 캐시가 낡는다 — 그 자리만 지운다
                cell = _LINESEG_RE.sub("", cell)
                new_tbl = new_tbl[:cs] + cell + new_tbl[ce:]

            stats["맞춘 표"] += 1
            out.append(new_tbl)

        out.append(text[last:])
        return "".join(out), stats

    return _rewrite(path, changer)


# ── 3. 글꼴 바꾸기 ────────────────────────────────────────────────────────
def _xml_escape(s: str) -> str:
    """★ 교차검증 Codex 지적 — 이스케이프 없이 넣으면 `&`·`<`가 header를 깨뜨린다."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def set_font(path: Path, face: str = DEFAULT_FACE) -> dict:
    """문서의 모든 글꼴 이름을 하나로 바꾼다.

    ★ `hh:font/@face`만 바꾼다. 글자 모양(charPr)은 글꼴을 **번호로** 가리키므로
      이름만 갈아 끼우면 크기·굵기·자간이 그대로 유지된다.
    ★ 이 파트는 header.xml에 있어 섹션만 고치는 기본 경로로는 닿지 않는다.
    """
    safe = _xml_escape(face)
    changed_names: set[str] = set()

    def changer(text: str) -> tuple[str, dict]:
        counts = {"바꾼 글꼴": 0, "이미 그 글꼴": 0}

        def sub(mo: re.Match) -> str:
            old = mo.group(2)
            if old == safe:
                counts["이미 그 글꼴"] += 1
                return mo.group(0)
            counts["바꾼 글꼴"] += 1
            changed_names.add(old)
            return mo.group(1) + safe + mo.group(3)

        return _FONT_RE.sub(sub, text), counts

    stats = _rewrite(path, changer, entries=("Contents/header.xml",))
    stats["바뀐 이름"] = sorted(changed_names)
    return stats


# ── 4. 지금 상태 보기 ─────────────────────────────────────────────────────
def check(path: Path) -> dict:
    cell: Counter = Counter()
    inner: Counter = Counter()
    no_margin_cells = 0
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not (name.startswith("Contents/section") and name.endswith(".xml")):
                continue
            body = z.read(name).decode("utf-8")
            for mo in CELL_MARGIN_RE.finditer(body):
                cell[_margin_values(mo.group(0))] += 1
            for mo in IN_MARGIN_RE.finditer(body):
                inner[_margin_values(mo.group(0))] += 1
            no_margin_cells += len(re.findall(r'<hp:tc\b[^>]*hasMargin="0"', body))
        faces = _FONT_RE.findall(z.read("Contents/header.xml").decode("utf-8"))
    want = tuple(str(HANCOM_CELL_MARGIN[k]) for k in ("left", "right", "top", "bottom"))
    return {
        "셀 여백 분포": dict(cell),
        "한글 기본값": want,
        "기본값인 셀": cell.get(want, 0),
        "기본값 아닌 셀": sum(v for k, v in cell.items() if k != want),
        # ★★★★ **화면이 실제로 쓰는 값** — `hasMargin="0"`인 셀은 셀 값이 아니라 이것을 본다
        "표 안쪽여백 분포": dict(inner),
        "기본값 아닌 표 안쪽여백": sum(v for k, v in inner.items() if k != want),
        "셀 여백을 안 쓰는 셀(hasMargin=0)": no_margin_cells,
        "쓰는 글꼴": sorted({f[1] for f in faces}),
    }


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) < 2:
        print(__doc__)
        return 2
    what, target = argv[0], Path(argv[1])
    if not target.exists():
        print("파일이 없습니다: %s" % target)
        return 2

    if what == "check":
        for key, val in check(target).items():
            print("  %s: %s" % (key, val))
        return 0
    if what == "both":
        what = "all"  # 옛 이름을 그대로 받아 준다
    if what not in ("fix", "fit", "font", "all"):
        print("모르는 명령입니다: %s" % what)
        return 2

    face = DEFAULT_FACE
    if "--face" in argv:
        i = argv.index("--face")
        if i + 1 >= len(argv):
            print("--face 뒤에 글꼴 이름을 적어 주십시오.")
            return 2
        face = argv[i + 1]

    touched = 0
    try:
        if what in ("fix", "all"):
            got = fix_margins(target)
            print("여백:", got)
            touched += got.get("바꾼 셀 여백", 0) + got.get("바꾼 표 안쪽여백", 0)
        if what in ("fit", "all"):
            got = fit_column_widths(target)
            print("열 너비:", got)
            touched += got.get("맞춘 표", 0)
        if what in ("font", "all"):
            got = set_font(target, face)
            print("글꼴:", got)
            touched += got.get("바꾼 글꼴", 0)
    except RuntimeError as e:
        print("멈췄습니다 —", e)
        return 2

    if touched == 0:
        # ★★★ 교차검증 지적 — 정규식이 죽어도 «0건»은 초록으로 보인다. 그 길을 막는다
        print("")
        print("[!] 손댈 것을 하나도 못 찾았습니다.")
        print("  이미 다 맞춰져 있거나, **찾는 눈이 죽었을 수** 있습니다.")
        print("  `check`로 지금 상태를 보고 판단하십시오.")
        return 1

    print("")
    print("* 표를 손댔으니 마지막에 한컴으로 다시 저장하십시오:")
    print("   finalize_hwpx.py <파일> --hancom-resave")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
