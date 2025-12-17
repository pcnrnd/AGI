from __future__ import annotations

"""
RFZ 규제자유특구 사례 크롤러 (menuno=206) - 노트북 rfz_crawler_v4 기반.

원본 노트북:
- notebooks/10_sandbox/rfz/rfz_crawler_v4.ipynb
"""

import csv
import re
import time
from dataclasses import dataclass
from typing import List, Tuple

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from agi_sandbox_law_crawling._common import build_logger

log = build_logger("agi.rfz206")


@dataclass(frozen=True)
class Rfz206Config:
    url: str = "https://rfz.go.kr/?menuno=206#none"
    headless: bool = True
    out_csv: str = "rfz_crawl.csv"
    dedup: bool = True


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def clean_major_title(s: str) -> str:
    """대제목 앞의 차수 표기(10차 등) 제거."""
    s = normalize_spaces(s)
    s = re.sub(r"^\s*(?:\d+|[①-⑳])\s*차\s*[-–—·\.\)]*\s*", "", s)
    return s


def clean_mid_title(s: str) -> str:
    """중제목 앞 '실증특례' 접두 제거."""
    s0 = normalize_spaces(s)
    s1 = re.sub(
        r"^\s*[\u2460-\u2473]?\s*(?:\(|\[)?\s*실증\s*특례\s*(?:\)|\])?\s*[-–—:·\.\)]*\s*",
        "",
        s0,
    )
    return s1 if s1 else s0


def first_sentence(txt: str, max_len: int = 120) -> str:
    txt = normalize_spaces(txt)
    m = re.search(r"(.+?)(?:[.!?。…]|$)", txt)
    cand = m.group(1) if m else txt
    return cand[:max_len].strip()


def extract_subtitle_from_block(html: str) -> str:
    """본문 블록에서 소제목(보통 strong 또는 [] 텍스트) 추출."""
    soup = BeautifulSoup(html or "", "html.parser")
    st = soup.find("strong")
    if st:
        return normalize_spaces(st.get_text(" ", strip=True))
    flat = soup.get_text(" ", strip=True)
    m = re.search(r"\[([^\]]+)\]", flat)
    if m:
        return normalize_spaces(m.group(1))

    flat2 = re.sub(r"(?:\(|\[)?\s*(현황|허용|조건부\s*허용)\s*(?:\)|\])", " ||LABEL|| ", flat)
    pre = flat2.split("||LABEL||")[0]
    return first_sentence(pre) if pre.strip() else ""


def strip_label_prefix(s: str, label_regex: str) -> str:
    return re.sub(label_regex, "", s, flags=re.I).strip()


def parse_stat_allow_from_block_html(html: str) -> Tuple[str, str]:
    """블록 HTML에서 현황/허용 텍스트를 분리."""
    soup = BeautifulSoup(html or "", "html.parser")
    parts_stat, parts_allow = [], []
    state = None

    label_pat = re.compile(
        r"^\s*(?:\(|\[)?\s*(현황|허용|조건부\s*허용)\s*(?:\)|\])?\s*[:\-–—·\.\)]*\s*",
        re.I,
    )

    elems = soup.find_all(["p", "div"])
    for el in elems:
        txt = el.get_text(" ", strip=True)
        if not txt:
            continue

        label_hit = None
        for b in el.find_all(["b", "strong"]):
            t = b.get_text(" ", strip=True)
            if re.search(r"현황", t):
                label_hit = "stat"
                break
            if re.search(r"(?:조건부\s*)?허용", t):
                label_hit = "allow"
                break

        m = label_pat.match(txt)
        if m:
            key = m.group(1)
            state = "allow" if re.search(r"허용", key) else "stat"
            txt = txt[m.end() :].strip()
        elif label_hit:
            state = label_hit
            txt = strip_label_prefix(
                txt,
                r"^\s*(?:\(|\[)?\s*(?:현황|허용|조건부\s*허용)\s*(?:\)|\])?\s*[:\-–—·\.\)]*\s*",
            )
        else:
            # '☞ ... 허용' 형태는 허용으로 처리
            if txt.lstrip().startswith("☞") and ("허용" in txt):
                state = "allow"
                txt = txt.lstrip("☞").strip()

        if state == "stat":
            parts_stat.append(txt)
        elif state == "allow":
            parts_allow.append(txt)

    stat = normalize_spaces(" ".join(parts_stat))
    allow = normalize_spaces(" ".join(parts_allow))

    stat = strip_label_prefix(stat, r"^\s*(?:\(|\[)?\s*현황\s*(?:\)|\])?\s*[:\-–—·\.\)]*\s*")
    allow = strip_label_prefix(allow, r"^\s*(?:\(|\[)?\s*(?:조건부\s*)?허용\s*(?:\)|\])?\s*[:\-–—·\.\)]*\s*")
    return stat, allow


