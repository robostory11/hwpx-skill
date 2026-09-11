# -*- coding: utf-8 -*-
"""content_guard — 문서 **안에서 서로 어긋나는 말**을 잡는다.

★ 왜 있나
  `layout_guard.py` 는 종이에 제대로 찍히는지만 본다. `validate.py` 는 XML 문법만 본다.
  **셋 다 통과한 문서가 같은 문서 안에서 서로 다른 말을 한다.**

  2026-09-11 타투다 외주용역 결과보고서 실측 — 표의 이행 상태 칸을 전부 「완료」로 바꾸고
  **본문 서술을 안 고쳤다.** 빌드도 검사도 전부 통과했고, 교차검증 검토자가 읽고서야 나왔다:

    · 표는 「완료」인데 같은 행에 "대기 중인 것은 단말 푸시 발송과 iOS 빌드 둘뿐이다"
    · 표는 「완료」인데 "인증기관과의 실연동은 미연결"
    · 다른 절에 "그대로 완료 7개 / 외부 연동만 대기 3개 / 협의 변경 2개" 가 통째로 남음
      → agy 평가: "평가위원이 즉시 허위 기재 또는 과업 미완료로 적발할 수 있는 가장 치명적 결함"
    · "이행 상태를 세 가지로 구분" 이라 써 놓고 정의 표에는 한 가지만
    · 목차를 재배치하고 본문의 "4-1 대조표" 참조를 안 고침 (4-1 은 다른 절이 됐다)

  네 가지 다 **기계가 볼 수 있는 어긋남**이다. 사람이 읽어야만 보이는 것이 아니었다.

★ 무엇을 보나 (전부 실제로 난 것)
  1. status_vs_prose   표 한 행의 상태 칸이 「완료」인데 같은 행에 「대기·미연결·않는다」 류
  2. count_mismatch    「N 가지로 구분」 이라 선언하고 바로 아래 표는 다른 수
  3. bad_section_ref   본문이 가리키는 절 번호가 실제 제목과 다르다
  4. label_value_split 같은 라벨에 붙은 값이 문서 안에서 서로 다르다 (금액·날짜)

  되돌아오는 값: 0 통과 / 1 문제 발견 / 2 검사 자체가 깨짐

사용:
    python content_guard.py 원고.md
    python content_guard.py 문서.hwpx
    python content_guard.py 원고.md --json
"""
import argparse
import json
import os
import re
import sys
import zipfile

HP = 'http://www.hancom.co.kr/hwpml/2011/paragraph'

# ─── 「아직 안 됐다」로 읽히는 말 ────────────────────────────────────
#   상태 칸이 「완료」인 행에 이런 말이 있으면 같은 줄이 서로 다른 말을 하는 것이다.
NOT_DONE = [
    '미연결', '미도입', '미구현', '미완료', '미제출', '미적용',
    '대기 중', '대기중', '연동 대기', '아직', '예정',
    '하지 않는다', '않았다', '두지 않았', '못 한다', '못한다',
    '협의 변경', '변경됨',
]

# 상태 칸에서 「됐다」로 읽는 말
DONE_WORDS = ['완료', '이행', '충족', '적합']

KO_NUM = {'한': 1, '두': 2, '세': 3, '네': 4, '다섯': 5, '여섯': 6,
          '일곱': 7, '여덟': 8, '아홉': 9, '열': 10}


# ─── 문서 읽기 ──────────────────────────────────────────────────────

def read_md(path):
    text = open(path, encoding='utf-8').read()
    return text.split('\n')


