---
name: hwpx
description: "HWPX 문서 생성·읽기·편집. 한글 파일 통합 스킬."
allowed-tools: Bash(python3 *), Read, Write, Glob, Grep
---

# HWPX 통합 문서 스킬

HWPX는 한컴오피스 한글의 개방형 문서 포맷이다. **ZIP 패키지 + XML 파트** 구조.

## 스킬 디렉토리

```
${CLAUDE_SKILL_DIR}/
├── SKILL.md
├── scripts/
│   ├── hwpx_helpers.py        # ★ 헬퍼 라이브러리 (배너/섹션바/이미지/빌드 함수)
│   ├── build_hwpx.py          # 템플릿+XML → .hwpx 조립
│   ├── fix_namespaces.py      # ★ 필수: 네임스페이스 후처리
│   ├── validate.py            # HWPX 구조 검증
│   ├── analyze_template.py    # HWPX 심층 분석
│   ├── clone_form.py           # ★ 양식 복제 (Workflow F)
│   ├── verify_hwpx.py         # ★ 서브에이전트 검수 도구
│   ├── text_extract.py        # 텍스트 추출
│   ├── diff_hwpx.py           # ★ 두 hwpx 견주기 (사람이 손으로 고친 것 찾기)
│   ├── md2hwpx.py             # 마크다운→HWPX 자동 변환
│   └── office/{unpack,pack}.py
├── templates/
│   ├── base/                  # 베이스 Skeleton
│   ├── report/                # 보고서
│   ├── gonmun/                # 공문
│   ├── minutes/               # 회의록
│   ├── proposal/              # 제안서
│   └── government/            # ★ 관공서 (컬러 섹션 바/표지 배너)
├── assets/
│   ├── report-template.hwpx
│   └── government-reference.hwpx
└── references/
    ├── xml-structure.md       # XML 구조, 이미지 삽입, 표지/섹션 바 패턴
    ├── template-styles.md     # 템플릿별 스타일 ID 맵
    ├── troubleshooting.md     # 트러블슈팅
    ├── report-style.md        # 보고서 양식 상세
    ├── official-doc-style.md  # 공문서 양식 상세
    └── xml-internals.md       # 저수준 XML 구조
```

## 환경 설정

```bash
pip install python-hwpx lxml --break-system-packages
```

---

## ★ 워크플로우 선택 (Decision Tree)

> **반드시 아래 판단을 따른다.**

```
사용자 요청
 ├─ "마크다운/텍스트/URL → HWPX" → 워크플로우 A (콘텐츠→HWPX)
 ├─ "양식에 내용 채워줘" → 워크플로우 B (템플릿 치환)
 ├─ "HWPX 수정해줘" → 워크플로우 C (기존 문서 편집)
 ├─ "이 HWPX 양식으로 만들어줘" → 워크플로우 D (레퍼런스 기반)
 ├─ "이 양식 복제해서 내용 바꿔줘" → 워크플로우 F (양식 복제) ★
 └─ "HWPX 읽어줘" → 워크플로우 E (읽기/추출)
```

### ⚠️ 자동 판별 규칙 (사용자가 양식 파일을 제공한 경우)

> **사용자가 `.hwpx` 파일을 주고 "이걸로 테스트", "내용 바꿔줘", "이 양식으로" 등을 요청하면
> 먼저 `clone_form.py --analyze`로 구조를 확인한다.**

```
양식 분석 결과
 ├─ 테이블 ≥ 1개 또는 이미지 ≥ 1개 → 워크플로우 F (양식 복제) ★★★
 ├─ 테이블 0개, 이미지 0개, 단순 텍스트 → 워크플로우 C 또는 D 가능
 └─ 판단 불가 → 워크플로우 F를 기본으로 사용 (가장 안전)
```

