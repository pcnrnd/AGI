## Solution Overview
- 이 폴더(`.../AGI/데이터/AGI/agi_sandbox_law_crawling`)는 **샌드박스/법령 크롤링 노트북을 목적별로 정리**하기 위한 프로젝트 루트입니다.
- 노트북 파일은 **사용자가 직접 `notebooks/` 아래에 배치**하는 것을 기본 운영 방식으로 합니다.
- 데이터/산출물 폴더를 표준화해서, 크롤링 → 전처리 → 통합데이터 생성 흐름을 재현 가능하게 만듭니다.

## Project Structure (권장)
```
agi_sandbox_law_crawling/
  notebooks/
    10_sandbox/
      ict/            # sandbox.or.kr (NIPA ICT 규제샌드박스)
      fintech/        # Fintech Sandbox 기업소개 크롤링
      rfz/            # 규제자유특구(RFZ) 크롤링
    20_laws/
      01_download_pdf/ # 법제처/국가법령정보센터에서 PDF 내려받기
      02_pdf_to_csv/   # PDF 텍스트 추출 → CSV 변환
    30_dataset/        # 샌드박스 데이터 정규화/통합(마스터 CSV 생성)
    90_utils/          # docx/html 등 유틸성 전처리
  data/
    input/             # 엑셀 등 입력(리스트/매핑)
    raw/               # 원천(다운로드) 결과 저장 권장
    processed/         # 전처리/정규화 결과
  outputs/             # 실행 산출물(csv/jsonl/log 등)
  scripts/             # (선택) 배치 자동화 스크립트
  README.md
```

## Notebook Placement (현재 파일 기준 권장 위치)
현재 `agi_sandbox_law_crawling` 루트에 있는 노트북을 아래 경로로 옮겨두면 됩니다.

- **샌드박스**
  - `sandbox_selective_crawler_with_improvement_separate.ipynb` → `notebooks/10_sandbox/ict/`
  - `fintech_sandbox_crawler_v5_full_20251028_055640.ipynb` → `notebooks/10_sandbox/fintech/`
  - `rfz_crawler_v4.ipynb` → `notebooks/10_sandbox/rfz/`
  - `rfz_menuno149_crawler_v17_strip_leading_index_range.ipynb` → `notebooks/10_sandbox/rfz/`
- **법령**
  - `crawling.ipynb` → `notebooks/20_laws/01_download_pdf/`  (법령 PDF 다운로드)
  - `pdf_to_csv.ipynb` → `notebooks/20_laws/02_pdf_to_csv/`  (PDF→CSV)
- **통합 데이터셋**
  - `crawler.ipynb` → `notebooks/30_dataset/`               (정규화 + 마스터 CSV 생성)
- **유틸**
  - `docx_to_csv.ipynb` → `notebooks/90_utils/`
  - `html_parser.ipynb` → `notebooks/90_utils/`

## How to Run (권장 실행 순서)
- **샌드박스 수집**
  - `notebooks/10_sandbox/ict/` → ICT 규제샌드박스 수집/정제
  - `notebooks/10_sandbox/fintech/` → 금융(핀테크) 샌드박스 기업소개 수집
  - `notebooks/10_sandbox/rfz/` → 규제자유특구(RFZ) 수집
- **법령 수집/변환**
  - `notebooks/20_laws/01_download_pdf/` → 법령 PDF 다운로드
  - `notebooks/20_laws/02_pdf_to_csv/` → PDF 텍스트 추출 후 CSV화
- **통합 데이터 생성**
  - `notebooks/30_dataset/` → 여러 샌드박스 데이터 정규화/통합

## Output Conventions (권장)
- **원천 다운로드 결과**: `data/raw/`
- **전처리/정규화 결과**: `data/processed/`
- **최종 산출물(csv/jsonl/log 등)**: `outputs/`

## Tests
노트북 중심 구성이라 별도 자동화 테스트는 포함하지 않았습니다.

## Trade-offs & Alternatives
- 장기적으로는 크롤러/파서를 `src/`로 분리하고 `pytest`를 붙이는 구성이 유지보수에 유리합니다.

