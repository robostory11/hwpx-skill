# HWPX 트러블슈팅

## "문서가 손상되었거나 변조되었을 가능성" 보안 경고 (열기 거부)

> 한글 GUI에서 "[문서 보안 설정]을 [낮음]으로 설정해야 합니다" 메시지와 함께 열리지 않는 증상.
> 2026-06-11 실사례 + 한컴 개발자 포럼 공식 답변(forum.developer.hancom.com/t/hwpx-section0-xml/2414)으로 확인.

| 원인 | 해결 |
|------|------|
| 한글이 저장한 hwpx의 section0.xml 텍스트를 외부에서 수정 → 각 문단의 `<hp:linesegarray>`(줄 레이아웃 캐시)와 실제 텍스트가 불일치 → 한글이 변조로 판정 | **수정한 section0.xml에서 `<hp:linesegarray>...</hp:linesegarray>`를 전부 제거** (optional 요소라 제거 시 한글이 재계산). `re.sub(r'<hp:linesegarray>.*?</hp:linesegarray>', '', xml, flags=re.S)` |

- ZIP 재포장 방식·메타데이터 문제가 아님 (local header까지 동일해도 발생)
- clone_form.py / ZIP-level 치환으로 텍스트를 바꾼 모든 경우에 적용 - **한글 저장본을 치환 편집했으면 linesegarray 제거를 표준 후처리로 실행할 것**
- 검증 시 verify_hwpx.py의 section 크기 비율이 줄어드는 것은 linesegarray 제거 때문이므로 정상

## "한글에서 빈 페이지로 열림"

| 원인 | 해결 |
|------|------|
| fix_namespaces.py 미실행 | 반드시 후처리 실행 |
| section0.xml에 secPr 없음 | 첫 문단 첫 run에 secPr + colPr 포함 |
| charPrIDRef가 header.xml에 없는 ID 참조 | 템플릿에 정의된 ID만 사용 |
| mimetype이 첫 ZIP 엔트리 아님 | build_hwpx.py 사용 시 자동 처리 |

## ★ "한컴이 '손상된 문서' 복구 대화상자를 띄움" (secPr 불완전)

> **validate.py(XML 유효성)와 fill verify(값 존재)를 통과해도 한컴이 안 열리는 가장 흔한 원인.**
> LLM이 section0.xml을 손수 작성하면 secPr을 `<hp:secPr pageWidth=".." leftMargin="..">`처럼
> **가짜 속성**으로 만들기 쉽다. 실제 HWPX 스키마는 secPr의 **자식 요소**
> `<hp:pagePr>`(용지 크기)+`<hp:margin>`(여백)을 요구한다. 이게 없으면 한컴은
> 문서를 그릴 수 없어 손상 판정한다.

| 증상 | 진단 | 해결 |
|------|------|------|
| validate 통과·한컴 손상 경고 | `fill_hwpx.py check 파일.hwpx` 실행 → secPr errors 확인 | 정상 HWPX의 secPr을 이식 |
| secPr에 pageWidth/leftMargin 등 속성 | LLM이 손수 작성한 가짜 secPr | 동일 용지의 정상 파일에서 `<hp:secPr>...</hp:secPr>` 통째 복사 |
| secPr에 pagePr/margin 자식 없음 | 필수 자식 누락 | templates/base 또는 정상 파일의 secPr 사용 |

```bash
# 배포 전 항상 열림 가능성 점검 (값 없이도 실행 가능)
python3 scripts/fill_hwpx.py check output.hwpx     # exit 0=정상, 2=secPr 문제
```

> **교훈: LLM이 section0.xml을 처음부터 쓰지 말 것.** 정상 HWPX(워크플로우 H 변환본
> 또는 한컴 저장본)를 베이스로 fill/replace만 적용하면 secPr이 자동 보존된다.

## ★ "한컴에서 빈 페이지로 열림 (손상 경고는 없음)" — raw LLM 파일