> **절대 하지 말 것:**
> - `<hp:t>` 노드를 순차적으로 새 텍스트로 덮어쓰기 — **런(run) 소실, 서식 파괴**
> - lxml로 텍스트 노드를 직접 조작 — **네임스페이스/속성 손실 위험**
> - 새 section0.xml을 처음부터 작성 (Workflow A/D) — **구조 97.5% 손실**
>
> **반드시 할 것:**
> - `clone_form.py`의 `clone()` 함수 또는 ZIP-level 문자열 치환 사용
> - 치환은 `str.replace()` 기반으로 XML 구조를 건드리지 않음

---

## 워크플로우 A: 콘텐츠 → HWPX (가장 중요!)

> **마크다운·텍스트·URL → 구조화된 HWPX 문서. 이 워크플로우가 핵심.**

> **⚠️ md2hwpx.py를 직접 실행하지 마라.** md2hwpx.py는 base/report 템플릿만 지원하며,
> government 템플릿의 컬러 배너·섹션 바·표지 페이지를 생성할 수 없다.
> **반드시 `hwpx_helpers.py`를 import하고 아래 흐름을 따른다.**

### 전체 흐름

```
[1] 소스 자료 읽기
[2] 구조 파싱 (제목, 섹션, 본문, 이미지)
[3] 템플릿 선택 → 해당 템플릿의 스타일 ID만 사용 (references/template-styles.md)
    ⚠️ 템플릿 간 ID는 호환되지 않음! government charPr를 report에 쓰면 깨짐
[4] hwpx_helpers.py를 import하여 Python 빌드 스크립트 작성
[5] build_hwpx.py로 .hwpx 조립
[6] 이미지가 있으면 add_images_to_hwpx() + update_content_hpf()
[7] fix_namespaces.py 후처리 (필수!)
[8] validate.py 검증
```

> **올바른 방식**: `from hwpx_helpers import *` → `make_cover_page()` → `make_section_bar()` → `make_body_para()`
> **잘못된 방식**: `python3 md2hwpx.py input.md` (컬러 배너·섹션 바 없음, 기본 스타일만 적용)

### section0.xml 핵심 규칙

1. **첫 문단 첫 run에 secPr + colPr 필수** — 없으면 문서가 안 열림
2. **모든 문단 id는 고유 정수**
3. **XML 특수문자 `<>&"` 반드시 이스케이프**
4. **표지→본문 사이 `pageBreak="1"` 문단 삽입**

> XML 구조 상세: [references/xml-structure.md](references/xml-structure.md)

### 빌드 명령

```bash
# 1. section0.xml을 임시 파일로 작성 (Python 스크립트로 생성)

# 2. 빌드 (government 템플릿 사용 시)
python3 "${CLAUDE_SKILL_DIR}/scripts/build_hwpx.py" \
  --header "${CLAUDE_SKILL_DIR}/templates/government/header.xml" \
  --section /tmp/section0.xml \
  --title "문서 제목" \
  --output result.hwpx

# 3. 네임스페이스 후처리 (필수!)
python3 "${CLAUDE_SKILL_DIR}/scripts/fix_namespaces.py" result.hwpx

# 4. 검증
python3 "${CLAUDE_SKILL_DIR}/scripts/validate.py" result.hwpx
```

### Python 빌드 스크립트 패턴

> **`scripts/hwpx_helpers.py`를 import하여 검증된 함수를 재사용한다.**

