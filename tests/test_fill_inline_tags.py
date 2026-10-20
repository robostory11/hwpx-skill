#!/usr/bin/env python3
"""fill_hwpx 가 글자를 고칠 때 <hp:t> 안의 탭·형광펜 같은 인라인 요소를 지우지 않는지 본다.

경위(2026-10-20): 충남대 RISE 동의서에서 `replace` 로 「□동의함.」→「■동의함.」,
「성    명 : 」→「성    명 : 이호섭」 을 바꾸자 같은 <hp:t> 안의 <hp:tab/> 이 전부 사라져
「■동의함.□동의하지 않음.」 · 「이호섭(인 또는 서명)」 처럼 붙어 버렸다. 검사(check --strict ·
validate)는 모두 통과했고 PDF 로 찍어 보고서야 보였다.

사용법: python tests/test_fill_inline_tags.py   (종료 코드 0 = 전체 통과)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fill_hwpx as F  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


TAB1 = '<hp:tab width="2668" leader="0" type="1"/>'
TAB2 = '<hp:tab width="4000" leader="0" type="1"/>'


def sec(*paras):
    body = "".join(
        f'<hp:p id="{i}"><hp:run charPrIDRef="13"><hp:t>{t}</hp:t></hp:run></hp:p>'
        for i, t in enumerate(paras))
    return f'<hs:sec xmlns:hs="urn:s" xmlns:hp="urn:p">{body}</hs:sec>'


def replace(xml, mapping):
    counts, warnings = {}, []
    try:
        out = F.replace_in_section(xml, mapping, counts, warnings=warnings)
    except TypeError:  # 경고 통로가 없는 옛 판 — 글자 검사는 그대로 돌게 한다
        out = F.replace_in_section(xml, mapping, counts)
        warnings = None
    return out, counts, warnings


print("[1] 맞춘 글자 바로 뒤에 덧붙이면 — 탭은 덧붙인 글자 뒤로 밀린다")
out, counts, _ = replace(sec(f"성    명 : {TAB1}{TAB2}(인 또는 서명)"),
                         {"성    명 : ": "성    명 : 이호섭"})
check("교체 1회", counts.get("성    명 : ") == 1, counts)
check("탭 둘이 이름 뒤에 그대로", out and f"성    명 : 이호섭{TAB1}{TAB2}(인 또는 서명)" in out, out)

print("[2] 한 글자 바꾸기 — 뒤의 탭 자리는 그대로")
out, _, _ = replace(sec(f"□동의함.{TAB1}{TAB2}□동의하지 않음."), {"□동의함.": "■동의함."})
check("■동의함. 뒤에 탭 둘", out and f"■동의함.{TAB1}{TAB2}□동의하지 않음." in out, out)

print("[3] 탭을 사이에 두고 걸친 문구 — 바뀐 글자만 고치고 탭은 제자리")
out, counts, warnings = replace(sec(f"□동의함.{TAB1}□동의하지 않음."),
                                {"□동의함.□동의하지 않음.": "■동의함.□동의하지 않음."})
check("교체 1회", counts.get("□동의함.□동의하지 않음.") == 1, counts)
check("탭이 두 문구 사이에", out and f"■동의함.{TAB1}□동의하지 않음." in out, out)
check("경고 없음", warnings == [], warnings)

print("[4] 엔티티가 섞여도 자리가 맞는다")
out, _, _ = replace(sec(f"A &amp; B{TAB1}C"), {"B": "D"})
check("A &amp; D<tab>C", out and f"A &amp; D{TAB1}C" in out, out)

print("[5] 고친 글자 한가운데의 탭은 버리지 않고 뒤로 옮기며 알린다")
out, _, warnings = replace(sec(f"AB{TAB1}CD"), {"BC": "XY"})
check("탭이 남는다", out and out.count("<hp:tab ") == 1, out)
check("AXY<tab>D", out and f"AXY{TAB1}D" in out, out)
check("경고 1건", len(warnings) == 1, warnings)

print("[6] 형광펜 짝(시작·끝)도 남는다")
MB, ME = '<hp:markpenBegin color="#FFFF00"/>', "<hp:markpenEnd/>"
out, _, _ = replace(sec(f"기간 {MB}30일{ME} 이내"), {"30일": "90일"})
check("형광펜 안의 글자만 바뀜", out and f"기간 {MB}90일{ME} 이내" in out, out)

def fill_run(text, value):
    xml = sec(text)
    root = F.scan_xml(xml)
    reg = F.Registry(xml)
    run = next(iter(F.descendants(root, "run")))
    F.set_run_text(run, value, reg)
    return F.apply_splices(xml, F.build_splices(xml, reg))


print("[7] 셀 값 채우기는 「새 내용으로 갈기」 — 원래 글자와 그 안의 탭을 함께 버린다")
out = fill_run(f"{TAB1}년{TAB1}월{TAB1}일", "2026년 10월 20일")
check("탭이 남지 않는다", out.count("<hp:tab ") == 0, out)
check("값만 들어간다", "<hp:t>2026년 10월 20일</hp:t>" in out, out)

print("[8] 문단 복제(add-para)도 「새 내용」 — 기준 문단의 탭이 끝에 붙어 남지 않는다")
frag = f'<hp:p id="7"><hp:run charPrIDRef="13"><hp:t>1.{TAB1}사업 개요</hp:t></hp:run></hp:p>'
out = F._clone_para(frag, "2. 추진 일정", [99])
check("2. 추진 일정 · 탭 없음", "<hp:t>2. 추진 일정</hp:t>" in out and "<hp:tab " not in out, out)

print("[9] 경고는 그 호출 것만 — 결과 JSON 에 실리고 다음 호출에서 비워진다")
del F.INLINE_WARNINGS[:]
replace(sec(f"AB{TAB1}CD"), {"BC": "XY"})
rep = F._with_inline_warnings({"ok": True})
check("inline_warnings 가 실린다", len(rep.get("inline_warnings", [])) == 1, rep)
del F.INLINE_WARNINGS[:]
check("비우면 안 실린다", "inline_warnings" not in F._with_inline_warnings({"ok": True}))

def para(*ts):
    runs = "".join(f'<hp:run charPrIDRef="13"><hp:t>{t}</hp:t></hp:run>' for t in ts)
    return f'<hs:sec xmlns:hs="urn:s" xmlns:hp="urn:p"><hp:p id="0">{runs}</hp:p></hs:sec>'


print("[10] 탭만 든 <hp:t> 를 비울 때도 탭이 지워진다(글자가 같아도 다시 쓴다)")
frag = (f'<hp:p id="7"><hp:run charPrIDRef="13"><hp:t>1.</hp:t></hp:run>'
        f'<hp:run charPrIDRef="20"><hp:t>{TAB1}</hp:t></hp:run>'
        f'<hp:run charPrIDRef="13"><hp:t>사업 개요</hp:t></hp:run></hp:p>')
out = F._clone_para(frag, "2. 추진 일정", [99])
check("복제 문단에 탭이 남지 않는다", "<hp:tab " not in out, out)
out = fill_run(f"A{TAB1}", "A")
check("같은 글자로 채워도 탭이 지워진다", "<hp:tab " not in out and "<hp:t>A</hp:t>" in out, out)

print("[11] run 경계를 넘는 교체 — 바뀐 글자만 고치고 탭은 제자리")
out, counts, warnings = replace(para(f"A{TAB1}", "B"), {"AB": "XB"})
check("교체 1회", counts.get("AB") == 1, counts)
check("X<tab> · B 그대로", out and f"<hp:t>X{TAB1}</hp:t>" in out and "<hp:t>B</hp:t>" in out, out)
check("경고 없음", warnings == [], warnings)

print("[12] run 경계의 탭이 바뀐 구간 안이면 남기고 알린다")
out, _, warnings = replace(para(f"A{TAB1}", "BC"), {"AB": "XY"})
check("탭이 남는다", out and out.count("<hp:tab ") == 1, out)
check("경고 1건", warnings is not None and len(warnings) == 1, warnings)

print("[13] run 경계를 넘는 문구 끝에 덧붙이면 — 덧붙인 글자는 탭 앞")
out, _, _ = replace(para("성", f"명:{TAB1}(서명)"), {"성명:": "성명:홍"})
check("명:홍<tab>(서명)", out and f"<hp:t>명:홍{TAB1}(서명)</hp:t>" in out, out)

print("[14] 진입점 넷이 부를 때마다 지난 경고를 비운다")
for fn, args in ((F.fill_hwpx, ("없는파일.hwpx", "x.hwpx", {"a": "b"})),
                 (F.replace_hwpx, ("없는파일.hwpx", "x.hwpx", {"a": "b"})),
                 (F.add_rows_hwpx, ("없는파일.hwpx", "x.hwpx", 0, [["a"]])),
                 (F.add_paras_hwpx, ("없는파일.hwpx", "x.hwpx", [{"after": "a", "text": "b"}]))):
    F.INLINE_WARNINGS.append("지난 호출의 경고")
    try:
        fn(*args)
    except OSError:
        pass
    check(f"{fn.__name__} 가 비운다", F.INLINE_WARNINGS == [], F.INLINE_WARNINGS)

print("[15] run 경계를 넘어 바뀐 구간 안의 탭은 새 글자 뒤로 옮기며 알린다(조용히 남기지 않는다)")
out, _, warnings = replace(para(f"A{TAB1}B", "C"), {"ABC": "XB"})
check("XB<tab> · 빈 노드", out and f"<hp:t>XB{TAB1}</hp:t>" in out, out)
check("경고 1건", warnings is not None and len(warnings) == 1, warnings)

print("[16] 요소만 든 run 을 가로지른 교체도 알린다")
out, _, warnings = replace(para("A", TAB1, "B"), {"AB": "XY"})
check("탭이 남는다", out and out.count("<hp:tab ") == 1, out)
check("경고 1건", warnings is not None and len(warnings) == 1, warnings)
out, _, warnings = replace(para("1.", TAB1, "사업 개요"), {"1.사업 개요": "2.추진 일정"})
check("「1.|탭|사업 개요」 도 경고 1건", warnings is not None and len(warnings) == 1, warnings)

print("[17] 셀 패턴 채우기 — 여러 run 이어도 한 run 과 같은 자리에 넣는다")
def cell(*ts, values, paras=False):
    """셀 패턴 채우기를 fill_section 과 같은 길(fill_in_cell_patterns → apply_pattern_edits)로 돌린다."""
    if paras:
        body = "".join(f'<hp:p id="{k}"><hp:run charPrIDRef="13"><hp:t>{t}</hp:t></hp:run></hp:p>'
                       for k, t in enumerate(ts))
        xml = f'<hs:sec xmlns:hs="urn:s" xmlns:hp="urn:p">{body}</hs:sec>'
    else:
        xml = para(*ts)
    root = F.scan_xml(xml)
    reg = F.Registry(xml)
    tns = [reg.get(t) for t in F.descendants(root, "t")]
    full = "".join(tn.text for tn in tns)
    result = F.fill_in_cell_patterns(full, F.normalize_values(values), set())
    assert result, full
    new_text, _matches, stages = result
    F.apply_pattern_edits(tns, stages)
    assert "".join(tn.text for tn in tns) == new_text
    return [tn.render() for tn in tns]
one = "".join(cell(f"item( {TAB1})", values={"item": "A"}))
two = "".join(cell("it", f"em( {TAB1})", values={"item": "A"}))
check("한 run 과 두 run 결과 글자 배치가 같다", one == two, (one, two))
check("item(A<tab>)", one == f"item(A{TAB1})", one)

print("[18] 같은 모양 탭 둘이 구간 안이면 경고도 둘")
out, _, warnings = replace(sec(f"A{TAB1}B{TAB1}C"), {"ABC": "XYZ"})
check("탭 둘이 남는다", out and out.count("<hp:tab ") == 2, out)
check("경고 2건", warnings is not None and len(warnings) == 2, warnings)

print("[19] 인라인 라벨의 빈 값이 문단 끝이면 — 끝 탭 뒤에 넣는다")
xml = sec(f"성명:{TAB1}")
root = F.scan_xml(xml)
reg = F.Registry(xml)
tns = [reg.get(t) for t in F.descendants(root, "t")]
F.replace_text_range(tns, 3, 3, "홍길동")
check("성명:<tab>홍길동", tns[0].render() == f"성명:{TAB1}홍길동", tns[0].render())

print("[20] 한 셀에 체크박스 여럿 — 일치마다 제자리에서 바뀐다")
one = "".join(cell(f"□AI{TAB1}□SW{TAB1}□HW", values={"AI": "☑", "SW": "☑"}))
check("☑AI<tab>☑SW<tab>□HW", one == f"☑AI{TAB1}☑SW{TAB1}□HW", one)
got = cell("□AI", "□SW", values={"AI": "☑", "SW": "☑"}, paras=True)
check("두 문단이 각자 ☑AI · ☑SW", got == ["☑AI", "☑SW"], got)

print("[21] 공백 든 값 — 값 하나가 run 여럿으로 갈리지 않고 빈칸 안 탭은 값 앞에 남는다")
got = cell("구분(", "  )", values={"구분": "2026. 10. 20"})
check("「구분(」 · 「2026. 10. 20)」", got == ["구분(", "2026. 10. 20)"], got)
got = cell(f"구분({TAB1}  )", values={"구분": "2026. 10. 20"})
check("구분(<tab>2026. 10. 20)", got == [f"구분({TAB1}2026. 10. 20)"], got)

print(f"\n결과: {PASS} 통과 / {FAIL} 실패")
sys.exit(1 if FAIL else 0)
