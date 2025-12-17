from __future__ import annotations

"""
법령 PDF 텍스트 추출 → 조문/항 단위 CSV 변환.

원본 노트북:
- notebooks/20_laws/02_pdf_to_csv/pdf_to_csv.ipynb
"""

import re
from pathlib import Path
from typing import Optional

import pandas as pd
import pdfplumber
from tqdm import tqdm

from agi_sandbox_law_crawling._common import build_logger

log = build_logger("agi.laws.pdf_to_csv")

# "제1장 총칙" 같은 장(章) 패턴
CHAPTER_PATTERN = re.compile(r"^제\s*\d+\s*장\s*.*")

# "제1조(목적)" 같은 조(條) 패턴(조 제목만 있는 줄)
ARTICLE_PATTERN = re.compile(r"^제\s*\d+\s*조(?:\s*\(.*?\))?\s*$")

# ①, ②, ③, ... 항 번호
CIRCLED_DIGITS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
CLAUSE_PATTERN = re.compile(rf"^[{CIRCLED_DIGITS}]\s*")

# "제35조(과징금 처분 등) ① ..." 같이 한 줄에 조 제목과 본문이 붙은 경우
ARTICLE_TITLE_PATTERN = re.compile(r"^제\s*(\d+)\s*조(?:\((.+?)\))?\s*(.*)$")


def extract_text_from_pdf(pdf_path: str) -> str:
    """pdfplumber로 PDF 전체 텍스트를 추출합니다."""
    text_chunks: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text_chunks.append(page.extract_text() or "")
    return "\n".join(text_chunks)


def normalize_lines(text: str, law_name: Optional[str] = None) -> list[str]:
    """
    줄 단위 정리:
    - 전각 공백 제거
    - 공백 트림
    - 헤더/푸터(법제처/국가법령정보센터/페이지번호/법령명 단독 줄) 제거
    """
    lines = text.splitlines()
    norm_lines: list[str] = []
    for line in lines:
        line = line.replace("\u3000", " ").strip()
        if not line:
            continue

        # ----- 헤더/푸터 필터링 -----
        if law_name and line == law_name:
            continue
        if "국가법령정보센터" in line or "법제처" in line:
            continue
        if re.fullmatch(r"\d+", line):
            continue
        # ---------------------------

        norm_lines.append(line)

    return norm_lines


def split_clause_start(line: str):
    """줄 맨 앞에 ①, ②,...가 있으면 (항번호, 본문)으로 분리합니다."""
    line = line.lstrip()
    m = CLAUSE_PATTERN.match(line)
    if not m:
        return None, line
    clause_char = m.group(0).strip()[0]
    rest = CLAUSE_PATTERN.sub("", line).strip()
    return clause_char, rest


def parse_article_title(line: str):
    """
    '제35조(과징금 처분 등) ① ...' 같은 한 줄을
    - article_number: '제35조'
    - article_title:  '과징금 처분 등'
    - body_start:     '① ...' (또는 일반 문장)
    로 분리합니다.
    """
    m = ARTICLE_TITLE_PATTERN.match(line)
    if not m:
        return line.strip(), None, None

    num, title_in_paren, rest = m.groups()
    article_number = f"제{num}조"
    rest = (rest or "").strip()

    if title_in_paren:
        article_title = title_in_paren.strip()
        body_start = rest if rest else None
    else:
        article_title = rest if rest else None
        body_start = None

    return article_number, article_title, body_start