def build_driver(headless: bool = True) -> webdriver.Chrome:
    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=opts)
    driver.set_window_size(1400, 2000)
    return driver


def crawl_rfz_menuno206(config: Rfz206Config = Rfz206Config()) -> pd.DataFrame:
    """
    RFZ menuno=206 페이지를 크롤링하여 DataFrame으로 반환하고 CSV로 저장합니다.

    컬럼: 대제목, 중제목, 소제목, 현황, 허용
    """
    driver = build_driver(headless=config.headless)
    all_rows: list[list[str]] = []
    try:
        driver.get(config.url)
        WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.CSS_SELECTOR, "form > ul > li")))
        lis = driver.find_elements(By.CSS_SELECTOR, "form > ul > li")

        for li in lis:
            # 탭 클릭
            a = li.find_element(By.XPATH, ".//a")
            driver.execute_script("arguments[0].click();", a)
            try:
                WebDriverWait(driver, 10).until(
                    lambda d: "active" in (li.get_attribute("class") or "").lower()
                )
            except TimeoutException:
                driver.execute_script("arguments[0].click();", a)
                WebDriverWait(driver, 10).until(
                    lambda d: "active" in (li.get_attribute("class") or "").lower()
                )

            major = clean_major_title(a.text)

            scopes = li.find_elements(
                By.XPATH, ".//div[contains(@class,'con-template-list') or contains(@class,'before')]"
            )
            scopes = [e for e in scopes if e.is_displayed()]
            scope = scopes[0] if scopes else li

            h4s = [e for e in scope.find_elements(By.XPATH, ".//h4") if e.is_displayed()]
            for h4 in h4s:
                mid = clean_mid_title(h4.text).strip()
                if not mid:
                    continue

                uls = [e for e in h4.find_elements(By.XPATH, "following-sibling::ul[1]") if e.is_displayed()]
                if not uls:
                    continue
                ul = uls[0]

                li_items = [e for e in ul.find_elements(By.XPATH, "./li") if e.is_displayed()]
                for it in li_items:
                    blocks = it.find_elements(
                        By.XPATH, ".//div[contains(@class,'txt-area') or contains(@class,'text')]"
                    )
                    blocks = [e for e in blocks if e.is_displayed()] or [it]
                    for b in blocks:
                        html = b.get_attribute("innerHTML") or ""
                        sub = extract_subtitle_from_block(html)
                        stat, allow = parse_stat_allow_from_block_html(html)
                        all_rows.append([major, mid, sub, stat, allow])

            time.sleep(0.1)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    df = pd.DataFrame(all_rows, columns=["대제목", "중제목", "소제목", "현황", "허용"])
    if config.dedup and not df.empty:
        df = df.drop_duplicates(subset=["대제목", "중제목", "소제목", "현황", "허용"], keep="first").reset_index(
            drop=True
        )

    df.to_csv(
        config.out_csv,
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_ALL,
        quotechar='"',
        doublequote=True,
        lineterminator="\n",
    )
    log.info("Saved to %s (rows=%s)", config.out_csv, len(df))
    return df

