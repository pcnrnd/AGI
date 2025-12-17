from __future__ import annotations

"""
Fintech Sandbox '기업소개' 상세 크롤러 (노트북 v5 기반).

원본 노트북:
- notebooks/10_sandbox/fintech/fintech_sandbox_crawler_v5_full_20251028_055640.ipynb
"""

import csv
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from agi_sandbox_law_crawling._common import build_logger

log = build_logger("agi.fintech")


@dataclass(frozen=True)
class FintechCrawlConfig:
    """Fintech Sandbox 크롤링 설정."""

    base_list_url: str = "https://sandbox.fintech.or.kr/business/enterprise_intro.do?pageIndex={page}"
    detail_base: str = "https://sandbox.fintech.or.kr/business/enterprise.do?lang=ko&id={id}"
    max_page: int = 72
    headless: bool = True
    timeout_sec: int = 14
    retry_detail: int = 2
    slow_min_sec: float = 0.35
    slow_max_sec: float = 0.9
    target_keys: Tuple[str, ...] = (
        "서비스명",
        "지정 제도",
        "서비스 주요 내용",
        "규제 특례 내용",
        "주요 부가 조건 내용",
    )


def build_driver(headless: bool = True) -> webdriver.Chrome:
    """셀레니움 드라이버를 생성합니다."""
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,2600")
    opts.add_argument("--lang=ko-KR")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    drv = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    drv.set_page_load_timeout(50)
    return drv


def _remove_artifact_tokens(s: str) -> str:
    """노트북에서 관측된 LAW 태그 같은 노이즈 토큰 제거."""
    if not s:
        return s
    s = re.sub(r"</?LAW[^>]*>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*LAW[_A-Za-z0-9\-]*\s*>", "", s, flags=re.IGNORECASE)
    return s


BULLET_START = re.compile(r"^(\s*(?:[\-–—•·/]|[①-⑳]|\(?\d{1,3}\)?[.)]|[가-힣]\))\s*)")


def _strip_leading_bullets_once(line: str) -> str:
    m = BULLET_START.match(line)
    return line[m.end() :] if m else line


def _strip_leading_bullets_multiline(text: str) -> str:
    """행별로 앞쪽 불릿/번호를 반복 제거(법 조문 형태는 보존)."""
    out_lines: list[str] = []
    for ln in text.splitlines():
        s = ln
        if re.match(r"^\s*제\s*\d+\s*조", s):
            out_lines.append(s.strip())
            continue
        prev = None
        while prev != s:
            prev = s
            s = _strip_leading_bullets_once(s)
        out_lines.append(s.strip())
    return "\n".join(out_lines).strip()


def clean_text_keep_law(s: str) -> str:
    """공백/개행 정리 + 노이즈 토큰 제거 + 불릿 제거."""
    if not s:
        return ""
    s = s.replace("\r", "\n").replace("\xa0", " ").strip()
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = "\n".join(line.strip() for line in s.splitlines())
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = _remove_artifact_tokens(s)
    s = _strip_leading_bullets_multiline(s)
    return s


def find_main_list_table(drv: webdriver.Chrome):
    """목록 페이지에서 메인 테이블(기업소개 리스트)을 찾습니다."""
    tables = drv.find_elements(By.TAG_NAME, "table")
    best, best_score = None, -1
    header_tokens = ["No", "NO", "no", "기업", "회사", "서비스", "상세", "보기", "등록일"]
    for t in tables:
        try:
            ths = t.find_elements(By.CSS_SELECTOR, "thead th")
            text = ""
            if ths:
                text = " ".join(clean_text_keep_law(th.get_attribute("innerText")) for th in ths)
            else:
                first_tr = t.find_elements(By.CSS_SELECTOR, "tr")
                if first_tr:
                    tds = first_tr[0].find_elements(By.CSS_SELECTOR, "th,td")
                    text = " ".join(clean_text_keep_law(x.get_attribute("innerText")) for x in tds)
            score = sum(1 for tok in header_tokens if tok in text)
            rows = t.find_elements(By.CSS_SELECTOR, "tbody tr")
            if len(rows) >= 5:
                score += 1
            if score > best_score:
                best, best_score = t, score
        except StaleElementReferenceException:
            continue
    return best