def parse_law_pdf(pdf_path: str, law_name: str) -> pd.DataFrame:
    """
    PDF 1개를 조문/항 단위로 파싱해 DataFrame으로 반환합니다.

    컬럼:
    - law_name, chapter, article_number, article_title, clause_number, text
    """
    raw_text = extract_text_from_pdf(pdf_path)
    lines = normalize_lines(raw_text, law_name=law_name)

    records: list[dict] = []
    current_chapter = None
    current_article_number = None
    current_article_title = None
    current_clause_number = None

    clause_buffer: list[str] = []
    article_head_buffer: list[str] = []

    def flush_clause():
        nonlocal clause_buffer, current_clause_number
        if clause_buffer:
            records.append(
                {
                    "law_name": law_name,
                    "chapter": current_chapter,
                    "article_number": current_article_number,
                    "article_title": current_article_title,
                    "clause_number": current_clause_number,
                    "text": " ".join(clause_buffer).strip(),
                }
            )
        clause_buffer = []

    def flush_article_head():
        nonlocal article_head_buffer
        if article_head_buffer:
            records.append(
                {
                    "law_name": law_name,
                    "chapter": current_chapter,
                    "article_number": current_article_number,
                    "article_title": current_article_title,
                    "clause_number": None,
                    "text": " ".join(article_head_buffer).strip(),
                }
            )
        article_head_buffer = []

    prev_article_no: Optional[int] = None  # 조 번호 추적(오탐 방지)

    for line in lines:
        # -------- 장(章) --------
        if CHAPTER_PATTERN.match(line):
            flush_clause()
            flush_article_head()
            current_chapter = line.strip()
            continue

        # -------- 조(條) + 오탐 보정 --------
        m = ARTICLE_PATTERN.match(line)
        is_article_line = False

        if m:
            try:
                num_now = int(re.search(r"\d+", line).group())
            except Exception:
                num_now = None

            # 이전 조 번호 대비 너무 큰 점프면(예: "제21조제2항" 같은 본문) 조 제목으로 오인 가능
            if num_now is not None and prev_article_no is not None and abs(num_now - prev_article_no) > 5:
                is_article_line = False
            else:
                is_article_line = True

        if is_article_line:
            flush_clause()
            flush_article_head()

            article_number, article_title, body_start = parse_article_title(line)
            current_article_number = article_number
            current_article_title = article_title
            current_clause_number = None

            try:
                prev_article_no = int(re.search(r"\d+", article_number).group())
            except Exception:
                pass

            # 같은 줄에 본문이 붙어 있는 경우 처리
            if body_start:
                clause_no, rest = split_clause_start(body_start)
                if clause_no:
                    current_clause_number = clause_no
                    clause_buffer = [rest] if rest else []
                else:
                    article_head_buffer.append(body_start)
            continue

        # -------- 항(①, ②, …) --------
        clause_no, rest_line = split_clause_start(line)
        if clause_no:
            flush_clause()
            current_clause_number = clause_no
            clause_buffer = [rest_line] if rest_line else []
            continue

        # -------- 일반 본문 --------
        if current_article_number is None:
            continue

        if current_clause_number:
            clause_buffer.append(line)
        else:
            article_head_buffer.append(line)

    flush_clause()
    flush_article_head()

    return pd.DataFrame(
        records,
        columns=["law_name", "chapter", "article_number", "article_title", "clause_number", "text"],
    )


def process_all_pdfs(
    *,
    input_dir: Path,
    output_dir: Path,
    merge_to_one: bool = False,
    merged_filename: str = "ALL_LAWS.csv",
) -> None:
    """
    input_dir 아래 모든 PDF를 처리합니다.
    - 각 PDF → <파일명>.csv
    - (옵션) 전부 합친 CSV 생성
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = [p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"]
    log.info("PDF 개수=%s, input=%s, output=%s", len(pdf_files), input_dir, output_dir)

    if not pdf_files:
        raise FileNotFoundError(f"PDF를 찾지 못했습니다: {input_dir}")

    all_dfs: list[pd.DataFrame] = []
    for pdf_path in tqdm(pdf_files, desc="Processing PDF → CSV"):
        law_name = pdf_path.stem
        try:
            df = parse_law_pdf(str(pdf_path), law_name)
        except Exception as e:
            log.warning("PDF 처리 실패: %s (%s)", pdf_path.name, e)
            continue

        out_csv = output_dir / f"{pdf_path.stem}.csv"
        df.to_csv(out_csv, index=False, encoding="utf-8-sig")
        all_dfs.append(df)

    if merge_to_one and all_dfs:
        merged_df = pd.concat(all_dfs, ignore_index=True)
        merged_path = output_dir / merged_filename
        merged_df.to_csv(merged_path, index=False, encoding="utf-8-sig")
        log.info("병합 CSV 저장: %s", merged_path)

