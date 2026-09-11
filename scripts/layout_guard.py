# -*- coding: utf-8 -*-
"""layout_guard — 내보내기 직전 「종이에 제대로 찍히는가」를 기계가 확인한다.

★ 왜 있나
  `validate.py` 는 XML 문법만 보고, `fill_hwpx.py check` 는 파일이 열리는지만 본다.
  **둘 다 통과한 문서가 종이에서는 글이 잘리고 글자가 겹친다.**
  2026-09-11 타투다 외주용역 결과보고서에서 넷이 한꺼번에 났다:

    1. 표 칸 높이가 본문 높이를 넘어 「2. 과업 수행 결과」 12항목 중 뒤 절반이
       **경고 없이 안 찍혔다** (칸 82,200 > 본문 72,852)
    2. 양식 문단의 줄간격이 90% 라 두 줄로 접힌 글이 서로 **겹쳐** 읽을 수 없었다
    3. 표를 다시 조립하며 표 머리(<hp:sz>·여백)를 버려 표가 제멋대로 그려졌다
    4. 표 크기를 바꾼다는 코드가 **셀 안 첫 그림의 크기**를 덮어써 사진이 잘렸다

  넷 다 **PDF 로 찍어 눈으로 보고서야** 드러났다. 그 「찍어 보기」가 사람 손에
  맡겨져 있는 한 바쁠 때 빠진다 — 그래서 기계가 한다.

  ※ 1번은 이 사고 전에도 메모리에 적혀 있었다(「표 칸은 한 쪽을 못 넘는다」).
    **적어 두는 방식으로는 안 막힌다는 증거**라 검사로 올렸다.

★ 무엇을 보나
  --xml   (빠름·한컴 불필요) XML 함정 넷
  --paper (한컴 필요·문서당 20초쯤) 한글로 PDF 를 찍어
          **hwpx 안의 글이 종이에 다 있는지** 대조한다.
          기대값을 사람이 적을 필요가 없다 — 문서 자신이 기대값이다.
          ★ 이쪽이 더 값어치 있다: 내가 **아직 모르는 함정**까지 잡는다.

  되돌아오는 값: 0 통과 / 1 문제 발견 / 2 검사 자체가 깨짐
  (2 를 1 과 가른 이유 — 검사가 죽은 것을 「문제 없음」으로 읽지 않게)

사용:
    python layout_guard.py 문서.hwpx              # xml + paper 둘 다
    python layout_guard.py 문서.hwpx --xml        # XML 검사만 (빠름)
    python layout_guard.py 문서.hwpx --json
"""
import argparse
import json
import os
import re
import sys
import tempfile
import zipfile

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

# ─── XML 훑기 (문자열 기준, DOM 재직렬화 없음) ───────────────────────

def _spans(text, open_pat, close_tag):
    """중첩을 고려해 [(start, end, depth)] 를 낸다."""
    events = [(m.start(), 1) for m in re.finditer(open_pat, text)]
    events += [(m.start(), -1) for m in re.finditer(re.escape(close_tag), text)]
    events.sort()
    stack, out = [], []
    for pos, kind in events:
        if kind == 1:
            stack.append(pos)
        elif stack:
            st = stack.pop()
            out.append((st, pos + len(close_tag), len(stack)))
    out.sort()
    return out


def table_spans(xml):
    return _spans(xml, r"<hp:tbl\b", "</hp:tbl>")


def row_spans(tbl):
    return [s for s in _spans(tbl, r"<hp:tr\b", "</hp:tr>") if s[2] == 0]


def cell_spans(tr):
    return [(a, b) for a, b, d in _spans(tr, r"<hp:tc\b", "</hp:tc>") if d == 0]


def para_spans(xml):
    return _spans(xml, r"<hp:p\b", "</hp:p>")


def attr(tag_xml, name):
    end = tag_xml.find(">")
    m = re.search(r'\b' + re.escape(name) + r'="([^"]*)"', tag_xml[:end if end > 0 else len(tag_xml)])
    return m.group(1) if m else None