```python
import subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path("${CLAUDE_SKILL_DIR}/scripts")))
from hwpx_helpers import *

SKILL_DIR = Path("${CLAUDE_SKILL_DIR}")
REF_HWPX = SKILL_DIR / "assets" / "government-reference.hwpx"
OUTPUT = Path("output.hwpx")

# 0. government header 검증 (잘못된 header 사용 방지)
GOV_HEADER = SKILL_DIR / "templates/government/header.xml"
validate_header_for_government(GOV_HEADER)

# 1. secPr 추출
secpr, colpr = extract_secpr_and_colpr(REF_HWPX)

# 2. section0.xml 조립
parts = []
parts.append(f'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>')
parts.append(f'<hs:sec {NS_DECL}>')
parts.append(make_first_para(secpr, colpr))
parts.extend(make_cover_page("문서 제목", subtitle="(부제)", date="2026. 3."))
parts.append(make_cover_banner("문서 제목"))  # 본문 페이지 배너
parts.append(make_empty_line())
parts.append(make_section_bar("1", "섹션 제목"))
parts.append(make_body_para("가.", "본문 내용"))
parts.append(f'</hs:sec>')
section_xml = "\n".join(parts)

# 3. 빌드
Path("/tmp/section0.xml").write_text(section_xml, encoding="utf-8")
subprocess.run(["python3", str(SKILL_DIR/"scripts/build_hwpx.py"),
    "--header", str(SKILL_DIR/"templates/government/header.xml"),
    "--section", "/tmp/section0.xml", "--output", str(OUTPUT)], check=True)

# 4. (이미지 있으면) add_images_to_hwpx() + update_content_hpf()

# 5. 후처리 + 검증
subprocess.run(["python3", str(SKILL_DIR/"scripts/fix_namespaces.py"), str(OUTPUT)], check=True)
subprocess.run(["python3", str(SKILL_DIR/"scripts/validate.py"), str(OUTPUT)])
```

### hwpx_helpers.py 제공 함수

| 함수 | 설명 |
|------|------|
| `next_id()` | 고유 ID 생성 |
| `xml_escape(text)` | XML 특수문자 이스케이프 |
| `validate_header_for_government(path)` | header.xml이 government용인지 검증 (크기·charPr 수 체크) |
| `extract_secpr_and_colpr(hwpx)` | HWPX에서 secPr+colPr 추출 |
| `make_first_para(secpr, colpr)` | 첫 문단 (secPr 포함) |
| `make_empty_line()` | 빈 줄 |
| `make_page_break()` | 페이지 넘김 |
| `make_text_para(text, charpr, parapr)` | 텍스트 문단 |
| `make_body_para(marker, text)` | 본문 (마커+내용) |
| `make_cover_banner(title)` | 표지 배너 (3×2 컬러 테이블) |
| `make_section_bar(number, title)` | 섹션 바 (1×3 컬러 테이블) |
| `make_cover_page(title, subtitle, date)` | 표지 전체 + pageBreak |
| `make_image_para(binary_item_id, w, h)` | 이미지 (전체 hp:pic 구조) |
| `add_images_to_hwpx(path, images)` | ZIP에 이미지 추가 |
| `update_content_hpf(path, images)` | content.hpf에 이미지 등록 |
| `NS_DECL` | 네임스페이스 선언 상수 |

> 스타일 ID 상세: [references/template-styles.md](references/template-styles.md)

### 이미지 포함 시

> **이미지 `<hp:pic>` 구조가 불완전하면 한컴오피스가 크래시한다.**
> 반드시 [references/xml-structure.md](references/xml-structure.md)의 "이미지 삽입" 섹션을 읽고 전체 구조를 사용할 것.

---

## 워크플로우 B: 템플릿 치환

> **기존 양식의 플레이스홀더를 교체. 양식 문서에 적합.**

```
[1] 양식 파일 복사 → [2] ObjectFinder로 텍스트 조사
[3] 플레이스홀더 매핑 → [4] ZIP-level 치환 → [5] fix_namespaces.py → [6] 검증
```

### ZIP-level 치환

```python
import zipfile, os

def zip_replace(src, dst, replacements):
    tmp = dst + ".tmp"
    with zipfile.ZipFile(src, "r") as zin:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.startswith("Contents/") and item.filename.endswith(".xml"):
                    text = data.decode("utf-8")
                    for old, new in replacements.items():
                        text = text.replace(old, new)
                    data = text.encode("utf-8")
                if item.filename == "mimetype":
                    zout.writestr(item, data, compress_type=zipfile.ZIP_STORED)
                else:
                    zout.writestr(item, data)
    os.replace(tmp, dst)
```

### 양식 선택 정책

1. 사용자 업로드 양식 → 해당 파일 사용
2. `${CLAUDE_SKILL_DIR}/assets/report-template.hwpx`
3. HwpxDocument.new()는 최후의 수단

---