> secPr은 멀쩡한데도 본문이 안 보이면, **한컴을 한 번도 거치지 않은 raw 파일**일
> 가능성이 높다. 한컴은 저장 시 본문 기반으로 미리보기(Preview/PrvText.txt)와
> 줄배치 캐시(hp:linesegarray)를 항상 생성하는데, LLM이 section XML을 손수 만들어
> ZIP으로 묶기만 하면 이 둘이 비어 본문 레이아웃이 그려지지 않는다.

| 진단 | 신호 | 해결 |
|------|------|------|
| `fill_hwpx.py check 파일.hwpx --strict` | `raw_llm_suspect: true` | 정상 HWPX를 베이스로 fill/replace |
| PrvText.txt가 거의 빔 (2~3자) | 미리보기 미생성 | 한컴에서 한 번 열어 저장 |
| section에 linesegarray 0개 | 줄배치 캐시 부재 | 한컴 저장본/워크플로우 H 변환본 사용 |

```bash
# 배포 전 raw 파일까지 걸러내기 (한컴 미경유 파일 차단)
python3 scripts/fill_hwpx.py check output.hwpx --strict
```

> **근본 해결**: `자문_수락서.hwpx` 같은 raw 파일을 만들지 말고, 한컴에서 저장한
> 정상 .hwpx를 베이스로 `fill`/`replace`만 적용하라. 그러면 미리보기·줄배치·secPr이
> 모두 보존된 채 내용만 바뀐다. `scripts/hwpx_guard_hook.py`를 PreToolUse 훅으로
> 걸면 raw/깨진 파일이 사용자에게 전달되기 전에 자동 차단된다.

## "내용은 있지만 서식이 깨짐"

| 원인 | 해결 |
|------|------|
| 템플릿과 section0.xml의 스타일 ID 불일치 | analyze_template.py로 실제 ID 확인 |
| header.xml의 itemCnt 불일치 | charPr/paraPr/borderFill 수와 맞추기 |
| 글꼴 미설치 | 함초롬돋움, 함초롬바탕 등 필요 |

## "표가 잘려서 보임"

| 원인 | 해결 |
|------|------|
| 열 너비 합 ≠ 본문폭 | 열 너비의 합을 본문폭과 일치 |
| rowCnt/colCnt 불일치 | 실제 행/열 수와 속성값 맞추기 |

## "이미지 포함 문서에서 한컴오피스 크래시"

| 원인 | 해결 |
|------|------|
| `<hp:pic>`에 필수 자식 요소 누락 | xml-structure.md의 `<hp:pic>` 전체 구조 사용 |
| `href=""`, `groupLevel="0"`, `instid`, `reverse="0"` 누락 | `<hp:pic>` 속성에 반드시 포함 |
| `<hp:renderingInfo>` 미포함 | transMatrix, scaMatrix, rotMatrix 전부 포함 |
| `<hp:imgClip>`, `<hp:imgDim>`, `<hp:effects/>` 누락 | 전부 포함 |
| `<hp:sz>`, `<hp:pos>` 순서 잘못 | `<hp:effects/>` 뒤에 배치 |
| `</hp:pic>` 뒤 `<hp:t/>` 누락 | run 안에 빈 텍스트 노드 추가 |
| content.hpf에 이미지 미등록 | `<opf:item>` 추가 (isEmbeded="1") |

## ★ "변환 후 모든 글자에 네모 테두리가 생김" (hwp2hwpx 버그)

> HWP→HWPX 변환 시 변환기가 글자모양(charPr)마다 테두리 borderFill을
> 참조시켜 **문서의 모든 글자에 검은 네모 테두리**가 생긴다. 표 셀 테두리가
> 아니라 글자 하나하나에 박스가 쳐진 모양이면 이 버그다.