def para_text(p_xml):
    """그 문단의 직속 글자만. 표를 품은 문단이 표 안 글자를 끌어오지 않게 한다."""
    body = p_xml
    for a, b, d in sorted(table_spans(p_xml), key=lambda s: -s[0]):
        if d == 0:
            body = body[:a] + body[b:]
    out = []
    for m in re.finditer(r"<hp:t\b[^>]*>(.*?)</hp:t>", body, re.S):
        seg = re.sub(r"<[^>]+>", "", m.group(1))
        out.append(seg)
    return unescape("".join(out))


def unescape(s):
    return (s.replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&"))


# ─── 쪽 설정 ────────────────────────────────────────────────────────

def page_body_height(sec_xml):
    """본문(머리말·꼬리말·여백을 뺀) 높이. 못 읽으면 None."""
    m = re.search(r"<hp:pagePr\b[^>]*>", sec_xml)
    if not m:
        return None
    h = attr(m.group(0), "height")
    mm = re.search(r"<hp:margin\b[^>]*/?>", sec_xml[m.start():m.start() + 800])
    if not (h and mm):
        return None
    g = mm.group(0)
    vals = [attr(g, k) for k in ("top", "bottom", "header", "footer")]
    if any(v is None for v in vals):
        return None
    return int(h) - sum(int(v) for v in vals)


def page_body_width(sec_xml):
    m = re.search(r"<hp:pagePr\b[^>]*>", sec_xml)
    if not m:
        return None
    w = attr(m.group(0), "width")
    mm = re.search(r"<hp:margin\b[^>]*/?>", sec_xml[m.start():m.start() + 800])
    if not (w and mm):
        return None
    g = mm.group(0)
    l, r = attr(g, "left"), attr(g, "right")
    if None in (l, r):
        return None
    return int(w) - int(l) - int(r)


# ─── 문단 줄간격 (header.xml) ───────────────────────────────────────

def line_spacings(header_xml):
    """paraPr 번호 -> (종류, 값). 값이 PERCENT 면 백분율."""
    out = {}
    for m in re.finditer(r'<hh:paraPr id="(\d+)".*?</hh:paraPr>', header_xml, re.S):
        pid, body = m.group(1), m.group(0)
        ls = re.search(r'<hh:lineSpacing type="([A-Z]+)" value="(-?\d+)"', body)
        if ls:
            out[pid] = (ls.group(1), int(ls.group(2)))
    return out


def char_heights(header_xml):
    out = {}
    for m in re.finditer(r'<hh:charPr id="(\d+)"[^>]*\bheight="(\d+)"', header_xml):
        out[m.group(1)] = int(m.group(2))
    return out


# ─── XML 함정 검사 ──────────────────────────────────────────────────

# 줄간격이 100% 면 글자 높이만큼 띄우므로 빽빽해도 겹치지는 않는다.
# 실측(2026-09-11): 겹쳐서 못 읽은 것은 **90%** 였고, 100% 는 멀쩡했다.
MIN_SAFE_SPACING = 100

# 한컴이 다시 저장하면 그림 크기를 잔단위로 반올림한다(실측: 90,450 → 90,480).
# 그 차이를 결함으로 읽으면 정상 문서가 매번 걸린다.
IMG_CLIP_TOLERANCE = 0.01


def check_xml(path):
    findings = []
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist()
                 if n.startswith("Contents/section") and n.endswith(".xml")]
        header = z.read("Contents/header.xml").decode("utf-8")
        spacings = line_spacings(header)
        charh = char_heights(header)
        for name in sorted(names):
            sec = z.read(name).decode("utf-8")
            body_h = page_body_height(sec)
            body_w = page_body_width(sec)
            findings += _check_section(sec, name, body_h, body_w, spacings, charh)
    return findings


