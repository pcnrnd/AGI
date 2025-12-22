"""
법제처 사이트에서 법령 문서(PDF/DOCX)를 자동 다운로드하는 모듈

샌드박스 법령 리스트를 읽어 법제처 사이트에서 PDF 또는 DOCX 파일을 일괄 다운로드합니다.
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Set
import logging
import time
import pandas as pd
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class LawDocumentDownloader:
    """
    법제처 사이트에서 법령 문서를 자동 다운로드하는 클래스
    
    엑셀 파일에서 법령명 리스트를 읽어 법제처 사이트에 접속하여
    PDF 또는 DOCX 형식으로 문서를 다운로드합니다.
    """
    
    # 기본 설정값
    DEFAULT_BASE_SEARCH_URL = "https://www.law.go.kr/lsSc.do?menuId=1&subMenuId=15&tabMenuId=81&query="
    DEFAULT_SAVE_BUTTON_XPATH = "/html/body/form[2]/div[1]/div[2]/div[1]/div[3]/a[5]"
    DEFAULT_PDF_RADIO_XPATH = "/html/body/div[45]/div[2]/div/div/form/fieldset/div[3]/div[1]/div[3]"
    DEFAULT_DOC_RADIO_XPATH = "/html/body/div[45]/div[2]/div/div/form/fieldset/div[3]/div[1]/div[4]"
    DEFAULT_DOWNLOAD_BUTTON_XPATH = "/html/body/div[45]/div[2]/div/div/form/fieldset/div[3]/div[2]/a[1]"
    DEFAULT_DOWNLOAD_TIMEOUT_SEC = 180
    DEFAULT_MODAL_TIMEOUT_SEC = 15
    DEFAULT_PAGE_LOAD_TIMEOUT = 60
    
    def __init__(
        self,
        base_dir: Path,
        list_file: Path,
        download_dir: Optional[Path] = None,
        column_name: str = "정식 법령명",
        file_format: str = "docx",  # "pdf" or "docx"
        base_search_url: Optional[str] = None,
        headless: bool = False,
        max_downloads: Optional[int] = None,
        download_timeout_sec: int = DEFAULT_DOWNLOAD_TIMEOUT_SEC,
        modal_timeout_sec: int = DEFAULT_MODAL_TIMEOUT_SEC,
        save_button_xpath: Optional[str] = None,
        pdf_radio_xpath: Optional[str] = None,
        doc_radio_xpath: Optional[str] = None,
        download_button_xpath: Optional[str] = None,
    ):
        """
        LawDocumentDownloader 초기화
        
        Args:
            base_dir: 기본 작업 디렉토리 경로
            list_file: 법령명 리스트가 포함된 엑셀 파일 경로
            download_dir: 다운로드 폴더 경로 (None이면 base_dir/law_doc_downloads)
            column_name: 엑셀 파일 내 법령명 컬럼명
            file_format: 다운로드할 파일 형식 ("pdf" 또는 "docx")
            base_search_url: 법제처 검색 URL (기본값 사용 시 None)
            headless: 헤드리스 모드 사용 여부
            max_downloads: 최대 다운로드 개수 (None이면 전체)
            download_timeout_sec: 다운로드 완료 대기 시간(초)
            modal_timeout_sec: 모달 표시 대기 시간(초)
            save_button_xpath: 저장 버튼 XPath (기본값 사용 시 None)
            pdf_radio_xpath: PDF 라디오 버튼 XPath (기본값 사용 시 None)
            doc_radio_xpath: DOCX 라디오 버튼 XPath (기본값 사용 시 None)
            download_button_xpath: 다운로드 버튼 XPath (기본값 사용 시 None)
        """
        self.base_dir = Path(base_dir)
        self.list_file = Path(list_file)
        self.download_dir = Path(download_dir) if download_dir else self.base_dir / "law_doc_downloads"
        self.column_name = column_name
        self.file_format = file_format.lower()
        self.base_search_url = base_search_url or self.DEFAULT_BASE_SEARCH_URL
        self.headless = headless
        self.max_downloads = max_downloads
        self.download_timeout_sec = download_timeout_sec
        self.modal_timeout_sec = modal_timeout_sec
        
        # XPath 설정
        self.save_button_xpath = save_button_xpath or self.DEFAULT_SAVE_BUTTON_XPATH
        self.pdf_radio_xpath = pdf_radio_xpath or self.DEFAULT_PDF_RADIO_XPATH
        self.doc_radio_xpath = doc_radio_xpath or self.DEFAULT_DOC_RADIO_XPATH
        self.download_button_xpath = download_button_xpath or self.DEFAULT_DOWNLOAD_BUTTON_XPATH
        
        # 파일 형식 검증
        if self.file_format not in ["pdf", "docx"]:
            raise ValueError(f"지원하지 않는 파일 형식입니다: {file_format}. 'pdf' 또는 'docx'를 사용하세요.")
        
        # 다운로드 디렉토리 생성
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"LawDocumentDownloader 초기화 완료: 형식={file_format}, 다운로드 폴더={self.download_dir}")
    
    def _sanitize_filename(self, raw_name: str) -> str:
        """
        파일 시스템에서 사용할 수 있도록 특수문자를 제거합니다.
        
        Args:
            raw_name: 원본 파일명
            
        Returns:
            정리된 파일명
        """
        invalid_chars = '<>:"/\\|?*'
        cleaned = ''.join(ch for ch in raw_name if ch not in invalid_chars).strip()
        return cleaned or "법령"
    
    def _load_law_names(self) -> List[str]:
        """
        엑셀 파일에서 법령명 목록을 읽어 문자열 리스트로 반환합니다.
        
        Returns:
            법령명 리스트
            
        Raises:
            FileNotFoundError: 엑셀 파일이 존재하지 않을 경우
            ValueError: 컬럼이 없거나 법령명이 비어있을 경우
        """
        if not self.list_file.exists():
            raise FileNotFoundError(f"엑셀 파일을 찾을 수 없습니다: {self.list_file}")
        
        df = pd.read_excel(self.list_file)
        
        if self.column_name not in df.columns:
            raise ValueError(
                f"엑셀에 '{self.column_name}' 컬럼이 없습니다. "
                f"실제 컬럼명: {list(df.columns)}"
            )
        
        names = (
            df[self.column_name]
            .dropna()
            .astype(str)
            .str.strip()
        )
        result = [name for name in names if name]
        
        if not result:
            raise ValueError("다운로드할 법령명이 비어 있습니다.")
        
        logger.info(f"법령명 {len(result)}개 로드 완료")
        return result
    
    def _build_driver(self) -> webdriver.Chrome:
        """
        Selenium WebDriver를 생성하고 설정합니다.
        
        Returns:
            설정된 Chrome WebDriver 인스턴스
        """
        options = Options()
        
        # 다운로드 경로 설정
        prefs = {
            "download.default_directory": str(self.download_dir.resolve()),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        }
        options.add_experimental_option("prefs", prefs)
        
        # 헤드리스 모드 설정
        if self.headless:
            options.add_argument("--headless=new")
        
        # WebDriver 생성 (webdriver-manager가 자동으로 관리)
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(self.DEFAULT_PAGE_LOAD_TIMEOUT)
        
        logger.debug("WebDriver 생성 완료")
        return driver
    
    def _wait_for_new_file(self, before_files: Set[Path]) -> Path:
        """
        다운로드 폴더에서 새롭게 생성된 파일이 나타날 때까지 대기합니다.
        
        Args:
            before_files: 다운로드 전 파일 목록
            
        Returns:
            새로 생성된 파일 경로
            
        Raises:
            TimeoutException: 타임아웃 내에 파일이 생성되지 않을 경우
        """
        deadline = time.time() + self.download_timeout_sec
        
        while time.time() < deadline:
            current_files = {
                file_path.resolve()
                for file_path in self.download_dir.glob('*')
                if file_path.is_file() and not file_path.name.endswith('.crdownload')
            }
            diff = current_files - before_files
            
            if diff:
                # 가장 최근에 수정된 파일 반환
                return max(diff, key=lambda p: p.stat().st_mtime)
            
            time.sleep(1)
        
        raise TimeoutException("다운로드 완료 파일을 찾지 못했습니다.")
    
    def _select_format_and_save(self, driver: webdriver.Chrome) -> None:
        """
        모달 내에서 파일 형식(PDF/DOCX)을 선택하고 저장 버튼을 클릭합니다.
        
        Args:
            driver: WebDriver 인스턴스
        """
        wait = WebDriverWait(driver, self.modal_timeout_sec)
        
        # 파일 형식에 따라 라디오 버튼 선택
        if self.file_format == "pdf":
            radio_xpath = self.pdf_radio_xpath
            format_name = "PDF"
        else:  # docx
            radio_xpath = self.doc_radio_xpath
            format_name = "DOCX"
        
        # 라디오 버튼 클릭
        radio_button = wait.until(EC.element_to_be_clickable((By.XPATH, radio_xpath)))
        radio_button.click()
        logger.debug(f"{format_name} 라디오 버튼 선택 완료")
        
        # 저장 버튼 클릭
        save_button = wait.until(EC.element_to_be_clickable((By.XPATH, self.download_button_xpath)))
        save_button.click()
        logger.debug("저장 버튼 클릭 완료")
    
    def download_single_law(self, driver: webdriver.Chrome, law_name: str) -> Path:
        """
        단일 법령에 대해 문서 다운로드를 수행하고 파일 경로를 반환합니다.
        
        Args:
            driver: WebDriver 인스턴스
            law_name: 다운로드할 법령명
            
        Returns:
            다운로드된 파일 경로
            
        Raises:
            TimeoutException: 다운로드가 완료되지 않을 경우
            WebDriverException: 웹 드라이버 관련 오류
        """
        # URL 인코딩
        encoded_name = quote_plus(law_name)
        target_url = f"{self.base_search_url}{encoded_name}"
        
        logger.info(f"검색 페이지 접속: {target_url}")
        driver.get(target_url)
        
        # 저장 버튼 클릭 대기 및 클릭
        wait = WebDriverWait(driver, 20)
        save_button = wait.until(EC.element_to_be_clickable((By.XPATH, self.save_button_xpath)))
        save_button.click()
        
        # 다운로드 전 파일 목록 스냅샷
        before_files = {
            f.resolve()
            for f in self.download_dir.glob('*')
            if f.is_file() and not f.name.endswith('.crdownload')
        }
        
        # 파일 형식 선택 및 저장
        self._select_format_and_save(driver)
        
        # 새로 생성된 파일 대기
        downloaded_file = self._wait_for_new_file(before_files)
        
        # 최종 파일명으로 변경
        target_name = self._sanitize_filename(law_name)
        file_extension = ".pdf" if self.file_format == "pdf" else ".docx"
        final_path = self.download_dir / f"{target_name}{file_extension}"
        
        # 파일명 변경 (이미 존재하면 덮어쓰기)
        if final_path.exists():
            final_path.unlink()
        downloaded_file.rename(final_path)
        
        logger.info(f"다운로드 완료 ({self.file_format.upper()}): {law_name} -> {final_path}")
        return final_path
    
    def bulk_download(self) -> dict:
        """
        법령명 리스트를 순회하며 일괄 다운로드를 수행합니다.
        
        Returns:
            다운로드 결과 딕셔너리
            - successes: 성공한 파일 경로 리스트
            - failures: 실패한 항목 리스트 (law_name, error 포함)
        """
        law_names = self._load_law_names()
        target_list = law_names if self.max_downloads is None else law_names[:self.max_downloads]
        
        logger.info(f"일괄 다운로드 시작: 총 {len(target_list)}개")
        
        driver = self._build_driver()
        successes = []
        failures = []
        
        try:
            for idx, name in enumerate(target_list, start=1):
                logger.info(f"[{idx}/{len(target_list)}] 처리 중: {name}")
                try:
                    path = self.download_single_law(driver, name)
                    successes.append(path)
                except Exception as exc:  # pylint: disable=broad-except
                    logger.error(f"다운로드 실패 ({name}): {exc}")
                    failures.append({"law_name": name, "error": str(exc)})
        finally:
            driver.quit()
            logger.info("WebDriver 종료")
        
        logger.info(f"일괄 다운로드 완료: 성공 {len(successes)}개, 실패 {len(failures)}개")
        
        return {
            "successes": successes,
            "failures": failures
        }
    
    def check_missing_files(self) -> List[str]:
        """
        엑셀 파일의 법령명 리스트와 비교하여 누락된 파일을 확인합니다.
        
        Returns:
            누락된 법령명 리스트
        """
        law_names = self._load_law_names()
        
        # 기존 파일 목록 (확장자 제외)
        file_extension = ".pdf" if self.file_format == "pdf" else ".doc*"
        existing_files = {
            file_path.stem
            for file_path in self.download_dir.glob(f"*{file_extension}")
        }
        
        # 누락된 법령명 찾기
        missing_law_names = [
            name for name in law_names
            if self._sanitize_filename(name) not in existing_files
        ]
        
        logger.info(
            f"파일 확인 완료: 총 {len(law_names)}개 중 "
            f"{len(existing_files)}개 다운로드 완료, "
            f"{len(missing_law_names)}개 누락"
        )
        
        return missing_law_names
    
    def retry_missing_downloads(self) -> dict:
        """
        누락된 파일만 재다운로드합니다.
        
        Returns:
            다운로드 결과 딕셔너리 (bulk_download과 동일한 형식)
        """
        missing_law_names = self.check_missing_files()
        
        if not missing_law_names:
            logger.info("모든 파일이 이미 다운로드되었습니다.")
            return {"successes": [], "failures": []}
        
        logger.info(f"누락된 항목 {len(missing_law_names)}개 재다운로드 시작")
        
        # 임시로 max_downloads를 None으로 설정하여 누락된 항목만 다운로드
        original_max_downloads = self.max_downloads
        self.max_downloads = None
        
        # 누락된 법령명만 다운로드하기 위해 임시로 list_file을 수정하는 대신
        # 직접 다운로드 로직 실행
        driver = self._build_driver()
        successes = []
        failures = []
        
        try:
            for idx, name in enumerate(missing_law_names, start=1):
                logger.info(f"[{idx}/{len(missing_law_names)}] 재다운로드 중: {name}")
                try:
                    path = self.download_single_law(driver, name)
                    successes.append(path)
                except Exception as exc:  # pylint: disable=broad-except
                    logger.error(f"재다운로드 실패 ({name}): {exc}")
                    failures.append({"law_name": name, "error": str(exc)})
        finally:
            driver.quit()
            self.max_downloads = original_max_downloads
            logger.info("WebDriver 종료")
        
        # 최종 확인
        final_missing = self.check_missing_files()
        if final_missing:
            logger.warning(f"재다운로드 후에도 {len(final_missing)}개 항목이 누락되었습니다.")
        else:
            logger.info("모든 파일 다운로드 완료!")
        
        return {
            "successes": successes,
            "failures": failures
        }


def main():
    """
    메인 실행 함수 (예제)
    """
    base_dir = Path(".")
    list_file = base_dir / "샌드박스_법령명_163개_리스트.xlsx"
    
    downloader = LawDocumentDownloader(
        base_dir=base_dir,
        list_file=list_file,
        file_format="docx",
        headless=False,
        max_downloads=None,  # 전체 다운로드
    )
    
    # 일괄 다운로드
    summary = downloader.bulk_download()
    print(f"다운로드 완료: 성공 {len(summary['successes'])}개, 실패 {len(summary['failures'])}개")
    
    # 누락 파일 재다운로드
    if summary['failures']:
        print("\n누락 파일 재다운로드 시작...")
        retry_summary = downloader.retry_missing_downloads()
        print(f"재다운로드 완료: 성공 {len(retry_summary['successes'])}개, 실패 {len(retry_summary['failures'])}개")


if __name__ == "__main__":
    main()