def read_hwpx(path):
    """hwpx 를 「표는 | 로 구분된 한 줄」 꼴로 펴서 md 와 같은 로직을 쓴다."""
    import xml.etree.ElementTree as ET
    P = '{%s}' % HP
    out = []

    def para_text(p):
        body = p
        return ''.join(''.join(t.itertext())
                       for r in body.findall(P + 'run')
                       for t in r.findall(P + 't'))

    def walk(el):
        for child in list(el):
            if child.tag == P + 'p':
                # 표를 품은 문단은 표를 먼저 펴고, 그 문단 자신의 글은 따로
                tbls = child.findall('.//' + P + 'tbl')
                own = para_text(child).strip()
                if own:
                    out.append(own)
                for t in tbls:
                    for tr in t.findall(P + 'tr'):
                        cells = []
                        for tc in tr.findall(P + 'tc'):
                            txt = ' '.join(
                                x for x in (para_text(p).strip()
                                            for p in tc.iter(P + 'p')) if x)
                            cells.append(txt)
                        out.append('| ' + ' | '.join(cells) + ' |')
            else:
                walk(child)

    with zipfile.ZipFile(path) as z:
        for name in sorted(n for n in z.namelist()
                           if n.startswith('Contents/section') and n.endswith('.xml')):
            walk(ET.fromstring(z.read(name)))
    return out


def load(path):
    if path.lower().endswith('.hwpx'):
        return read_hwpx(path)
    return read_md(path)


# ─── 1. 상태 칸이 「완료」인데 같은 행이 아니라고 말한다 ─────────────

def is_table_row(line):
    s = line.strip()
    return s.startswith('|') and s.count('|') >= 3


def cells_of(line):
    s = line.strip().strip('|')
    return [c.strip() for c in s.split('|')]


def is_separator(line):
    return bool(re.match(r'^\|[\s:|-]+\|$', line.strip()))


def check_status_vs_prose(lines):
    out = []
    for i, line in enumerate(lines):
        if not is_table_row(line) or is_separator(line):
            continue
        cells = cells_of(line)
        # 마지막 칸(또는 어느 칸이든)이 「완료」 한 낱말이면 그 행은 완료 선언이다
        done_idx = [j for j, c in enumerate(cells)
                    if c in DONE_WORDS or (len(c) <= 6 and any(c.startswith(d) for d in DONE_WORDS))]
        if not done_idx:
            continue
        rest = ' '.join(c for j, c in enumerate(cells) if j not in done_idx)
        hits = [w for w in NOT_DONE if w in rest]
        if hits:
            out.append({
                'rule': 'status_vs_prose',
                'severity': 'error',
                'line': i + 1,
                'detail': '상태 칸은 「%s」인데 같은 행이 「%s」라고 말한다 — '
                          '표와 서술이 서로 다른 말을 한다'
                          % (cells[done_idx[0]], '·'.join(hits)),
                'sample': line.strip()[:110],
            })
    return out


# ─── 2. 「N 가지로 구분」 선언과 실제 표 행 수 ───────────────────────

DECLARE = re.compile(r'(?:을|를|은|는)?\s*([0-9]+|' + '|'.join(KO_NUM) + r')\s*가지(?:로|는|가)?\s*'
                     r'(?:구분|나눈|나누|분류|정의)')


def check_count_mismatch(lines):
    out = []
    for i, line in enumerate(lines):
        m = DECLARE.search(line)
        if not m:
            continue
        tok = m.group(1)
        want = int(tok) if tok.isdigit() else KO_NUM[tok]
        # 아래로 내려가며 첫 표를 찾아 자료 행을 센다
        rows, seen_table, j = 0, False, i + 1
        while j < len(lines) and j < i + 15:
            ln = lines[j]
            if is_table_row(ln):
                seen_table = True
                if not is_separator(ln):
                    cells = cells_of(ln)
                    # 머리 행(구분/뜻 같은 라벨)은 세지 않는다 — 첫 표 행 하나만 건너뛴다
                    rows += 1
            elif seen_table and ln.strip() == '':
                if rows:
                    break
            j += 1
        if not seen_table:
            continue
        actual = max(0, rows - 1)          # 머리 행 제외
        if actual and actual != want:
            out.append({
                'rule': 'count_mismatch',
                'severity': 'error',
                'line': i + 1,
                'detail': '「%d 가지」라고 선언했는데 바로 아래 표는 %d 행이다 — '
                          '항목을 지우고 선언을 안 고쳤을 수 있다' % (want, actual),
                'sample': line.strip()[:110],
            })
    return out