| 원인 | 해결 |
|------|------|
| charPr의 borderFillIDRef가 테두리(SOLID) borderFill을 참조 | `convert_hwp.py`는 변환 직후 자동 제거(기본 동작) |
| 이미 변환된 .hwpx에 테두리가 남음 | `python3 scripts/fill_hwpx.py fix-borders 파일.hwpx` |
| 표 셀 테두리까지 사라질까 걱정 | tc(표 셀)의 borderFillIDRef는 section에 있어 보존됨 |

```bash
# 이미 변환된 파일 보정 (표 테두리는 유지, 글자 테두리만 제거)
python3 scripts/fill_hwpx.py fix-borders 변환본.hwpx              # 덮어쓰기
python3 scripts/fill_hwpx.py fix-borders 변환본.hwpx out.hwpx     # 새 파일로

# 배포 전 점검 — 글자 테두리도 함께 검사 (strict면 차단)
python3 scripts/fill_hwpx.py check 파일.hwpx --strict
```

> **convert_hwp.py를 거치지 않은 경로 주의**: 이미 변환된 hwpx(또는 한컴 저장본)를
> 베이스로 replace/clone만 하면 변환 시점의 자동 보정이 안 걸려 글자 테두리가
> 남는다. `hwpx_guard_hook.py`를 PreToolUse 훅으로 걸면 파일을 사용자에게 전달
> (open/cp)하기 직전 **글자 테두리를 자동 제거**하므로 어떤 경로든 안전하다.

## "python-hwpx 에러"

| 원인 | 해결 |
|------|------|
| HwpxDocument.open() 실패 | XML-first 접근 또는 ZIP-level 치환 사용 |
| ObjectFinder 에러 | `pip install python-hwpx --break-system-packages` |

## Hancom says the file is damaged after text replacement

| Cause | Fix |
|------|-----|
| Stale `hp:linesegarray` layout caches remain after editing text outside Hancom | Run `python3 scripts/finalize_hwpx.py output.hwpx --strip-linesegarray` before validation |
| XML validation passed but Hancom still refuses the file | Run `python3 scripts/validate.py output.hwpx --hancom` on Windows with Hancom Office installed |
| Template was filled by rewriting XML nodes and losing run/control structure | Recreate from the original template with `clone_form.py` or ZIP-level string replacement, then finalize |

## Text is squeezed or overlaps in table cells

| Cause | Fix |
|------|-----|
| Long content is stored as one paragraph in a fixed-height cell | Split it into real `hp:p` paragraphs or list items |
| Row height was not updated after content expansion | Increase every `hp:cellSz/@height` in the row and update table `hp:sz/@height` |
| Text was forced to fit by changing the template structure | Keep the template structure; write an editing note when content cannot fit without a format decision |

Use:

```bash
python3 scripts/finalize_hwpx.py output.hwpx --layout
```

The layout check is warning-based. It identifies likely risks that still need
template-aware review.

## 한컴 재저장이 안 끝날 때 (2026-09-02 실측)

### ★★★★★ 그 「환경 문제」의 정체 — 보안 모듈 등록이 죽은 경로를 가리킨다 (2026-09-02 해결)

아래 절을 쓴 날 저녁에 **원인을 잡고 고쳤다.** paperwork 저장소를 뒤져 나온 것이다.

| 실측 | 값 |
|---|---|
| `HKCU\Software\HNC\HwpAutomation\Modules` 의 `FilePathCheckerModule` | `C:\dev\reportshot\venv\Lib\site-packages\pyhwpx\FilePathCheckerModule.dll` |
| 그 파일 | **없다.** `C:\dev\reportshot` 폴더가 2026-08-16 에 지워졌다(`C:\dev\.projects-meta.yml:374`) |
| 살아 있는 같은 DLL | `%APPDATA%\Python\Python3xx\site-packages\pyhwpx\FilePathCheckerModule.dll` (pyhwpx 설치본) |