## 워크플로우 C: 기존 문서 편집

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/office/unpack.py" doc.hwpx ./unpacked/
# XML 편집 후
python3 "${CLAUDE_SKILL_DIR}/scripts/office/pack.py" ./unpacked/ edited.hwpx
python3 "${CLAUDE_SKILL_DIR}/scripts/fix_namespaces.py" edited.hwpx
```

## 워크플로우 D: 레퍼런스 기반 생성

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/analyze_template.py" reference.hwpx
# header.xml 추출 후 동일 스타일 ID로 새 section0.xml 작성
python3 "${CLAUDE_SKILL_DIR}/scripts/build_hwpx.py" \
  --header /tmp/ref_header.xml --section /tmp/new_section.xml --output result.hwpx
python3 "${CLAUDE_SKILL_DIR}/scripts/fix_namespaces.py" result.hwpx
```

## 워크플로우 E: 읽기/추출

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/text_extract.py" doc.hwpx
python3 "${CLAUDE_SKILL_DIR}/scripts/text_extract.py" doc.hwpx --format markdown
```

---

## 워크플로우 E-2: 두 hwpx 견주기 (★ 사람이 손으로 고친 것 되찾기)

> **문서를 프로그램으로 만들어 두는 경우, 사람이 한글에서 손으로 고친 내용은 다음 생성 때
> 조용히 날아간다.** 막으려면 무엇이 바뀌었는지 정확히 알아 **생성기에 되먹여야** 하는데,
> 눈으로는 못 찾는 것이 많다.

```bash
py "${CLAUDE_SKILL_DIR}/scripts/diff_hwpx.py" <프로그램이_만든것>.hwpx <사람이_고친것>.hwpx
py "${CLAUDE_SKILL_DIR}/scripts/diff_hwpx.py" a.hwpx b.hwpx --글자     # 글자 차이만
py "${CLAUDE_SKILL_DIR}/scripts/diff_hwpx.py" a.hwpx b.hwpx --조용히   # 같으면 침묵
# 되돌아오는 값: 차이 있으면 1, 없으면 0
```

다섯 층을 한 번에 본다.

| 층 | 무엇을 잡나 |
|---|---|
| 1. 글자 | 내용이 바뀌었나 (문단 단위 diff · 표 안 글자까지) |
| 2. 들어 있는 것 | 그림·도장이 빠졌나 들어왔나 · **이름이 같아도 알맹이가 바뀌었나**(CRC) |
| 3. 글자 모양 정의 | charPr — 크기·굵기·밑줄·색·글꼴·자간… **속성 전체** |
| 4. 문단 모양 정의 | paraPr — 정렬·줄간격·여백·테두리… **속성 전체** |
| 5. 문단별 서식 | **글자는 같은데 모양만 다른 곳** — 어느 문단에서 굵기·정렬이 바뀌었나 |

**5번이 핵심이다.** 글자가 안 바뀌었다고 "차이 없음"으로 넘기면 서식 수정을 통째로 잃는다.

3·4층은 몇 개 속성만 골라 보지 않고 **요소의 속성과 자식을 통째로** 견준다. 골라 보면
밑줄·글꼴·자간처럼 목록에 없는 변화가 조용히 지나간다. "무엇이 달라졌는지 설명은 못 해도
달라졌다는 사실은 놓치지 않는다"가 이 도구의 원칙이다.

### 이 도구가 못 보는 것 (한계를 알고 쓸 것)

"차이 없음"이 **문서가 완전히 같다는 뜻은 아니다.** 아래는 아직 못 잡는다.

| 못 잡는 것 | 왜 |
|---|---|
| 표의 셀 병합·셀 크기 | 표 구조를 따로 견주지 않는다(표 안 **글자**는 1층이 본다) |
| 쪽 여백·용지 방향(secPr) | 구역 설정을 안 본다 |
| 개체 위치 이동 | 도장을 옮기기만 하면 이름·알맹이가 그대로다 |
| 각주·머리말·꼬리말 | 본문 문단만 순회한다 |
| 하이퍼링크 주소 | 겉글자만 본다 |

발송 직전 최종 확인은 **한글이나 PDF로 눈으로 보는 것**을 대신하지 못한다.
이 도구는 "눈으로는 못 찾는 것"을 잡아 주는 보조 수단이다.

### 만들면서 부딪힌 함정 셋 (같은 걸 새로 짤 때 반복하지 말 것)

1. **XML을 정규식으로 훑지 말 것.** 표 안에 문단이 중첩되면 `<hp:p …>.*?</hp:p>`가 바깥
   문단을 잘라 글자를 통째로 놓친다(실측: 82개 중 77개만 잡힘). `xml.etree.ElementTree`로 읽는다.
2. **문단의 '직속' run만, run의 '직속' t만 모을 것.** `iter()`로 훑으면 표를 품은 문단이
   표 안 글자까지 끌어와 같은 글자를 두 번 센다(실측: 916자 → 3,576자).
3. **문단 모양을 XML 문자열로 견주지 말 것.** 한글이 저장할 때마다 네임스페이스 선언 방식이
   달라져 내용이 같아도 전부 "바뀜"이 된다(실측: 26종 전부 거짓 경보). 뜻이 있는 값
   (정렬·줄간격·여백)만 뽑아 견준다. `margin`·`lineSpacing`은 `<hh:switch>` 안에 있어
   `find()`로는 못 찾으니 `iter()`로 훑는다.

문단 짝짓기는 `difflib.SequenceMatcher`로 한다. 같은 글자를 앞에서부터 꺼내 쓰면 문단이
하나 끼어들었을 때 그 뒤가 전부 엉뚱한 짝이 되어 거짓 경보가 쏟아진다.

### 되먹이는 절차 (2026-07-28 실제 사례)

TattooDA 계약서에서 사장님이 한글로 두 가지를 고치셨다. **글자는 136줄 그대로**였다.
1. 직인을 뺐다 → `BinData/image1.png`와 `<hp:pic>`이 사라짐 (2층에서 잡힘)
2. 조 제목 여덟 개를 굵게 했다 → 2·3·5·7·8·9·12·18조 (4층에서 잡힘)

되먹인 방법:
- 굵기: 생성기의 강조 함수가 앞부분을 통째로 보통 글씨로 넣고 있었다.
  `제N조(제목)`을 정규식으로 떼어 그 부분만 굵은 글자모양으로 주도록 고침.
- 직인: 서명란을 템플릿에서 가져올 때 `<hp:pic>…</hp:pic>` 제거 +
  `BinData/image1.png` 삭제 + `Contents/content.hpf`의 `<opf:item>` 등록 제거.
  **참조만 지우면 안 보일 뿐 이미지가 그대로 딸려 나간다**(4MB → 115KB).

검증: 정본을 덮어쓰지 말고 **임시 경로로 생성**해 이 도구로 다시 견준다.
"차이 없음"이 나와야 되먹이기가 끝난 것이다.

> **애초에 손으로 고쳤음을 알아채려면** 발송본과 원본의 해시를 대조하는 검사를 따로 둘 것.
> 그 검사가 없으면 사람이 고친 줄 모르고 덮어쓴다.

---

## 워크플로우 F: 양식 복제 (★ 복잡한 양식에 필수)

> **기존 HWPX를 통째로 복사 + 텍스트만 치환. 테이블·이미지·스타일 100% 보존.**
>
> ⚠️ **테이블 5개 이상 또는 이미지 포함이면 반드시 워크플로우 F 사용.**
> 워크플로우 D는 header만 재활용하고 section을 새로 만들기 때문에 구조의 97.5%를 잃는다.

### 전체 흐름

```
[1] 원본 양식 분석:  clone_form.py --analyze sample.hwpx
[2] 구문 치환 맵 작성 (JSON): {"원본 문구": "새 문구", ...}
[3] (선택) 키워드 폴백 맵 작성: {"재난": "교육위기", "안전": "AI교육", ...}
[4] 복제 실행:  clone_form.py sample.hwpx output.hwpx --map map.json --keywords kw.json
[5] fix_namespaces.py 후처리 (필수!)
[6] validate.py 검증
```

### 2단계 치환 전략

| 단계 | 범위 | 용도 |
|------|------|------|
| Phase 1 (--map) | 전체 XML | 긴 문구·문장 단위 치환 |
| Phase 2 (--keywords) | `<hp:t>` 내부만 | 남은 키워드 개별 치환 (폴백) |

> 키워드는 길이 내림차순 정렬하여 "재난안전관리"가 "재난"보다 먼저 매칭된다.
> Phase 2는 `<hp:t>` 태그 안의 텍스트만 대상이므로 XML 구조를 손상시키지 않는다.

### CLI 사용법

```bash
# 분석
python3 "${CLAUDE_SKILL_DIR}/scripts/clone_form.py" --analyze sample.hwpx

