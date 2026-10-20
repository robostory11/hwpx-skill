#!/usr/bin/env python3
"""layout_guard 의 「그림이 일부만 그려진다」 판정을 한글이 실제로 찍은 결과와 맞춘다.

2026-10-20 한글로 PDF 를 찍어 가른 세 경우(충남대 RISE 서류의 신분증 그림):
  A. 한글이 그림 넣기로 넣은 그대로 — imgClip = imgDim = 120000×75300, orgSz = 36284×22677 → 온전히 찍힘
  B. imgClip 을 imgDim 의 절반으로 → 왼쪽 위만 찍힘
  C. imgClip = imgDim = orgSz = 표시 크기(hwpx_helpers 가 만드는 모양) → 온전히 찍힘
옛 판정은 imgClip 을 orgSz 와 견줘 A 를 잡았다(거짓 경보).

사용법: python tests/test_layout_guard_imgclip.py   (종료 코드 0 = 전체 통과)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import layout_guard as L  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def pic(org, clip, dim):
    parts = [f'<hp:pic id="1"><hp:orgSz width="{org[0]}" height="{org[1]}"/>']
    parts.append(f'<hp:imgClip left="0" right="{clip[0]}" top="0" bottom="{clip[1]}"/>')
    if dim:
        parts.append(f'<hp:imgDim dimwidth="{dim[0]}" dimheight="{dim[1]}"/>')
    parts.append("</hp:pic>")
    return "".join(parts)


print("[A] 한글이 넣은 그림 — clip = imgDim ≠ orgSz → 통과")
check("잡지 않는다", L.picture_clip_detail(pic((36284, 22677), (120000, 75300), (120000, 75300))) is None)

print("[B] clip 이 imgDim 의 절반 → 잡는다")
d = L.picture_clip_detail(pic((36284, 22677), (60000, 37650), (120000, 75300)))
check("잡는다", d is not None and "imgDim" in d, d)

print("[C] helpers 모양 — clip = imgDim = orgSz → 통과")
check("잡지 않는다", L.picture_clip_detail(pic((36284, 22677), (36284, 22677), (36284, 22677))) is None)

print("[D] imgDim 이 없는 옛 문서 — orgSz 와 견준다")
check("같으면 통과", L.picture_clip_detail(pic((36284, 22677), (36284, 22677), None)) is None)
d = L.picture_clip_detail(pic((36284, 22677), (120000, 75300), None))
check("다르면 잡는다", d is not None and "orgSz" in d, d)

print(f"\n결과: {PASS} 통과 / {FAIL} 실패")
sys.exit(1 if FAIL else 0)