def extract_detail_url_from_row(row, detail_base: str) -> Optional[str]:
    """목록 행에서 상세 URL을 최대한 복구합니다."""
    cands = []
    try:
        cands.append(row)
        cands.extend(row.find_elements(By.XPATH, ".//td[5]"))
        cands.extend(row.find_elements(By.XPATH, ".//td[5]//*"))
        cands.extend(row.find_elements(By.XPATH, ".//a|.//button|.//em"))
    except Exception:
        pass
    for el in cands:
        try:
            href = (el.get_attribute("href") or "").strip()
            onclick = (el.get_attribute("onclick") or "").strip()
            if "enterprise.do" in href:
                return href
            m = re.search(r"id=(\d{1,10})", onclick)
            if m:
                return detail_base.format(id=m.group(1))
            m2 = re.search(r"['\"]?(\d{1,10})['\"]?\)", onclick)
            if m2:
                return detail_base.format(id=m2.group(1))
        except StaleElementReferenceException:
            continue
    return None


def extract_detail_urls_on_list_page(drv: webdriver.Chrome, config: FintechCrawlConfig) -> List[str]:
    """목록 페이지에서 상세 URL 리스트를 수집합니다."""
    urls: List[str] = []
    table = find_main_list_table(drv)
    if table:
        rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
        for i, row in enumerate(rows, 1):
            url = extract_detail_url_from_row(row, detail_base=config.detail_base)
            if url:
                urls.append(url)
            else:
                log.warning("상세 링크 없음: row=%s", i)

    html = drv.page_source
    urls += re.findall(r"https?://sandbox\.fintech\.or\.kr/business/enterprise\.do\?lang=ko&id=\d+", html)
    for m in re.findall(r"goView\((?:'|\"|)(\d{1,10})(?:'|\"|)\)", html):
        urls.append(config.detail_base.format(id=m))

    seen = set()
    uniq: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def find_section_table(drv: webdriver.Chrome):
    """상세 페이지에서 '샌드박스 지정 내용 및 성과' 테이블을 찾습니다."""
    anchors = drv.find_elements(By.XPATH, "//*[contains(normalize-space(.),'샌드박스 지정 내용 및 성과')]")
    if anchors:
        try:
            tbl = drv.find_element(
                By.XPATH,
                "(//*[contains(normalize-space(.),'샌드박스 지정 내용 및 성과')])[1]/following::table[1]",
            )
            return tbl
        except NoSuchElementException:
            pass

    # 노트북에서 쓰던 고정 XPath(페이지 구조 바뀌면 실패 가능)
    try:
        return drv.find_element(By.XPATH, "/html/body/div/div[2]/div[3]/div[2]/div[7]/div[2]/table")
    except NoSuchElementException:
        pass

    try:
        tables = drv.find_elements(By.TAG_NAME, "table")
    except Exception:
        return None

    best, best_score = None, -1
    keys = ["서비스", "지정", "규제", "부가", "내용"]
    for t in tables:
        try:
            text = t.get_attribute("innerText") or ""
            score = sum(1 for k in keys if k in text)
            if score > best_score and len(text) > 30:
                best, best_score = t, score
        except StaleElementReferenceException:
            continue
    return best


def parse_table_to_map(tbl) -> Dict[str, str]:
    """테이블을 {라벨: 값} 형태로 변환합니다."""
    data: dict[str, str] = {}
    rows = tbl.find_elements(By.CSS_SELECTOR, "tr")
    for r in rows:
        label = ""
        try:
            ths = r.find_elements(By.CSS_SELECTOR, "th")
            if ths:
                label = clean_text_keep_law(ths[0].get_attribute("innerText")).replace(" ", "")
            else:
                tds = r.find_elements(By.CSS_SELECTOR, "td")
                if tds:
                    maybe = clean_text_keep_law(tds[0].get_attribute("innerText"))
                    if len(maybe) <= 12:
                        label = maybe.replace(" ", "")
        except Exception:
            pass

        value = ""
        try:
            tds = r.find_elements(By.CSS_SELECTOR, "td")
            if tds:
                value = clean_text_keep_law(tds[-1].get_attribute("innerText"))
        except Exception:
            pass

        if label:
            data[label] = value
    return data