**왜 조용히 실패하나** — `RegisterModule` 은 **레지스트리에 이름이 적혀 있으면 성공**이라
답한다. DLL 이 실제로 로드됐는지는 안 본다. 안 붙으면 한글이 파일을 열 때 **승인
대화상자**를 띄우는데(`C:\dev\assistant\scripts\hwp-to-pdf.ps1:74` 에 이미 적혀 있던 사실),
`finalize_hwpx.py` 가 `Visible = False` 로 창을 감춘 뒤 열기 때문에 **못 보고 못 누르는
대화상자 앞에서 영영 기다린다.** 파일 크기와 무관했던 것이 이 설명과 정확히 맞는다.

**고치는 법**

```
taskkill /F /IM Hwp.exe
python -c "from pyhwpx import Hwp; Hwp.register_regedit()"
reg query "HKCU\Software\HNC\HwpAutomation\Modules" /v FilePathCheckerModule
```

실측: 900초를 넘겨 멈추던 열기가 **0.2초**로 끝났다.

**paperwork 에서 함께 배운 것 둘**

- 거기 19곳이 전부 `Open(경로, "HWPX", "")` 로 **형식을 못박는다.** 이 스킬은 `Open(path, "", "")`
  이다. `""` 로도 돌던 실측이 있어 단독 원인으로 단정하지는 않았지만, 실제로 돌던 쪽에
  맞추는 편이 안전하다.
- *"다른 한글 인스턴스가 떠 있으면 `PageCount` 가 1로 나오는 등 엉뚱한 값이 온다"* —
  재기 전에 `taskkill /F /IM Hwp.exe` 를 먼저 한다.

**★★ 재저장 뒤에는 내용이 남았는지 센다.** paperwork 메모리에 *"보안 모듈 미등록 환경에서
문서 일부만 로드해 내용이 잘린다(표 20개 중 5개만 저장)"* 는 사고 기록이 있다.
`section0.xml` 의 `<hp:tbl` · `<hp:pic` 수와 `BinData/` 파일 수를 재저장 전후로 견준다.

#### ★★★ 재저장이 안 끝나면 **작은 파일로 먼저 재 볼 것** (2026-09-02 신설)

`hancom_resave` 가 `hwp.Open()` 에서 **영영 안 끝나는** 일이 있다. 그때 «문서가 무거워서»로
읽고 그림을 줄이는 데 시간을 쓰기 쉬운데, **크기와 상관없는 경우가 있다.**

실측(tattoo-da 결과보고서) — 9MB·그림 46장 짜리가 900초를 넘겨 멈췄다. 그림을 줄여 4MB 로
만들어도 같았고, **1.4MB 짜리 다른 hwpx 도 똑같이 멈췄다**(180초). `RegisterModule` 은
성공했으므로 파일 경로 보안 모듈 문제도 아니다. 한글이 **안 보이는 창에 확인 대화상자를
띄우고 기다리는 것**으로 의심된다.

**가르는 법 — 작은 파일 하나로 30초면 끝난다:**

```python
import win32com.client
hwp = win32com.client.Dispatch("HWPFrame.HwpObject")
hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
print(hwp.Open(r"작은파일.hwpx", "HWPX", "forceopen:true"))  # 여기서 멈추면 환경 문제다
```

- **작은 파일도 멈춘다** → 환경 문제다. 재저장을 **시간 상한을 걸어 건너뛰고**,
  「사람이 한글에서 한 번 열어 저장해 주십시오」를 **보고에 적는다.** 조용히 넘기지 않는다.
- **작은 파일은 되는데 큰 것만 멈춘다** → 그때가 그림을 줄일 자리다.

★ `subprocess.run(..., timeout=…)` 으로 상한을 걸 것. 상한이 없으면 «도는 중»과
«멈춤»이 구별되지 않아 한 번에 15분씩 날아간다.

※ **워크플로우 J(`fill`/`replace`)로 만든 것은 이 단계가 필요 없다** — 한컴이 저장한
  원본을 베이스로 하므로 캐시가 이미 들어 있다. 조립형(A·D)에만 해당한다.

## 탭·형광펜이 사라질 때 (fill_hwpx · 2026-10-20)

