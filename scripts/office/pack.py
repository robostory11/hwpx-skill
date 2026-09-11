#!/usr/bin/env python3
"""Pack a directory back into an HWPX (ZIP) file.

The mimetype file is stored as the first entry with ZIP_STORED (no compression),
per OPC packaging conventions.

Usage:
    python pack.py input_dir/ output.hwpx
"""

import stat
import argparse
import os
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile


def pack(input_dir: str, hwpx_path: str) -> None:
    """Create HWPX archive from a directory."""

    root = Path(input_dir)
    if not root.is_dir():  # 부재판정-허용: 없으면 바로 아래에서 FileNotFoundError 로 멈춘다
        raise FileNotFoundError(f"Directory not found: {input_dir}")

    mimetype_file = root / "mimetype"
    if not mimetype_file.is_file():  # 부재판정-허용: 없으면 바로 아래에서 FileNotFoundError 로 멈춘다
        raise FileNotFoundError(
            f"Missing required 'mimetype' file in {input_dir}"
        )

    # ★★ 2026-09-11: 여기 `if p.is_file()` 이 있었다. 못 읽으면 조용히 `False` 가 되어
    #   **그 파일이 ZIP 에서 빠진 채** 아무 검증 없이 묶인다. 아래에서 줄어든 개수를
    #   찍을 뿐인데 **사람은 원래 개수를 모른다** — 이미지나 section1.xml 이 빠진 문서가
    #   열리기는 하면서 내용만 없는 채로 나간다.
    #   ★ 여기 `root` 는 **사용자가 명령줄로 준 폴더**다(build_hwpx 의 임시 폴더와 다르다).
    #   → `stat()` 을 직접 불러 **못 읽으면 그 자리에서 시끄럽게 죽인다.**
    #     폴더인지는 `S_ISDIR` 로 가른다(그것은 정상적인 건너뛰기다).
    all_files = []
    for p in root.rglob("*"):
        try:
            st = p.stat()
        except OSError as e:
            raise OSError(
                f"Cannot stat {p} while packing {input_dir}: {e}. "
                f"Refusing to pack a partial archive."
            ) from e
        # ★ `S_ISDIR` 로 「폴더면 건너뛴다」가 아니라 **`S_ISREG` 로 「정규 파일만 담는다」**이다
        #   (2026-09-11 라운드 1 · codex). 앞엣것은 **범위를 넓힌다** — 원래 `is_file()` 은
        #   정규 파일에만 참이라 FIFO·소켓·장치 파일을 걸렀는데, 「폴더가 아니면 담는다」로
        #   바꾸면 그것들이 들어와 **ZIP 을 만들다 죽거나 멈춘다.**
        #   ※ `stat()` 은 링크를 따라가므로 정규 파일을 가리키는 심볼릭 링크는 그대로 담긴다.
        if not stat.S_ISREG(st.st_mode):
            continue
        all_files.append(p.relative_to(root).as_posix())
    all_files.sort()

    with ZipFile(hwpx_path, "w", ZIP_DEFLATED) as zf:
        # mimetype MUST be the first entry, stored without compression
        zf.write(mimetype_file, "mimetype", compress_type=ZIP_STORED)

        for rel_path in all_files:
            if rel_path == "mimetype":
                continue  # Already written
            full_path = root / rel_path
            zf.write(full_path, rel_path, compress_type=ZIP_DEFLATED)

    count = len(all_files)
    print(f"Packed: {input_dir} -> {hwpx_path}")
    print(f"  Files: {count} entries (mimetype first, ZIP_STORED)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pack a directory into an HWPX (ZIP) file"
    )
    parser.add_argument("input", help="Input directory path")
    parser.add_argument("output", help="Output .hwpx file path")
    args = parser.parse_args()

    if not os.path.isdir(args.input):   # 부재판정-허용: 못 읽으면 오류를 찍고 exit 1 로 멈춘다 — 조용하지 않다
        print(f"Error: Directory not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    pack(args.input, args.output)


if __name__ == "__main__":
    main()
