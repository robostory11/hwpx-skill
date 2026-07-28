"""hwpx 두 개를 견주어 무엇이 달라졌는지 알려준다.

왜 필요한가:
  문서를 프로그램으로 만들어 두면, 사람이 한글에서 손으로 고친 내용이 다음 생성 때
  조용히 날아간다. 막으려면 "무엇이 바뀌었는지" 정확히 알아 생성기에 되먹여야 하는데,
  눈으로는 못 찾는 것이 많다 — 도장이 빠졌다거나, 스무 개 조 중 여덟 개만 굵기가
  다르다거나(2026-07-28 TattooDA 계약서에서 실제로 있었던 일).

  hwpx는 사실 압축 파일이라 안을 열어볼 수 있다. 이 도구가 여섯 층을 한 번에 견준다.
    1)   글자          — 내용이 바뀌었나 (표 안 글자까지 · 형광펜이 껴도)
    2)   들어 있는 것   — 그림·도장이 빠졌나 · 알맹이가 바뀌었나 · 쪽 설정이 바뀌었나
    3)   글자 모양 정의 — 크기·굵기·밑줄·색·자간… 속성 전체
    4)   문단 모양 정의 — 정렬·줄간격·문단여백… 속성 전체
    4-2) 머리 정보     — 글꼴·음영·스타일. 3·4층이 번호로만 가리키는 실체
    5)   문단별 서식    — 모양이 다른 곳이 어디인가

  ★ XML을 정규식으로 훑지 않고 파서로 읽는다. 정규식으로 하면 표 안에 문단이 중첩될 때
    바깥 문단이 잘려 글자를 통째로 놓친다(실측: 82개 문단 중 77개만 잡힘). 놓친 채
    "차이 없음"이라고 말하는 것이 이 도구가 저지를 수 있는 가장 나쁜 실패다.

쓰는 법:
  py diff_hwpx.py <기준.hwpx> <비교.hwpx>
    기준 = 프로그램이 만든 것,  비교 = 사람이 손으로 고친 것
    (순서를 바꿔도 되지만, 위 순서로 두면 "사람이 무엇을 고쳤나"로 읽힌다)

  py diff_hwpx.py a.hwpx b.hwpx --글자      글자 차이만
  py diff_hwpx.py a.hwpx b.hwpx --조용히    차이 없으면 아무 말 안 함

되돌아오는 값: 차이가 있으면 1, 없으면 0 (다른 스크립트에서 판정에 쓸 수 있다)
"""
import io
import re
import sys
import difflib
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HP = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
HH = '{http://www.hancom.co.kr/hwpml/2011/head}'
머리XML = 'Contents/header.xml'


def 구역파일(z):
    #    사전순으로 두면 section10이 section2보다 앞에 온다. 숫자로 정렬한다.
    있는것 = [n for n in z.namelist() if re.match(r'Contents/section\d+\.xml$', n)]
    return sorted(있는것, key=lambda n: int(re.search(r'section(\d+)', n).group(1)))


def 지문(e):
    """요소를 견주기 위한 열쇠 — 네임스페이스를 뗀 태그명 + 속성 + 자식들.

    ★ XML 문자열로 견주면 안 된다. 한글이 저장할 때마다 네임스페이스 선언 방식이 달라져
      내용이 같아도 전부 "바뀜"이 된다(실측: paraPr 26종 전부 거짓 경보).
    ★ 그렇다고 몇 개 속성만 골라 견주면 밑줄·기울임·글꼴 같은 나머지 변화가 무음으로
      지나간다. 속성과 자식을 통째로 담아 "설명은 못 해도 달라졌다는 사실은 놓치지 않는다".
    """
    return (e.tag.split('}')[-1], tuple(sorted(e.attrib.items())),
            (e.text or '').strip(), (e.tail or '').strip(),
            tuple(지문(c) for c in e))


def 번호순(x):
    """모양 번호가 늘 숫자라는 보장이 없다. 숫자가 아니면 뒤로 보내고 죽지 않는다.
    여기서 터지면 종료코드 1이 되어 '차이 있음'과 구별되지 않는다."""
    try:
        return (0, int(x))
    except (TypeError, ValueError):
        return (1, str(x))