def _check_section(sec, name, body_h, body_w, spacings, charh):
    out = []
    tops = [s for s in table_spans(sec) if s[2] == 0]

    # (1) 표 칸이 한 쪽을 넘는가 — 한글은 넘친 글을 말없이 안 그린다
    if body_h:
        for a, b, _ in table_spans(sec):
            tbl = sec[a:b]
            for ra, rb, _ in row_spans(tbl):
                for ca, cb in cell_spans(tbl[ra:rb]):
                    tc = tbl[ra:rb][ca:cb]
                    m = re.search(r"<hp:cellSz\b[^>]*>", tc)
                    if not m:
                        continue
                    h = attr(m.group(0), "height")
                    if h and int(h) > body_h:
                        out.append({
                            "rule": "cell_taller_than_page",
                            "severity": "error",
                            "where": name,
                            "detail": "표 칸 높이 %s > 본문 높이 %d. 한글이 넘친 글을 "
                                      "경고 없이 안 그린다 — 내용을 나눠 표를 이어 붙일 것"
                                      % (h, body_h),
                            "sample": para_first_text(tc),
                        })

    # (2) 표 바로 뒤에 <hp:sz> 가 있는가 — 없으면 표 머리를 잃은 것
    for a, b, _ in table_spans(sec):
        tbl = sec[a:b]
        head = tbl.find(">") + 1
        if not re.match(r"<hp:sz\b", tbl[head:head + 12]):
            out.append({
                "rule": "table_head_lost",
                "severity": "error",
                "where": name,
                "detail": "표 바로 뒤가 <hp:sz> 가 아니다 — 표 머리(크기·위치·여백)를 "
                          "잃었다. 표를 다시 조립할 때 첫 <hp:tr> 앞을 통째로 남길 것",
                "sample": tbl[head:head + 60],
            })

    # (3) 셀 안 그림이 그 셀보다 넓은가 — 잘린다
    for a, b, _ in table_spans(sec):
        tbl = sec[a:b]
        for ra, rb, _ in row_spans(tbl):
            tr = tbl[ra:rb]
            for ca, cb in cell_spans(tr):
                tc = tr[ca:cb]
                m = re.search(r"<hp:cellSz\b[^>]*>", tc)
                if not m:
                    continue
                cw = attr(m.group(0), "width")
                if not cw:
                    continue
                cw = int(cw)
                for pm in re.finditer(r"<hp:pic\b.*?</hp:pic>", tc, re.S):
                    pic = pm.group(0)
                    szm = re.search(r"<hp:sz\b[^>]*>", pic)
                    if not szm:
                        continue
                    pw = attr(szm.group(0), "width")
                    if pw and int(pw) > cw:
                        out.append({
                            "rule": "picture_wider_than_cell",
                            "severity": "error",
                            "where": name,
                            "detail": "그림 폭 %s > 칸 폭 %d — 오른쪽이 잘린다. "
                                      "표 크기를 바꾸는 코드가 그림의 <hp:sz> 를 "
                                      "덮어썼을 수 있다" % (pw, cw),
                        })
                    # 원본 좌표계 확인: imgClip 이 orgSz 와 다르면 일부만 그린다
                    org = re.search(r"<hp:orgSz\b[^>]*>", pic)
                    clip = re.search(r"<hp:imgClip\b[^>]*>", pic)
                    if org and clip:
                        ow, oh = attr(org.group(0), "width"), attr(org.group(0), "height")
                        cr, cbm = attr(clip.group(0), "right"), attr(clip.group(0), "bottom")
                        if None not in (ow, oh, cr, cbm) and _far(ow, cr, oh, cbm):
                            out.append({
                                "rule": "imgclip_not_orgsz",
                                "severity": "error",
                                "where": name,
                                "detail": "imgClip(%s×%s) 이 orgSz(%s×%s) 와 다르다 — "
                                          "원본의 일부만 그려진다. imgRect·imgClip·imgDim 은 "
                                          "표시 크기가 아니라 **원본 좌표계**다"
                                          % (cr, cbm, ow, oh),
                            })

    # (4) 줄간격이 좁은 문단에 두 줄 넘는 글이 들어갔는가 — 글자가 겹친다
    if body_w:
        for a, b, d in para_spans(sec):
            p = sec[a:b]
            ppr = attr(p[:p.find(">") + 1], "paraPrIDRef")
            if ppr is None or ppr not in spacings:
                continue
            kind, val = spacings[ppr]
            if kind != "PERCENT" or val >= MIN_SAFE_SPACING:
                continue
            text = para_text(p)
            if not text.strip():
                continue
            cm = re.search(r"<hp:run\b[^>]*\bcharPrIDRef=\"(\d+)\"", p)
            size = charh.get(cm.group(1), 1000) if cm else 1000
            avail = cell_width_for(sec, a) or body_w
            em = sum(0.5 if ord(c) < 0x1100 else 1.0 for c in text)
            if em * size > (avail - 1020):
                out.append({
                    "rule": "tight_spacing_wraps",
                    "severity": "error",
                    "where": name,
                    "detail": "줄간격 %d%% 인 문단(paraPr %s)에 두 줄 넘는 글이 들어갔다 "
                              "— 접히면서 글자가 겹친다. 그 문단 서식을 복제해 "
                              "줄간격만 올린 서식을 쓸 것(번호는 마지막+1)" % (val, ppr),
                    "sample": text[:60],
                })
    return out