# ─── 3. 본문이 가리키는 절 번호가 실제 제목과 다르다 ────────────────

HEADING = re.compile(r'^#{1,6}\s+([0-9]+(?:-[0-9]+)*)\.\s*(.+)$')
# 「2-1 대조표」·「4-2-3 참조」처럼 번호 뒤에 이름이나 「참조」가 붙은 것만 본다
REF = re.compile(r'(?<![0-9-])([0-9]+-[0-9]+(?:-[0-9]+)?)\s*(대조표|성과품 목록|참조|절)')


def check_section_refs(lines):
    out = []
    headings = {}
    for line in lines:
        m = HEADING.match(line.strip())
        if m:
            headings[m.group(1)] = m.group(2).strip()
    if not headings:
        return out
    for i, line in enumerate(lines):
        if HEADING.match(line.strip()):
            continue
        for m in REF.finditer(line):
            num, word = m.group(1), m.group(2)
            if num not in headings:
                out.append({
                    'rule': 'bad_section_ref',
                    'severity': 'error',
                    'line': i + 1,
                    'detail': '「%s」을 가리키는데 그런 절이 없다 — '
                              '목차를 바꾸고 참조를 안 고쳤을 수 있다' % num,
                    'sample': line.strip()[:110],
                })
                continue
            if word in ('대조표', '성과품 목록') and word not in headings[num]:
                out.append({
                    'rule': 'bad_section_ref',
                    'severity': 'error',
                    'line': i + 1,
                    'detail': '「%s %s」라고 가리키는데 %s 절의 제목은 「%s」다'
                              % (num, word, num, headings[num]),
                    'sample': line.strip()[:110],
                })
    return out


# ─── 4. 같은 라벨의 값이 문서 안에서 다르다 ─────────────────────────

WATCH_LABELS = ['공급가액', '부가가치세', '집행액', '용역비', '계약일', '수행 기간',
                '개발 완료', '사업비', '계약기간']
MONEY = re.compile(r'[0-9]{1,3}(?:,[0-9]{3})+\s*원')
DATE = re.compile(r'20[0-9]{2}\s*[년.]\s*[0-9]{1,2}\s*[월.]\s*[0-9]{1,2}\s*일?')


def check_label_values(lines):
    seen = {}
    out = []
    for i, line in enumerate(lines):
        if not is_table_row(line) or is_separator(line):
            continue
        cells = cells_of(line)
        if len(cells) < 2:
            continue
        label = cells[0]
        if label not in WATCH_LABELS:
            continue
        vals = MONEY.findall(cells[1]) + DATE.findall(cells[1])
        if not vals:
            continue
        key = label
        norm = tuple(re.sub(r'\s+', '', v) for v in vals)
        if key in seen and seen[key][0] != norm:
            out.append({
                'rule': 'label_value_split',
                'severity': 'error',
                'line': i + 1,
                'detail': '「%s」의 값이 %d행에서는 %s 인데 여기서는 %s 다'
                          % (label, seen[key][1], ' / '.join(seen[key][0]), ' / '.join(norm)),
                'sample': line.strip()[:110],
            })
        else:
            seen.setdefault(key, (norm, i + 1))
    return out


# ─── 5. 상태 정의 집합 밖의 분류가 본문에 살아 있다 ─────────────────
#   실측(2026-09-11): 상태를 「완료」 하나로 통일했는데, 다른 절에
#   "그대로 완료: 7개 / 외부 연동만 대기: 3개 / 협의 변경: 2개" 가 통째로 남았다.
#   **표가 아니라 본문 불릿**이라 1번 검사가 못 본다 — agy 가 Critical 로 꼽은 바로 그 자리다.