def 문단들(z):
    """[(글자, [글자모양번호…], 문단모양번호)] — 문단 차례대로. 표 안 문단도 제 자리에 들어간다.

    ★ 문단의 '직속' run만, run의 '직속' t만 모은다. iter()로 훑으면 표를 품은 문단이
      표 안 글자까지 끌어와 같은 글자가 두 번 세어진다(실측: 916자 → 3,576자).
    """
    나온것 = []
    for 이름 in 구역파일(z):
        try:
            뿌리 = ET.fromstring(z.read(이름))
        except ET.ParseError as e:
            print(f'✗ {이름}을 읽지 못했습니다: {e}')
            sys.exit(2)
        for p in 뿌리.iter(HP + 'p'):
            런 = []
            for r in p.findall(HP + 'run'):
                #    ★ t.text는 첫 자식 요소 앞까지만이다. <hp:t> 안에는 형광펜
                #      <hp:markpenBegin/>, 묶음 빈칸 <hp:nbSpace/> 같은 것이 끼고,
                #      그 뒤 글자는 자식의 tail에 들어가 버려진다. 실측: 형광펜이 낀
                #      문단에서 "계약금은 "까지만 읽혀 "30일→90일" 변경을 놓쳤다.
                #      itertext()로 자식 사이 글자까지 모은다.
                글 = ''.join(''.join(t.itertext()) for t in r.findall(HP + 't'))
                if not 글:
                    continue
                #    번호가 없는 run도 글자는 반드시 센다. 안 그러면 그 문단이
                #    통째로 사라져 새 문단이 들어와도 "차이 없음"이 된다.
                런.append((r.get('charPrIDRef') or '?', 글))
            나온것.append((''.join(g for _, g in 런).strip(),
                         [c for c, _ in 런],
                         p.get('paraPrIDRef')))
    return 나온것


def 머리(z):
    if 머리XML not in z.namelist():
        return None
    try:
        return ET.fromstring(z.read(머리XML))
    except ET.ParseError:
        return None


def 글자모양(뿌리):
    """{번호: {크기, 굵게, 밑줄, 기울임, 색, 지문}} — 견주는 것은 '지문', 나머지는 설명용."""
    모양 = {}
    if 뿌리 is None:
        return 모양
    for c in 뿌리.iter(HH + 'charPr'):
        번호 = c.get('id')
        if 번호 is None:
            continue
        높이 = c.get('height')
        #    밑줄·취소선 요소는 꺼져 있어도 늘 들어 있다(type="NONE").
        #    존재만 보면 언제나 "밑줄"이 되므로 값을 봐야 한다.
        밑줄 = c.find(HH + 'underline')
        취소선 = c.find(HH + 'strikeout')
        모양[번호] = {
            '크기': (int(높이) / 100) if 높이 and 높이.isdigit() else None,
            '굵게': c.find(HH + 'bold') is not None,
            '밑줄': 밑줄 is not None and 밑줄.get('type') not in (None, 'NONE'),
            '취소선': 취소선 is not None and 취소선.get('shape') not in (None, 'NONE'),
            '기울임': c.find(HH + 'italic') is not None,
            '색': c.get('textColor'),
            '지문': 지문(c),
        }
    return 모양


def 문단모양(뿌리):
    """{번호: {정렬, 줄간격, 여백, 지문}}

    ★ 지문을 XML 문자열로 만들면 안 된다. 한글이 저장할 때마다 네임스페이스 선언
      방식이 달라져, 내용이 같아도 전부 "바뀜"으로 나온다(실측: 26종 전부 거짓 경보).
      뜻이 있는 값만 뽑아 튜플로 견준다.
    ★ margin·lineSpacing은 <hh:switch> 안에 들어 있어 find()로는 못 찾는다. iter()로 훑는다.
    """
    모양 = {}
    if 뿌리 is None:
        return 모양

    def 첫째(부모, 이름):
        for e in 부모.iter(HH + 이름):
            return e
        return None

    for p in 뿌리.iter(HH + 'paraPr'):
        번호 = p.get('id')
        if 번호 is None:
            continue
        정렬, 간격 = 첫째(p, 'align'), 첫째(p, 'lineSpacing')
        모양[번호] = {
            '정렬': 정렬.get('horizontal') if 정렬 is not None else None,
            '줄간격': (f"{간격.get('value')}{'%' if 간격.get('type') == 'PERCENT' else ''}"
                    if 간격 is not None else None),
            '지문': 지문(p),
        }
    return 모양