def _far(ow, cr, oh, cbm):
    """반올림 오차를 빼고, imgClip 이 원본과 정말 다른지 본다."""
    ow, cr, oh, cbm = int(ow), int(cr), int(oh), int(cbm)
    if ow <= 0 or oh <= 0:
        return True
    return (abs(ow - cr) / ow > IMG_CLIP_TOLERANCE
            or abs(oh - cbm) / oh > IMG_CLIP_TOLERANCE)


def cell_width_for(sec, para_pos):
    """그 문단을 품은 가장 안쪽 셀의 폭. 셀 밖이면 None."""
    best = None
    for a, b, _ in table_spans(sec):
        if not (a < para_pos < b):
            continue
        tbl = sec[a:b]
        for ra, rb, _ in row_spans(tbl):
            tr = tbl[ra:rb]
            for ca, cb in cell_spans(tr):
                lo, hi = a + ra + ca, a + ra + cb
                if lo < para_pos < hi:
                    m = re.search(r"<hp:cellSz\b[^>]*>", tr[ca:cb])
                    if m:
                        w = attr(m.group(0), "width")
                        if w:
                            best = int(w)
    return best


def para_first_text(xml):
    sp = para_spans(xml)
    for a, b, _ in sp:
        t = para_text(xml[a:b]).strip()
        if t:
            return t[:50]
    return ""


# ─── 종이 대조 (한글로 PDF 를 찍어 글자를 맞춰 본다) ────────────────

def doc_paragraphs(path):
    """문서 안의 글을 문단 단위로. 표 안 글자도 포함, 중복 없이."""
    out = []
    with zipfile.ZipFile(path) as z:
        for name in sorted(n for n in z.namelist()
                           if n.startswith("Contents/section") and n.endswith(".xml")):
            sec = z.read(name).decode("utf-8")
            for a, b, _ in para_spans(sec):
                t = para_text(sec[a:b]).strip()
                if t:
                    out.append(t)
    return out


def to_pdf(src, dst, timeout_note=""):
    try:
        import win32com.client  # type: ignore
    except ImportError:
        return False, "pywin32 가 없어 종이 대조를 못 한다"
    hwp = None
    try:
        hwp = win32com.client.Dispatch("HWPFrame.HwpObject")
        try:
            hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        except Exception:
            pass
        try:
            hwp.XHwpWindows.Item(0).Visible = False
        except Exception:
            pass
        if not bool(hwp.Open(os.path.abspath(src), "", "")):
            return False, "한글이 파일을 열지 못했다"
        ok = bool(hwp.SaveAs(os.path.abspath(dst), "PDF", ""))
        return ok, "" if ok else "PDF 저장 실패"
    except Exception as exc:
        return False, "한글 COM 실패: %s" % exc
    finally:
        if hwp is not None:
            try:
                hwp.Quit()
            except Exception:
                pass