# ★ 「구분」·「상태」는 아무 표에나 붙는 흔한 머리라 그것으로 찾으면 엉뚱한 표를 집는다
#   (실측: 용역 개요 표의 `| 구분 | 내용 |` 을 상태 정의로 읽어 검사가 조용히 통과했다).
#   「이행 상태」처럼 붙여 쓴 것만 본다.
STATE_DEF_HEAD = re.compile(r'\|\s*이행\s*상태\s*\|')
COUNT_BULLET = re.compile(r'^\s*[-·*]\s*(.+?)\s*[:：]\s*([0-9]+)\s*(?:개|건)')


def state_vocabulary(lines):
    """상태 정의 표에서 허용 상태 집합을 뽑는다. 없으면 (None, None)."""
    for i, line in enumerate(lines):
        if not is_table_row(line) or not STATE_DEF_HEAD.search(line):
            continue
        vocab, j = set(), i + 1
        while j < len(lines) and is_table_row(lines[j]):
            if not is_separator(lines[j]):
                c = cells_of(lines[j])
                if c and c[0]:
                    vocab.add(c[0])
            j += 1
        if vocab:
            return vocab, i + 1
    return None, None


def check_state_vocab(lines):
    """상태를 한 가지로 정의해 놓고 다른 절에서 여러 갈래로 나눠 세면 잡는다.

    ★ 「분류 이름이 정의 집합에 있나」로 판정하지 않는다 — 실측에서 「그대로 완료」처럼
      정의된 말(완료)로 끝나는 수식 표현이 그 검사를 그냥 지나갔다.
      **세는 갈래가 몇 개인가**로 본다. 상태가 한 가지인데 갈래가 둘 이상이면 어긋난 것이다.
    """
    vocab, at = state_vocabulary(lines)
    if not vocab or len(vocab) > 1:
        return []                          # 상태가 여러 가지면 나눠 세는 것이 정상이다
    only = next(iter(vocab))
    out, group = [], []
    for i, line in enumerate(lines + ['']):
        m = COUNT_BULLET.match(line) if line else None
        if m:
            label = m.group(1).strip()
            if any(v in label for v in vocab) or any(w in label for w in NOT_DONE):
                group.append((i + 1, label, m.group(2)))
                continue
        if len(group) >= 2:                # 갈래가 둘 이상 — 상태가 하나인데 나눠 셌다
            out.append({
                'rule': 'state_vocab',
                'severity': 'error',
                'line': group[0][0],
                'detail': '이행 상태를 %d행 표에서 「%s」 한 가지로 정의했는데 여기서는 %d 갈래(%s)로 '
                          '나눠 센다 — 상태를 통일하고 이 분류를 안 고쳤을 수 있다'
                          % (at, only, len(group), ' / '.join(g[1] for g in group)),
                'sample': ' · '.join('%s: %s개' % (g[1], g[2]) for g in group)[:140],
            })
        group = []
    return out


# ─── 실행 ───────────────────────────────────────────────────────────

CHECKS = [
    ('status_vs_prose', check_status_vs_prose),
    ('count_mismatch', check_count_mismatch),
    ('bad_section_ref', check_section_refs),
    ('label_value_split', check_label_values),
    ('state_vocab', check_state_vocab),
]


def run(path):
    lines = load(path)
    findings = []
    for _, fn in CHECKS:
        findings += fn(lines)
    findings.sort(key=lambda f: f['line'])
    return findings, len(lines)


def main():
    ap = argparse.ArgumentParser(
        description='문서 안에서 서로 어긋나는 말을 잡는다 (표↔서술·개수·절 번호·같은 라벨의 값)')
    ap.add_argument('input')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print('파일이 없다: %s' % args.input, file=sys.stderr)
        return 2
    try:
        findings, n = run(args.input)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print('검사 자체가 깨졌다: %s' % exc, file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({'ok': not findings, 'findings': findings},
                         ensure_ascii=False, indent=2))
    elif not findings:
        print('CONTENT GUARD: PASS (%d줄)' % n)
    else:
        print('CONTENT GUARD: FAIL (%d건 / %d줄)' % (len(findings), n))
        for f in findings:
            print('  - %d행 [%s] %s' % (f['line'], f['rule'], f['detail']))
            print('      %s' % f['sample'])
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