def normalize_regulatory_value(val: str) -> str:
    """규제/특례가 '없음' 류면 빈 값으로 정규화."""
    v = (val or "").strip()
    if v == "" or v in ["-", "없음", "해당없음", "해당 없음", "미해당"]:
        return ""
    if re.fullmatch(r"(없음|해당없음|해당 없음|미해당)[\.\s]*", v or ""):
        return ""
    return v


def extract_service_name_fallbacks(drv: webdriver.Chrome) -> str:
    """서비스명 추출 실패 시 fallback."""
    for xp in [
        "//h3[contains(.,'서비스')]/following::*[self::p or self::div][1]",
        "//h2|//h3|//h4",
    ]:
        try:
            el = drv.find_element(By.XPATH, xp)
            t = clean_text_keep_law(el.get_attribute("innerText"))
            if t and len(t) <= 120 and "서비스" in t:
                return t
        except Exception:
            pass
    try:
        el = drv.find_element(By.XPATH, "//*[contains(normalize-space(.),'서비스명')]/following::*[1]")
        return clean_text_keep_law(el.get_attribute("innerText"))
    except Exception:
        return ""


def extract_fields_from_detail(drv: webdriver.Chrome, config: FintechCrawlConfig) -> Dict[str, str]:
    """상세 페이지에서 target_keys를 채웁니다."""
    result = {k: "" for k in config.target_keys}
    tbl = find_section_table(drv)
    if tbl:
        m = parse_table_to_map(tbl)
        alias = {
            "지정제도": "지정 제도",
            "지정제도구분": "지정 제도",
            "지정 제도": "지정 제도",
            "서비스명": "서비스명",
            "서비스 명": "서비스명",
            "서비스주요내용": "서비스 주요 내용",
            "서비스 주요 내용": "서비스 주요 내용",
            "규제특례내용": "규제 특례 내용",
            "규제 특례 내용": "규제 특례 내용",
            "주요부가조건내용": "주요 부가 조건 내용",
            "주요 부가 조건 내용": "주요 부가 조건 내용",
        }
        for k_src, v in m.items():
            k_norm = alias.get(k_src)
            if k_norm in result:
                result[k_norm] = v

        # 행 위치 기반 fallback (노트북 로직 유지)
        def td_by_row(idx: int) -> str:
            try:
                el = tbl.find_element(By.XPATH, f".//tbody/tr[{idx}]/td")
                return clean_text_keep_law(el.get_attribute("innerText"))
            except Exception:
                return ""

        if not result["지정 제도"]:
            result["지정 제도"] = td_by_row(1)
        if not result["서비스명"]:
            result["서비스명"] = td_by_row(2)
        if not result["서비스 주요 내용"]:
            result["서비스 주요 내용"] = td_by_row(3)
        if not result["규제 특례 내용"]:
            result["규제 특례 내용"] = td_by_row(5)
        if not result["주요 부가 조건 내용"]:
            result["주요 부가 조건 내용"] = td_by_row(6)

    if not result["서비스명"]:
        result["서비스명"] = extract_service_name_fallbacks(drv)

    result["규제 특례 내용"] = normalize_regulatory_value(result.get("규제 특례 내용", ""))
    return result


ZW_CHARS = r"[\u200B-\u200F\u202A-\u202E\u2060-\u206F\uFEFF]"
BULLETS = "•·●○◆◇■□▶▷◀◁▲△▼▽※☆★→←↔⇒⇔◦ㆍ❖➤➔➜➝✓✔✗✘"