# 복제 (구문 치환만)
python3 "${CLAUDE_SKILL_DIR}/scripts/clone_form.py" \
  sample.hwpx output.hwpx --map replacements.json

# 복제 (구문 + 키워드 폴백)
python3 "${CLAUDE_SKILL_DIR}/scripts/clone_form.py" \
  sample.hwpx output.hwpx --map map.json --keywords keywords.json --validate

# 후처리 (필수!)
python3 "${CLAUDE_SKILL_DIR}/scripts/fix_namespaces.py" output.hwpx
python3 "${CLAUDE_SKILL_DIR}/scripts/validate.py" output.hwpx
```

### Python API

```python
from clone_form import clone, analyze, extract_texts, validate_result

# 분석
texts = analyze("sample.hwpx")

# 복제
clone("sample.hwpx", "output.hwpx",
      replacements={"원본 문구": "새 문구"},
      keywords={"재난": "교육위기"},
      title="새 문서 제목", creator="작성자")

# 검증
result = validate_result("sample.hwpx", "output.hwpx",
                         replacements={...}, keywords={...})
print(f"커버리지: {result['coverage_pct']:.1f}%")
```

### 워크플로우 D vs F 비교

| 항목 | D (레퍼런스 기반) | F (양식 복제) |
|------|------------------|--------------|
| 원본 구조 보존 | ~2.5% | **100%** |
| 테이블 | ❌ 재구성 필요 | ✅ 그대로 |
| 이미지 | ❌ BinData 누락 | ✅ 그대로 |
| 스타일 | ⚠️ ID 매칭 필요 | ✅ 그대로 |
| 적합한 경우 | 간단한 텍스트 문서 | **복잡한 양식** |

---

## 서브에이전트 검수 (★ 권장)

> **문서 생성 후 별도 서브에이전트를 생성하여 품질 검증을 수행한다.**
> 생성 에이전트와 검수 에이전트를 분리하면 실수를 줄일 수 있다.

### 검수 도구

```bash
# 원본과 비교 검수 (구조 보존 확인)
python3 "${CLAUDE_SKILL_DIR}/scripts/verify_hwpx.py" \
  --source original.hwpx --result output.hwpx