def 글자모양설명(d):
    if d is None:
        return '(없음)'
    조각 = []
    if d['크기'] is not None:
        조각.append(f"{d['크기']:g}pt")
    조각.append('굵게' if d['굵게'] else '보통')
    if d.get('밑줄'):
        조각.append('밑줄')
    if d.get('취소선'):
        조각.append('취소선')
    if d.get('기울임'):
        조각.append('기울임')
    if d['색'] and d['색'].lower() not in ('#000000', 'none'):
        조각.append(f"색 {d['색']}")
    return ' · '.join(조각)


def 문단모양설명(d):
    if d is None:
        return '(없음)'
    조각 = []
    if d['정렬']:
        조각.append({'LEFT': '왼쪽', 'CENTER': '가운데', 'RIGHT': '오른쪽',
                    'JUSTIFY': '양쪽'}.get(d['정렬'], d['정렬']))
    if d['줄간격']:
        조각.append(f"줄간격 {d['줄간격']}")
    return ' · '.join(조각) or '(속성 없음)'


def 열기(경로):
    p = Path(경로)
    if not p.exists():
        print(f'✗ 파일이 없습니다: {p}')
        sys.exit(2)
    if p.suffix.lower() != '.hwpx':
        print(f'✗ hwpx만 견줄 수 있습니다(.hwp 구형식은 압축 파일이 아닙니다): {p.name}')
        sys.exit(2)
    try:
        z = zipfile.ZipFile(p)
    except zipfile.BadZipFile:
        print(f'✗ 열 수 없는 파일입니다(hwpx가 아니거나 깨졌습니다): {p.name}')
        sys.exit(2)
    if not 구역파일(z):
        print(f'✗ 본문(Contents/section0.xml)이 없습니다: {p.name}')
        sys.exit(2)
    return z