def sanitize_text(s: str) -> str:
    """CSV 저장 전 텍스트 후처리(제어문자/불릿/중복공백 제거)."""
    if not isinstance(s, str):
        return s
    t = s
    t = re.sub(ZW_CHARS, "", t)
    t = t.translate({ord(ch): None for ch in BULLETS})
    t = re.sub(r"^[\-\=_]{2,}$", "", t, flags=re.MULTILINE)
    t = re.sub(r"</?LAW[^>]*>", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


def sanitize_df(df: pd.DataFrame) -> pd.DataFrame:
    clean_df = df.copy()
    for col in clean_df.columns:
        clean_df[col] = clean_df[col].map(sanitize_text)
    return clean_df


def crawl_fintech_enterprise_intro(
    *,
    config: FintechCrawlConfig = FintechCrawlConfig(),
    out_raw_csv: Optional[Path] = None,
    out_clean_csv: Optional[Path] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Fintech Sandbox 기업소개 페이지를 페이지네이션으로 순회하며 상세 내용을 수집합니다.

    반환값:
    - raw_df: 원문에 가까운 DataFrame
    - clean_df: 특수문자/불릿 정리 후 DataFrame
    """
    if config.max_page <= 0:
        raise ValueError("max_page는 1 이상이어야 합니다.")

    ts = int(time.time())
    out_raw_csv = out_raw_csv or Path(f"./fintech_sandbox_v5_raw_{ts}.csv")
    out_clean_csv = out_clean_csv or Path(f"./fintech_sandbox_v5_clean_{ts}.csv")

    drv = build_driver(headless=config.headless)
    collected: list[dict[str, str]] = []
    bad_links: list[str] = []

    try:
        for page in range(1, config.max_page + 1):
            list_url = config.base_list_url.format(page=page)
            drv.get(list_url)
            try:
                WebDriverWait(drv, config.timeout_sec).until(
                    EC.presence_of_element_located((By.XPATH, "//table//tbody//tr"))
                )
            except TimeoutException:
                log.warning("목록 테이블 로드 타임아웃: page=%s", page)
                continue

            time.sleep(random.uniform(config.slow_min_sec, config.slow_max_sec))

            detail_urls = extract_detail_urls_on_list_page(drv, config)
            log.info("PAGE %s: detail=%s", page, len(detail_urls))

            for i, du in enumerate(detail_urls, 1):
                ok = False
                for attempt in range(1, config.retry_detail + 2):
                    try:
                        drv.get(du)
                        WebDriverWait(drv, config.timeout_sec).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
                        )
                        time.sleep(random.uniform(0.2, 0.6))

                        item = extract_fields_from_detail(drv, config)
                        row = {k: item.get(k, "") for k in config.target_keys}
                        collected.append(row)
                        log.info("  (%s/%s) OK: %s", i, len(detail_urls), row.get("서비스명", "")[:80])
                        ok = True
                        break
                    except TimeoutException:
                        log.warning("  (%s/%s) TIMEOUT[%s]: %s", i, len(detail_urls), attempt, du)
                        time.sleep(0.5 + 0.2 * attempt)
                    except WebDriverException as e:
                        log.warning("  (%s/%s) WEBDRV[%s] ERR: %s", i, len(detail_urls), attempt, e)
                        time.sleep(0.5 + 0.2 * attempt)
                    except Exception as e:
                        log.warning("  (%s/%s) ERR[%s]: %s", i, len(detail_urls), attempt, e)
                        time.sleep(0.5 + 0.2 * attempt)

                if not ok:
                    bad_links.append(du)

            time.sleep(random.uniform(config.slow_min_sec, config.slow_max_sec))

        df = pd.DataFrame(collected, columns=list(config.target_keys))
        df.to_csv(out_raw_csv, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)
        log.info("Saved RAW CSV -> %s (rows=%s)", out_raw_csv, len(df))

        df_clean = sanitize_df(df)
        df_clean.to_csv(out_clean_csv, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)
        log.info("Saved CLEAN CSV -> %s (rows=%s)", out_clean_csv, len(df_clean))

        if bad_links:
            log.warning("재시도 후 실패 링크: %s", len(bad_links))

        return df, df_clean
    finally:
        try:
            drv.quit()
        except Exception:
            pass