# 단독 검수 (XML 유효성 + 구조 체크)
python3 "${CLAUDE_SKILL_DIR}/scripts/verify_hwpx.py" --result output.hwpx

# JSON 리포트 출력 (자동화용)
python3 "${CLAUDE_SKILL_DIR}/scripts/verify_hwpx.py" \
  --source original.hwpx --result output.hwpx --json report.json
```

### 검수 항목

| 검사 | 내용 | FAIL 조건 |
|------|------|-----------|
| mimetype | 첫 엔트리 + ZIP_STORED | 위치·압축 불일치 |
| 필수 파일 | header.xml, section0.xml 등 | 누락 시 |
| XML 유효성 | 모든 XML 파싱 가능 | 파싱 오류 |
| 런 보존 | 원본 대비 런(run) 수 | **감소 시 FAIL** |
| 테이블·이미지 | 원본 대비 수량 | 감소 시 FAIL |
| section 크기 | 원본 대비 비율 | 50% 미만 시 FAIL |

### 서브에이전트 워크플로우 예시

```
[메인 에이전트]
  1. clone_form.py로 문서 생성
  2. fix_namespaces.py 후처리
  ↓
[검수 서브에이전트 생성]
  3. verify_hwpx.py --source --result 실행
  4. text_extract.py로 텍스트 추출 확인
  5. PASS/FAIL 리포트 반환
  ↓