**증상**: `fill_hwpx.py replace` 로 한 글자만 바꿨는데 같은 줄의 탭 간격이 사라져 글자가 붙는다.
`check --strict` · `validate` 는 통과한다 — PDF 로 찍어야 보인다.
실측: 충남대 RISE 동의서에서 「□동의함.<탭>□동의하지 않음.」 → 「■동의함.□동의하지 않음.」,
「성    명 : <탭×4>(인 또는 서명)」 → 「성    명 : 이호섭(인 또는 서명)」.

**원인**: 한 `<hp:t>` 안에는 글자 사이에 `<hp:tab/>` · `<hp:markpenBegin/>` · `<hp:nbSpace/>` 같은 요소가 낀다.
옛 `TNode` 는 이 요소를 뺀 글자만 들고 있다가 쓸 때 `<hp:t>` 내용을 통째로 그 글자로 덮었다.

**지금 규칙** (`scripts/fill_hwpx.py` — 글자를 쓰는 길은 둘뿐이다):
- **고쳐 쓰기 = `edit_range`** (replace · 체크박스 · 괄호 빈칸 · 인라인 라벨 · `TNode.text =`):
  문단(셀)의 `<hp:t>` 들을 글자와 요소가 한 줄로 늘어선 목록으로 펴서 한 번에 고치고 노드로 되돌린다.
  run 이 몇 조각이든 판단은 한 번이다(노드마다 따로 판단하다 교차검증 라운드 2·3 에서 연달아 어긋나 방식을 바꿨다).
  - 앞뒤 공통 글자를 빼고 실제로 바뀐 구간만 본다. 그 구간 **밖** 요소는 제자리.
  - 구간 **안**(첫·끝 바뀐 글자 사이) 요소는 버리지 않고 새 글자 뒤로 옮기며 `inline_warnings` 에 적는다(요소만 든 run 도).
  - 순수 덧붙임은 **맞춘 문구에 붙인다** — 문구 끝에 덧붙이면 요소 **앞**, 문구 맨 앞이면 요소 **뒤**.
    빈 문구가 문단 끝에 맞으면(인라인 라벨 「성명:<탭>」 의 빈 값) 끝 요소들 **뒤**.
  - 새 글자는 첫 바뀐 글자(덧붙임이면 붙는 글자)의 run 이 갖는다 — 그 run 의 글자 모양을 따른다.
  - 셀 패턴 채우기(체크박스 · 괄호 빈칸 · 어노테이션 `(한자:  )`)는 **정규식이 일치한 자리를 그대로** 받아
    (`fill_in_cell_patterns` 의 단계별 고칠 자리 → `apply_pattern_edits`) 일치마다 오른쪽부터 고친다.
    전후 글자를 견줘 자리를 다시 추정하면 틀렸다 — 셀 전체를 한 덩어리로 보면 「□AI □SW」 다중 선택의 사이 글자가 다른 문단으로 옮겨졌고(라운드 4),
    difflib 로 덩어리를 나누면 값 안의 공백이 빈칸 공백과 맞물려 「2026. 10. 20」 이 run 둘로 갈렸다(라운드 5).
- **새 내용으로 갈기 = `set_content`** (셀 값 채우기 · add-row · add-para 의 복제): 원래 글자와 그 안의 요소를 함께 버린다
  (한글에서 범위를 잡고 새로 쓰는 것과 같다). 「1.<탭>사업 개요」 를 복제해 「2. 추진 일정」 을 넣어도 탭이 끝에 남지 않는다.
  탭만 든 `<hp:t>` 를 비울 때처럼 **글자가 그대로여도** 요소를 버렸으면 다시 쓴다(`Registry.changed()` 가 `tags_dirty` 도 본다).

**알려진 한계**: 고친 글자 **안쪽**의, 정확히 요소가 있는 자리에 글자를 덧붙이면 글자를 요소 앞에 넣고 경고는 내지 않는다(요소는 남는다).

시험: `tests/test_fill_inline_tags.py` (고치기 전 코드에서 실패하는 것을 확인했다).
