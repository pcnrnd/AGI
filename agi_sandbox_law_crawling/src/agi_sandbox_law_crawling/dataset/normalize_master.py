from __future__ import annotations

"""
샌드박스 데이터 정규화 + 통합 마스터 CSV 생성.

원본 노트북:
- notebooks/30_dataset/crawler.ipynb
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from agi_sandbox_law_crawling._common import build_logger

log = build_logger("agi.dataset.normalize")


COMMON_COLS = [
    "index",  # 행 인덱스(숫자)
    "sandbox_type",  # ICT / REG_ZONE / FIN / IND_LAW / IND_CASE
    "category",  # 구분/제도/분류
    "title",  # 사례명/서비스명/사업명/제목
    "main_content",  # 서비스 내용/현황/주요내용
    "regulatory_issue",  # 규제 내용/현행 규제
    "regulatory_relief",  # 특례·허용·규제개정현황
    "conditions",  # 부가조건/주요 부가 조건
    "expected_effect",  # 기대효과
    "achievements",  # 성과/개선결과
]


@dataclass(frozen=True)
class NormalizePaths:
    """입력/출력 경로 모음(상대경로/절대경로 모두 지원)."""

    base_dir: Path

    ict_csv: Path = Path("ICT_규제_샌드박스.csv")
    regzone_csv: Path = Path("규제자유특구.csv")
    fin_csv: Path = Path("금융_샌드박스_사례.csv")
    ind_law_csv: Path = Path("산업융합_샌드박스_법령.csv")
    ind_case_xlsx: Path = Path("산업융합_샌드박스_사례_124_20251024.xlsx")

    out_normalized_ict: Path = Path("normalized_ICT_규제_샌드박스.csv")
    out_normalized_regzone: Path = Path("normalized_규제자유특구.csv")
    out_normalized_fin: Path = Path("normalized_금융_샌드박스_사례.csv")
    out_normalized_ind_law: Path = Path("normalized_산업융합_샌드박스_법령.csv")
    out_normalized_ind_case: Path = Path("normalized_산업융합_샌드박스_사례.csv")

    out_master: Path = Path("sandbox_master_normalized.csv")


def _abs(base: Path, p: Path) -> Path:
    return p if p.is_absolute() else (base / p)


def normalize_ict(paths: NormalizePaths) -> pd.DataFrame:
    """
    ICT_규제_샌드박스.csv → 공통 스키마로 변환
    예상 원본 컬럼:
      - 번호, 구분, 서비스명, 서비스 내용, 규제, 특례 내용, 부가조건, 기대효과, 개선결과
    """
    src = _abs(paths.base_dir, paths.ict_csv)
    df = pd.read_csv(src)

    mapping = {
        "번호": "index",
        "구분": "category",
        "서비스명": "title",
        "서비스 내용": "main_content",
        "규제": "regulatory_issue",
        "특례 내용": "regulatory_relief",
        "부가조건": "conditions",
        "기대효과": "expected_effect",
        "개선결과": "achievements",
    }

    missing = [c for c in mapping.keys() if c not in df.columns]
    if missing:
        raise ValueError(f"ICT 파일에 필요한 컬럼이 없습니다: {missing}")

    out_df = df[list(mapping.keys())].rename(columns=mapping)
    out_df["sandbox_type"] = "ICT"
    out_df = out_df[COMMON_COLS]

    out_path = _abs(paths.base_dir, paths.out_normalized_ict)
    out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out_df


def normalize_regzone(paths: NormalizePaths) -> pd.DataFrame:
    """
    규제자유특구.csv → 공통 스키마로 변환
    예상 원본 컬럼:
      - 대제목, 중제목, 소제목, 현황, 허용
    """
    src = _abs(paths.base_dir, paths.regzone_csv)
    df = pd.read_csv(src)

    df["index"] = range(1, len(df) + 1)

    if {"대제목", "중제목"}.issubset(df.columns):
        category = df["대제목"].astype(str) + " / " + df["중제목"].astype(str)
    elif "대제목" in df.columns:
        category = df["대제목"].astype(str)
    else:
        category = ""

    out_df = pd.DataFrame()
    out_df["index"] = df["index"]
    out_df["sandbox_type"] = "REG_ZONE"
    out_df["category"] = category
    out_df["title"] = df.get("소제목", "")
    out_df["main_content"] = df.get("현황", "")
    out_df["regulatory_issue"] = df.get("규제내용", "")
    out_df["regulatory_relief"] = df.get("허용", "")
    out_df["conditions"] = ""
    out_df["expected_effect"] = ""
    out_df["achievements"] = ""

    out_df = out_df[COMMON_COLS]
    out_path = _abs(paths.base_dir, paths.out_normalized_regzone)
    out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out_df


def normalize_fin(paths: NormalizePaths) -> pd.DataFrame:
    """
    금융_샌드박스_사례.csv → 공통 스키마로 변환
    예상 원본 컬럼:
      - 지정 제도, 서비스명, 서비스 주요 내용, (규제내용/본문 일부), 규제 특례 내용, 주요 부가 조건 내용
    """
    src = _abs(paths.base_dir, paths.fin_csv)
    df = pd.read_csv(src)
    df["index"] = range(1, len(df) + 1)

    out_df = pd.DataFrame()
    out_df["index"] = df["index"]
    out_df["sandbox_type"] = "FIN"
    out_df["category"] = df.get("지정 제도", "")
    out_df["title"] = df.get("서비스명", "")
    out_df["main_content"] = df.get("서비스 주요 내용", "")

    if "규제내용" in df.columns:
        out_df["regulatory_issue"] = df["규제내용"]
    elif "본문 일부" in df.columns:
        out_df["regulatory_issue"] = df["본문 일부"]
    else:
        out_df["regulatory_issue"] = ""

    out_df["regulatory_relief"] = df.get("규제 특례 내용", "")
    out_df["conditions"] = df.get("주요 부가 조건 내용", "")
    out_df["expected_effect"] = ""
    out_df["achievements"] = ""

    out_df = out_df[COMMON_COLS]
    out_path = _abs(paths.base_dir, paths.out_normalized_fin)
    out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out_df


def normalize_ind_law(paths: NormalizePaths) -> pd.DataFrame:
    """
    산업융합_샌드박스_법령.csv → 공통 스키마로 변환
    예상 원본 컬럼:
      - 순번, 국조실분류, 사업명, 규제내용
    """
    src = _abs(paths.base_dir, paths.ind_law_csv)
    df = pd.read_csv(src)

    out_df = pd.DataFrame()
    out_df["index"] = df.get("순번", range(1, len(df) + 1))
    out_df["sandbox_type"] = "IND_LAW"
    out_df["category"] = df.get("국조실분류", "")
    out_df["title"] = df.get("사업명", "")
    out_df["main_content"] = df.get("규제내용", "")
    out_df["regulatory_issue"] = df.get("규제내용", "")
    out_df["regulatory_relief"] = ""
    out_df["conditions"] = ""
    out_df["expected_effect"] = ""
    out_df["achievements"] = ""

    out_df = out_df[COMMON_COLS]
    out_path = _abs(paths.base_dir, paths.out_normalized_ind_law)
    out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out_df


def normalize_ind_case(paths: NormalizePaths) -> pd.DataFrame:
    """
    산업융합_샌드박스_사례_124_20251024.xlsx → 공통 스키마로 변환
    예상 원본 컬럼:
      - 번호, 구분(Category), 제목, 주요내용, 규제내용, 규제개정현황(유사), 기대효과, 주요성과
    """
    src = _abs(paths.base_dir, paths.ind_case_xlsx)
    df = pd.read_excel(src)

    out_df = pd.DataFrame()
    out_df["index"] = df.get("번호", range(1, len(df) + 1))
    out_df["sandbox_type"] = "IND_CASE"

    if "구분(Category)" in df.columns:
        out_df["category"] = df["구분(Category)"]
    elif "구분" in df.columns:
        out_df["category"] = df["구분"]
    else:
        out_df["category"] = ""

    out_df["title"] = df.get("제목", "")
    out_df["main_content"] = df.get("주요내용", "")
    out_df["regulatory_issue"] = df.get("규제내용", "")
    out_df["regulatory_relief"] = df.get("규제개정현황(유사)", "")
    out_df["conditions"] = ""
    out_df["expected_effect"] = df.get("기대효과", "")
    out_df["achievements"] = df.get("주요성과", "")

    out_df = out_df[COMMON_COLS]
    out_path = _abs(paths.base_dir, paths.out_normalized_ind_case)
    out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out_df


def build_master_dataset(
    *,
    base_dir: Path,
    out_master_path: Optional[Path] = None,
) -> Path:
    """
    5개 소스(ICT/REG_ZONE/FIN/IND_LAW/IND_CASE)를 정규화한 뒤 하나로 합칩니다.

    반환값: 생성된 master CSV 경로
    """
    base_dir = Path(base_dir)
    paths = NormalizePaths(base_dir=base_dir)

    dfs = [
        normalize_ict(paths),
        normalize_regzone(paths),
        normalize_fin(paths),
        normalize_ind_law(paths),
        normalize_ind_case(paths),
    ]

    master = pd.concat(dfs, ignore_index=True)
    out_path = out_master_path or _abs(base_dir, paths.out_master)
    master.to_csv(out_path, index=False, encoding="utf-8-sig")
    log.info("통합 마스터 CSV 저장 완료: %s (rows=%s)", out_path, len(master))
    return Path(out_path)