[메인 에이전트]
  6. FAIL이면 수정 후 재검수
  7. PASS이면 사용자에게 전달
```

---

## 네임스페이스 후처리 (★ 필수)

> **⚠️ 빠뜨리면 한글 Viewer에서 빈 페이지로 표시된다!**

```python
import subprocess
subprocess.run(["python3", f"{SKILL_DIR}/scripts/fix_namespaces.py", "output.hwpx"], check=True)
```

| URI | 프리픽스 |
|-----|---------|
| `.../2011/head` | `hh` |
| `.../2011/core` | `hc` |
| `.../2011/paragraph` | `hp` |
| `.../2011/section` | `hs` |

---

## 단위 변환

| 값 | HWPUNIT | 의미 |
|----|---------|------|
| 1pt | 100 | 기본 단위 |
| 1mm | 283.5 | 밀리미터 |
| A4 폭 | 59528 | 210mm |
| A4 높이 | 84186 | 297mm |
| 좌우여백 | 8504 | 30mm |
| 본문폭 | 42520 | 150mm |

---

## Critical Rules

1. **HWPX만 지원**: `.hwp`(바이너리)는 미지원
2. **secPr 필수**: 첫 문단 첫 run에 secPr + colPr
3. **mimetype**: 첫 ZIP 엔트리, ZIP_STORED
4. **네임스페이스**: `hp:`, `hs:`, `hh:`, `hc:` 접두사 유지
5. **fix_namespaces 필수**: 모든 빌드 후 반드시 실행
6. **fix_namespaces 호출법**: `subprocess.run()` 사용 (`exec()` 금지)
7. **build_hwpx.py 우선**: 새 문서는 build_hwpx.py 사용
8. **검증 필수**: 생성 후 validate.py 실행
9. **XML 이스케이프**: `<>&"` 반드시 이스케이프
10. **ID 고유성**: 모든 문단 id는 문서 내 고유
11. **이미지**: `<hp:pic>` 필수 구조 준수 → [xml-structure.md](references/xml-structure.md)
12. **템플릿 ID 호환 불가**: government charPr/paraPr/borderFill ID를 report/base 등 다른 템플릿에 사용하면 깨짐. 반드시 해당 템플릿의 ID만 사용. base charPr 3은 "16pt 제목"이 아니라 "9pt 각주"임에 주의
13. **hwpx_helpers.py 사용 필수**: md2hwpx.py 직접 실행 금지. 반드시 `from hwpx_helpers import *`로 함수를 사용하여 빌드 스크립트를 작성할 것. md2hwpx.py는 government 템플릿(컬러 배너/섹션 바)을 지원하지 않음
14. **양식 복제 시 Workflow F 필수**: 사용자가 `.hwpx` 양식을 제공하고 내용 변경을 요청하면 `clone_form.py` 사용. 절대로 `<hp:t>` 노드를 순차 덮어쓰기하거나 lxml로 텍스트를 직접 조작하지 말 것 (런 소실·서식 파괴 원인)
15. **서브에이전트 검수 권장**: 문서 생성 후 별도 서브에이전트로 `validate.py` + `text_extract.py` + 구조 비교를 실행하여 품질 검증

---

## 상세 참조

- **XML 구조·이미지·표지 패턴**: [references/xml-structure.md](references/xml-structure.md)
- **템플릿별 스타일 ID 맵**: [references/template-styles.md](references/template-styles.md)
- **트러블슈팅**: [references/troubleshooting.md](references/troubleshooting.md)
- **보고서 양식**: [references/report-style.md](references/report-style.md)
- **공문서 양식**: [references/official-doc-style.md](references/official-doc-style.md)
- **보고서 기호**: □(16pt) → ○(15pt) → ―(15pt) → ※(13pt)
- **공문서 번호**: 1. → 가. → 1) → 가) → (1) → (가) → ① → ㉮