def pdf_text(path):
    try:
        import pymupdf  # type: ignore
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore
        except ImportError:
            return None, None
    d = pymupdf.open(path)
    return "".join(p.get_text() or "" for p in d), len(d)


def squeeze(s):
    return re.sub(r"\s+", "", s)


def check_paper(path):
    """hwpx 안의 글이 종이에 다 찍히는지 본다. 기대값은 문서 자신이다."""
    findings = []
    paras = doc_paragraphs(path)
    tmpdir = tempfile.mkdtemp(prefix="layout_guard_")
    pdf = os.path.join(tmpdir, "check.pdf")
    ok, why = to_pdf(path, pdf)
    if not ok:
        return [{"rule": "paper_check_unavailable", "severity": "skipped",
                 "where": path, "detail": why}], None
    text, pages = pdf_text(pdf)
    if text is None:
        return [{"rule": "paper_check_unavailable", "severity": "skipped",
                 "where": path,
                 "detail": "pymupdf 가 없어 PDF 글자를 못 읽는다"}], None
    flat = squeeze(text)
    for t in paras:
        key = squeeze(t)
        if len(key) < 4:
            continue                     # 한두 글자는 우연히 겹쳐 뜻이 없다
        if key not in flat:
            findings.append({
                "rule": "text_missing_on_paper",
                "severity": "error",
                "where": path,
                "detail": "문서에 있는 글이 종이에는 없다 — 표 칸이 한 쪽을 넘어 "
                          "잘렸거나 개체에 가려졌을 수 있다",
                "sample": t[:70],
            })
    return findings, {"pages": pages, "paragraphs": len(paras), "pdf": pdf}


# ─── 실행 ───────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="내보내기 직전 레이아웃 관문 (잘림·겹침·표 머리·그림 넘침)")
    ap.add_argument("input")
    ap.add_argument("--xml", action="store_true", help="XML 함정 검사만 (빠름)")
    ap.add_argument("--paper", action="store_true", help="종이 대조만 (한컴 필요)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print("파일이 없다: %s" % args.input, file=sys.stderr)
        return 2

    do_xml = args.xml or not args.paper
    do_paper = args.paper or not args.xml

    findings, info = [], None
    try:
        if do_xml:
            findings += check_xml(args.input)
        if do_paper:
            f2, info = check_paper(args.input)
            findings += f2
    except Exception as exc:            # 검사가 깨진 것을 「문제 없음」으로 읽지 않게
        import traceback
        traceback.print_exc()
        print("검사 자체가 깨졌다: %s" % exc, file=sys.stderr)
        return 2

    errors = [f for f in findings if f["severity"] == "error"]
    skipped = [f for f in findings if f["severity"] == "skipped"]

    if args.json:
        print(json.dumps({"ok": not errors, "findings": findings, "info": info},
                         ensure_ascii=False, indent=2))
    else:
        if info:
            print("종이 %d쪽 · 문단 %d개 대조" % (info["pages"], info["paragraphs"]))
        for f in skipped:
            print("[건너뜀] %s — %s" % (f["rule"], f["detail"]))
        if not errors:
            print("LAYOUT GUARD: PASS")
        else:
            print("LAYOUT GUARD: FAIL (%d건)" % len(errors))
            seen = set()
            for f in errors:
                k = (f["rule"], f.get("sample", ""))
                if k in seen:
                    continue
                seen.add(k)
                print("  - [%s] %s" % (f["rule"], f["detail"]))
                if f.get("sample"):
                    print("      해당: %s" % f["sample"])
    # 건너뛴 것이 있으면 그 사실을 종료값으로도 알린다 (조용한 통과 방지)
    if errors:
        return 1
    if skipped and do_paper:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
