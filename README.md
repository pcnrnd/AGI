## Solution Overview
- 이 폴더는 **샌드박스/법령 크롤링 + 전처리 + 통합(정규화)** 작업을 “노트북 중심”으로 운영하기 위한 프로젝트 루트입니다.
- 실행은 `notebooks/` 아래 모듈별 노트북을 순서대로 수행하는 방식입니다.
- 각 노트북의 세부 설명/주의사항은 동일 폴더의 `*_README.md`(있는 경우)와 노트북 상단 설명 셀을 기준으로 합니다.
- 통합 및 샌드박스/법령 매핑을 진행하여 Corpus 데이터 1523 건을 구축하였습니다.
- 챗봇 PoC 파일은 추후 업로드 예정입니다.
- 
## Project Structure
```
AGI/
  main                      # (필요 시) 실행 진입점/메모용 파일
  notebooks/
    sandbox/
      ict/                  # ICT 규제샌드박스
      fintech/              # Fintech Sandbox
      rfz/                  # 규제자유특구(RFZ)
    laws/
      01_download_pdf/      # 법령 PDF 다운로드
      02_pdf_to_csv/        # PDF → CSV(조문/항 등 분해)
    dataset/                # 정규화/통합(마스터 데이터 생성)
    utils/                  # docx/html 등 유틸 전처리
```

## Notebooks (모듈별 구성)
### Sandbox (샌드박스)
- **ICT 규제샌드박스**
  - `notebooks/sandbox/ict/sandbox_selective_crawler_with_improvement_separate.ipynb`
- **Fintech Sandbox**
  - `notebooks/sandbox/fintech/fintech_sandbox_crawler_v5_full_20251028_055640.ipynb`
- **RFZ(규제자유특구)**
  - `notebooks/sandbox/rfz/rfz_crawler_v4.ipynb` (menuno=206)
  - `notebooks/sandbox/rfz/rfz_menuno149_crawler_v17_strip_leading_index_range.ipynb` (menuno=149)

### Laws (법령)
- **법령 PDF 다운로드**
  - `notebooks/laws/01_download_pdf/crawling.ipynb`
- **PDF → CSV 변환**
  - `notebooks/laws/02_pdf_to_csv/pdf_to_csv.ipynb`

### Dataset (정규화/통합)
- **샌드박스 정규화 + 마스터 CSV 생성**
  - `notebooks/dataset/crawler.ipynb`

### Utils (유틸)
- `notebooks/utils/docx_to_csv.ipynb`
- `notebooks/utils/html_parser.ipynb`

## How to Run
### 1) 환경 준비
- **Python/Conda**: 노트북에서 사용 중인 환경(예: Anaconda/conda env)을 사용하세요.
- **브라우저 자동화**: Selenium 기반 노트북은 Chrome/ChromeDriver 설정이 필요합니다.
  - 노트북 내 “환경설정 셀(경로/옵션)”에서 다운로드 폴더, 드라이버 경로, headless 여부 등을 조정하세요.

### 2) 권장 실행 순서
- **샌드박스 수집** → **법령 PDF 다운로드** → **PDF→CSV 변환** → **정규화/통합**
  - (수집된 파일이 어느 폴더에 저장되는지는 각 노트북의 경로 설정에 따릅니다.)

## Tests
- 현재는 노트북 기반 운영이라 자동화 테스트는 포함하지 않았습니다.
- 추후 크롤러/파서를 `src/` 파이썬 모듈로 분리하면 `pytest` 기반 단위테스트를 추가하는 구성이 적합합니다.

## Trade-offs & Alternatives
- **노트북 중심**: 빠르게 실험/검증 가능하지만, 배치 실행/테스트/재사용이 어렵습니다.
- **대안**: 노트북을 “실행 래퍼”로 최소화하고, 핵심 로직은 파이썬 모듈로 분리해 운영하는 방식을 권장합니다.

# AGI 법령 다운로드 프로젝트

법제처 사이트에서 샌드박스 관련 법령을 자동으로 검색‧다운로드하는 코드를
모듈화한 Python 프로젝트입니다. 원래 단일 주피터 노트북이던 스크립트를
다운로드 로직, 설정, 워크플로우, CLI 레이어로 분리해 재사용성과 테스트
가능성을 높였습니다.

## 폴더 구조

```
AGI/
├── agi_downloader/           # 패키지 소스
│   ├── __init__.py
│   ├── config.py             # 환경설정/경로 관리
│   ├── download_modes.py     # PDF/WORD 포맷 정의
│   ├── driver_factory.py     # Chrome WebDriver 생성
│   ├── file_utils.py         # 파일명/스냅샷 유틸
│   ├── law_loader.py         # 엑셀 로더
│   ├── service.py            # 핵심 다운로드 서비스
│   └── workflows.py          # 일괄/재시도 워크플로우
├── scripts/
│   ├── download_laws.py      # CLI: 전체 다운로드
│   └── retry_missing.py      # CLI: 누락분 재다운로드
├── tests/
│   └── test_helpers.py       # 기본 유닛 테스트
├── requirements.txt
└── README.md
```

## 의존성 설치

```powershell
cd AGI
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 환경 변수 (선택)

| 변수명 | 설명 | 기본값 |
| --- | --- | --- |
| `AGI_WORKSPACE_ROOT` | 데이터 루트 경로 | `AGI` 상위 디렉터리 |
| `AGI_LAW_LIST` | 법령명 엑셀 경로 | `샌드박스_법령명_163개_리스트.xlsx` |
| `AGI_LAW_COLUMN` | 엑셀 컬럼명 | `정식 법령명` |
| `AGI_DOWNLOAD_DIR` | 저장 폴더 | `law_pdf_downloads` |
| `AGI_BASE_SEARCH_URL` | 법제처 검색 URL | notebook 기본값 |
| `AGI_HEADLESS` | `true/false` | `false` |
| `AGI_MAX_DOWNLOADS` | 앞 N건만 처리 | 비활성 |
| `AGI_DOWNLOAD_TIMEOUT_SEC` | 파일 완료 대기 | `180` |
| `AGI_MODAL_TIMEOUT_SEC` | 모달 대기 | `15` |
| `AGI_PAGE_LOAD_TIMEOUT_SEC` | 페이지 로딩 | `60` |

## 사용법

### 전체 다운로드

```powershell
cd AGI
python scripts/download_laws.py --format pdf
# WORD가 필요하면 --format word
# 테스트용으로 앞 5건만: --limit 5
```

### 누락 파일만 재다운로드

```powershell
cd AGI
python scripts/retry_missing.py --format pdf
```

CLI 옵션(`--law-list`, `--column`, `--download-dir`, `--headless/--no-headless`)으로
상황별 경로를 즉시 덮어쓸 수 있습니다.

## 테스트

```powershell
cd AGI
pytest
```

`tests/test_helpers.py`는 파일명 정규화 및 엑셀 로더 로직을 검증하며, 추후
다운로드 서비스에 대한 모킹 기반 테스트를 추가할 수 있도록 구조를 분리해
두었습니다.