def main():
    인자 = [a for a in sys.argv[1:] if not a.startswith('--')]
    옵션 = {a for a in sys.argv[1:] if a.startswith('--')}
    if len(인자) != 2:
        print(__doc__)
        sys.exit(2)
    #    모르는 옵션을 조용히 흘리면 "--글자만"처럼 잘못 쳤을 때 그대로 다 돌린다.
    모르는옵션 = 옵션 - {'--글자', '--조용히'}
    if 모르는옵션:
        print(f'✗ 모르는 옵션입니다: {" ".join(sorted(모르는옵션))}')
        print('  쓸 수 있는 것: --글자  --조용히')
        sys.exit(2)

    가경로, 나경로 = Path(인자[0]), Path(인자[1])
    가, 나 = 열기(가경로), 열기(나경로)
    조용히, 글자만 = '--조용히' in 옵션, '--글자' in 옵션

    차이있음 = False
    줄 = []

    def 적기(t=''):
        줄.append(t)

    적기('=' * 64)
    적기(f'  기준: {가경로.name}  ({가경로.stat().st_size:,}바이트)')
    적기(f'  비교: {나경로.name}  ({나경로.stat().st_size:,}바이트)')
    적기('=' * 64)

    가문단, 나문단 = 문단들(가), 문단들(나)
    #    문단이 하나도 없으면 hwpx 껍데기만 있는 것이다. 이걸 "차이 없음"으로 넘기면
    #    아무것도 못 봤으면서 같다고 말하는 꼴이 된다.
    if not 가문단 or not 나문단:
        빈쪽 = 가경로.name if not 가문단 else 나경로.name
        print(f'✗ 본문에 문단이 없습니다: {빈쪽}  (hwpx 구조가 아닐 수 있습니다)')
        sys.exit(2)

    # ── 1. 글자 ────────────────────────────────────────────────
    가글 = [t for t, _, _ in 가문단 if t]
    나글 = [t for t, _, _ in 나문단 if t]
    적기()
    적기('[1] 글자')
    if 가글 == 나글:
        적기(f'    ○ 차이 없음 ({len(가글)}줄 · {sum(len(t) for t in 가글):,}자)')
    else:
        차이있음 = True
        적기(f'    ✗ 다름 — 기준 {len(가글)}줄 / 비교 {len(나글)}줄')
        for d in difflib.unified_diff(가글, 나글, lineterm='', n=0):
            if d.startswith(('---', '+++')):
                continue
            if d.startswith('@@'):
                적기(f'      {d}')
            elif d.startswith('-'):
                적기(f'      빠짐: {d[1:][:120]}')
            elif d.startswith('+'):
                적기(f'      들어옴: {d[1:][:120]}')

    if not 글자만:
        # ── 2. 들어 있는 것 ────────────────────────────────────
        가목록, 나목록 = set(가.namelist()), set(나.namelist())
        적기()
        적기('[2] 들어 있는 것 (그림·도장 등)')
        빠진것, 들어온것 = sorted(가목록 - 나목록), sorted(나목록 - 가목록)
        #    이름이 같아도 알맹이가 바뀔 수 있다 — 도장을 다른 도장으로 갈아끼운 경우.
        #    zip이 이미 갖고 있는 CRC로 견주므로 값이 들지 않는다.
        #    Contents/section*.xml·header.xml은 한글이 다시 저장할 때마다 달라지므로
        #    여기서 보지 않는다(그쪽 변화는 1·3·4·5층이 뜻으로 견준다).
        #    다만 content.hpf는 그 범주가 아니다 — 그림 등록 정보가 여기 있어서,
        #    참조만 되살려도 쓰이지 않는 이미지가 문서에 딸려 나간다.
        def 봐야하나(n):
            return n.startswith('BinData/') or n.endswith('content.hpf')

        내용바뀜 = [n for n in sorted(가목록 & 나목록)
                 if 봐야하나(n) and 가.getinfo(n).CRC != 나.getinfo(n).CRC]
        def 개체수(z, 태그):
            return sum(len(list(ET.fromstring(z.read(n)).iter(HP + 태그)))
                       for n in 구역파일(z))

        #    쪽 설정 — 용지 크기·방향·쪽 여백·단·쪽 테두리·쪽 번호 시작값.
        #    여백이 바뀌면 쪽수가 바뀌고 쪽수가 바뀌면 서명 위치가 바뀐다.
        #    4층의 '여백'은 문단 여백이라 다른 것이다.
        #    ★ secPr를 통째로 담지 않는다. 그 안의 머리말·꼬리말 본문(subList)에는
        #      한글이 재저장할 때마다 달라지는 줄바꿈 정보가 들어 있어 거짓 경보가 난다.
        #      머리말·꼬리말 글자는 1층이 이미 문단으로 읽는다.
        #    ★ colPr(단 나누기)는 secPr 안이 아니라 그 옆에 있다(실측). secPr 안만
        #      뒤지면 1단→2단 변경이 무음이 된다. 구역 파일 전체에서 찾는다.
        쪽설정태그 = ('pagePr', 'colPr', 'pageBorderFill', 'startNum')

        def 쪽설정(z):
            나온것 = []
            for n in 구역파일(z):
                뿌리 = ET.fromstring(z.read(n))
                for 태그 in 쪽설정태그:
                    나온것.extend(지문(e) for e in 뿌리.iter(HP + 태그))
            return 나온것

        말할것 = []
        for n in 빠진것:
            말할것.append(f'비교본에서 빠짐: {n} ({가.getinfo(n).file_size:,}바이트)')
        for n in 들어온것:
            말할것.append(f'비교본에 새로 들어옴: {n} ({나.getinfo(n).file_size:,}바이트)')
        for n in 내용바뀜:
            말할것.append(f'이름은 같은데 알맹이가 바뀜: {n} '
                        f'({가.getinfo(n).file_size:,} → {나.getinfo(n).file_size:,}바이트)')
        for 이름, 태그 in (('그림', 'pic'), ('표', 'tbl'), ('글상자', 'rect')):
            ㄱ, ㄴ = 개체수(가, 태그), 개체수(나, 태그)
            if ㄱ != ㄴ:
                말할것.append(f'{이름} 개수: {ㄱ}개 → {ㄴ}개')
        if 쪽설정(가) != 쪽설정(나):
            말할것.append('쪽 설정(용지 크기·방향·쪽 여백)이 바뀌었습니다')

        if not 말할것:
            적기('    ○ 같음')
        else:
            차이있음 = True
            for m in 말할것:
                적기(f'    ✗ {m}')

        가머리, 나머리 = 머리(가), 머리(나)

        # ── 3. 글자 모양 정의 ──────────────────────────────────
        가글모양, 나글모양 = 글자모양(가머리), 글자모양(나머리)
        적기()
        적기('[3] 글자 모양 정의 (크기·굵기·색)')
        바뀜 = [k for k in sorted(set(가글모양) | set(나글모양), key=번호순)
              if (가글모양.get(k) or {}).get('지문') != (나글모양.get(k) or {}).get('지문')]
        if not 바뀜:
            적기(f'    ○ 같음 ({len(가글모양)}종)')
        else:
            차이있음 = True
            for k in 바뀜[:15]:
                적기(f'    ✗ {k}번: {글자모양설명(가글모양.get(k))} → {글자모양설명(나글모양.get(k))}')
            if len(바뀜) > 15:
                적기(f'    … 그 밖에 {len(바뀜) - 15}종')

        # ── 4. 문단 모양 정의 ──────────────────────────────────
        가문모양, 나문모양 = 문단모양(가머리), 문단모양(나머리)
        적기()
        적기('[4] 문단 모양 정의 (정렬·줄간격·여백)')
        바뀜 = [k for k in sorted(set(가문모양) | set(나문모양), key=번호순)
              if (가문모양.get(k) or {}).get('지문') != (나문모양.get(k) or {}).get('지문')]
        if not 바뀜:
            적기(f'    ○ 같음 ({len(가문모양)}종)')
        else:
            차이있음 = True
            for k in 바뀜[:15]:
                적기(f'    ✗ {k}번: {문단모양설명(가문모양.get(k))} → {문단모양설명(나문모양.get(k))}')
            if len(바뀜) > 15:
                적기(f'    … 그 밖에 {len(바뀜) - 15}종')

        # ── 4-2. 머리 정보 나머지 ──────────────────────────────
        #     3·4층은 charPr·paraPr '정의'만 본다. 그런데 그 정의는 번호로 다른 것을
        #     가리킬 뿐이다 — 글꼴은 fontfaces에, 글자 음영은 borderFills에 있다.
        #     정의를 통째로 담아도 참조 끝의 실체가 바뀌면 무음이 된다.
        #     묶음째로 견줘 그 구멍을 막는다(실측: 한글 재저장판과 생성기판이 모두 같음).
        묶음이름 = {'fontfaces': '글꼴', 'borderFills': '테두리·음영', 'styles': '스타일',
                  'numberings': '번호매기기', 'tabProperties': '탭', 'bullets': '글머리표'}
        적기()
        적기('[4-2] 머리 정보 나머지 (글꼴·음영·스타일 등)')

        def 묶음(뿌리, 이름):
            if 뿌리 is None:
                return None
            for c in 뿌리.iter():
                if c.tag.endswith('}' + 이름):
                    return 지문(c)
            return None

        바뀐묶음 = [(이름, 뜻) for 이름, 뜻 in 묶음이름.items()
                 if 묶음(가머리, 이름) != 묶음(나머리, 이름)]
        if not 바뀐묶음:
            적기('    ○ 같음')
        else:
            차이있음 = True
            for 이름, 뜻 in 바뀐묶음:
                적기(f'    ✗ {뜻}({이름})이 바뀌었습니다')

        # ── 5. 문단별 서식 ─────────────────────────────────────
        #     글자가 같은 문단끼리 견준다. 차례가 밀리지 않도록 SequenceMatcher로
        #     짝을 짓는다(단순히 같은 글자를 앞에서부터 꺼내 쓰면, 문단이 하나
        #     끼어들었을 때 그 뒤 전부가 엉뚱한 짝이 된다).
        적기()
        적기('[5] 문단별 서식 (모양이 다른 곳)')
        #     빈 문단은 어차피 건너뛰므로 짝짓기 목록에서 뺀다. 빈 문단이 수백 개면
        #     똑같은 문자열이 대량 반복되어 SequenceMatcher가 제곱으로 느려진다.
        가쓸것 = [(i, t) for i, (t, _, _) in enumerate(가문단) if t]
        나쓸것 = [(j, t) for j, (t, _, _) in enumerate(나문단) if t]
        맞춤 = difflib.SequenceMatcher(
            None, [t for _, t in 가쓸것], [t for _, t in 나쓸것], autojunk=False)
        바뀐문단 = []
        for 태그, i1, i2, j1, j2 in 맞춤.get_opcodes():
            if 태그 == 'delete' or 태그 == 'insert':
                continue
            #     ★ equal만 보면 "글자와 서식을 함께 고친 문단"을 통째로 건너뛴다.
            #       (예: 30일→90일 + 굵게) 1층은 글자만 알려주므로 굵기를 되먹일 때 빠뜨린다.
            #       replace 구간도 자리끼리 맞춰 서식을 견준다.
            for i, j in zip(range(i1, i2), range(j1, j2)):
                가자리, 글 = 가쓸것[i]
                나자리, 나글 = 나쓸것[j]
                _, ㄱ글모양, ㄱ문모양 = 가문단[가자리]
                _, ㄴ글모양, ㄴ문모양 = 나문단[나자리]
                if ㄱ글모양 != ㄴ글모양 or ㄱ문모양 != ㄴ문모양:
                    보일글 = 글 if 태그 == 'equal' else f'{글}  →  {나글}'
                    바뀐문단.append((보일글, ㄱ글모양, ㄴ글모양, ㄱ문모양, ㄴ문모양))
        if not 바뀐문단:
            적기('    ○ 같음')
        else:
            차이있음 = True
            적기(f'    ✗ {len(바뀐문단)}곳')
            for 글, ㄱ, ㄴ, ㄱ문, ㄴ문 in 바뀐문단[:20]:
                적기(f'      {글[:52]}')
                if ㄱ != ㄴ:
                    앞 = 글자모양설명(가글모양.get(ㄱ[0])) if ㄱ else '-'
                    뒤 = 글자모양설명(나글모양.get(ㄴ[0])) if ㄴ else '-'
                    꼬리 = '' if 앞 == 뒤 else f'  [첫 글자: {앞} → {뒤}]'
                    적기(f'        글자모양 {ㄱ} → {ㄴ}{꼬리}')
                if ㄱ문 != ㄴ문:
                    적기(f'        문단모양 {ㄱ문} → {ㄴ문}'
                        f'  [{문단모양설명(가문모양.get(ㄱ문))}'
                        f' → {문단모양설명(나문모양.get(ㄴ문))}]')
            if len(바뀐문단) > 20:
                적기(f'    … 그 밖에 {len(바뀐문단) - 20}곳')

    적기()
    적기('=' * 64)
    적기('  차이 있음 — 위 내용을 생성기에 되먹이지 않으면 다음 생성 때 날아갑니다.'
        if 차이있음 else '  차이 없음 — 두 파일이 같습니다.')

    if 차이있음 or not 조용히:
        print('\n'.join(줄))
    sys.exit(1 if 차이있음 else 0)


if __name__ == '__main__':
    main()
