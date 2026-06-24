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

## "python-hwpx 에러"

| 원인 | 해결 |
|------|------|
| HwpxDocument.open() 실패 | XML-first 접근 또는 ZIP-level 치환 사용 |
| ObjectFinder 에러 | `pip install python-hwpx --break-system-packages` |
