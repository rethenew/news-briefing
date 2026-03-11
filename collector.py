#!/usr/bin/env python3
# ============================================================
# 식품진흥원 뉴스 브리핑 자동화 시스템
# collector.py - 뉴스 수집 엔진
# ============================================================

import os
import re
import json
import time
import hashlib
import logging
import requests
import urllib.parse
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict, field

from config import (
    NAVER_CLIENT_ID,
    NAVER_CLIENT_SECRET,
    CATEGORIES,
    BODY_MATCH_KEYWORDS,
    MAX_ARTICLES_PER_KEYWORD,
    MAX_ARTICLES_INITIAL,
    DUPLICATE_THRESHOLD,
    OUTPUT_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("news_briefing.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ============================================================
# 데이터 클래스
# ============================================================

@dataclass
class Article:
    title: str
    link: str
    description: str
    pub_date: str
    source: str
    category: str
    keywords_matched: List[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    def uid(self) -> str:
        return hashlib.md5(self.link.encode()).hexdigest()


# ============================================================
# 유사도 계산 (자카드 유사도)
# ============================================================

def _tokenize(text: str) -> set:
    return set(re.findall(r"[가-힣a-zA-Z0-9]+", text.lower()))


def _bigrams(text: str) -> set:
    """2개 연속 단어 조합 (구문 단위 유사도 측정용)"""
    tokens = re.findall(r"[가-힣a-zA-Z0-9]+", text.lower())
    return set(zip(tokens, tokens[1:])) if len(tokens) >= 2 else set()


def similarity(text_a: str, text_b: str) -> float:
    """단어 단위 자카드 유사도"""
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def bigram_similarity(text_a: str, text_b: str) -> float:
    """바이그램(2연속 단어) 자카드 유사도 — 핵심 구문 중복 탐지용"""
    bg_a = _bigrams(text_a)
    bg_b = _bigrams(text_b)
    if not bg_a or not bg_b:
        return 0.0
    return len(bg_a & bg_b) / len(bg_a | bg_b)


def is_duplicate(article: Article, existing: List[Article], threshold: float) -> bool:
    """
    중복 판정 — 아래 셋 중 하나라도 해당하면 제외:
      ① 제목 단어 유사도  65% 이상 (거의 같은 제목)
      ② 제목 바이그램 유사도  50% 이상 (핵심 구문이 같음)
      ③ 제목+요약 단어 유사도  80% 이상 (내용 전체 중복)
    """
    TITLE_UNI_THRESHOLD  = 0.50   # ① 제목 단어 50% 이상 겹치면 중복
    TITLE_BI_THRESHOLD   = 0.50   # ② 제목 구문 50% 이상 겹치면 중복
    FULL_UNI_THRESHOLD   = 0.50   # ③ 제목+요약 50% 이상 겹치면 중복

    new_title = article.title
    new_full  = article.title + " " + article.description

    for ex in existing:
        ex_title = ex.title
        ex_full  = ex.title + " " + ex.description

        # ① 제목 단어 유사도
        t_sim = similarity(new_title, ex_title)
        if t_sim >= TITLE_UNI_THRESHOLD:
            logger.info(f"  ↳ 중복(제목단어 {t_sim:.0%}): {article.title[:40]}")
            return True

        # ② 제목 바이그램 유사도 — "수출주니어 기업" 같은 구문 일치 탐지
        b_sim = bigram_similarity(new_title, ex_title)
        if b_sim >= TITLE_BI_THRESHOLD:
            logger.info(f"  ↳ 중복(제목구문 {b_sim:.0%}): {article.title[:40]}")
            return True

        # ③ 제목+요약 전체 유사도
        f_sim = similarity(new_full, ex_full)
        if f_sim >= FULL_UNI_THRESHOLD:
            logger.info(f"  ↳ 중복(전체내용 {f_sim:.0%}): {article.title[:40]}")
            return True

    return False


# ============================================================
# 날짜 파싱
# ============================================================

def parse_pub_date(date_str: str) -> Optional[datetime]:
    try:
        return parsedate_to_datetime(date_str).replace(tzinfo=None)
    except Exception:
        return None


# ============================================================
# 네이버 뉴스 API 수집
# ============================================================

class NaverNewsCollector:
    BASE_URL = "https://openapi.naver.com/v1/search/news.json"

    def __init__(self, client_id: str, client_secret: str):
        self.headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        }

    def search(self, keyword: str, display: int = 10, start: int = 1) -> List[Dict]:
        params = {
            "query": keyword,
            "display": min(display, 100),
            "start": start,
            "sort": "date",
        }
        try:
            resp = requests.get(self.BASE_URL, headers=self.headers, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json().get("items", [])
        except Exception as e:
            logger.warning(f"네이버 API 오류 ({keyword}): {e}")
            return []

    def search_range(self, keyword: str, date_from: datetime, date_to: datetime, max_articles: int) -> List[Dict]:
        """날짜 범위 내 기사를 페이지네이션으로 수집"""
        collected = []
        start = 1

        while len(collected) < max_articles:
            items = self.search(keyword, display=100, start=start)
            if not items:
                break

            stop = False
            for item in items:
                pub = parse_pub_date(item.get("pubDate", ""))
                if pub is None:
                    continue
                if pub > date_to:
                    continue
                if pub < date_from:
                    stop = True
                    break
                collected.append(item)
                if len(collected) >= max_articles:
                    stop = True
                    break

            if stop or len(items) < 100:
                break

            start += 100
            time.sleep(0.15)   # API 과호출 방지

        return collected

    def collect_by_category(self, categories: Dict, date_from=None, date_to=None, initial=False) -> Dict[str, List[Article]]:
        result = {cat: [] for cat in categories}
        seen_uids: set = set()   # URL 기준 전역 중복 제거 (동일 링크)
        max_per_kw = MAX_ARTICLES_INITIAL if initial else MAX_ARTICLES_PER_KEYWORD

        for cat_name, cat_info in categories.items():
            kw_filtered = 0
            dup_filtered = 0

            for keyword in cat_info["keywords"]:
                # 초기/정기 모두 날짜 범위 필터 적용
                if date_from and date_to:
                    items = self.search_range(keyword, date_from, date_to, max_per_kw)
                else:
                    items = self.search(keyword, display=max_per_kw)

                logger.info(f"  [{keyword}] API 응답 {len(items)}건")

                for item in items:
                    title = self._clean_html(item.get("title", ""))
                    desc  = self._clean_html(item.get("description", ""))

                    # ── 키워드 매칭 필터 ──
                    if keyword in BODY_MATCH_KEYWORDS:
                        if not self._exact_match(keyword, title) and not self._exact_match(keyword, desc):
                            kw_filtered += 1
                            continue
                    else:
                        if not self._exact_match(keyword, title):
                            kw_filtered += 1
                            continue

                    article = Article(
                        title=title,
                        link=item.get("originallink") or item.get("link", ""),
                        description=desc[:200] + "..." if desc else "",
                        pub_date=item.get("pubDate", ""),
                        source=self._extract_source(item.get("originallink", "")),
                        category=cat_name,
                        keywords_matched=[keyword],
                    )

                    # ── URL 중복 제거 (전역) ──
                    uid = article.uid()
                    if uid in seen_uids:
                        continue

                    # ── 유사도 중복 제거 (카테고리 내에서만 비교) ──
                    if is_duplicate(article, result[cat_name], DUPLICATE_THRESHOLD):
                        dup_filtered += 1
                        continue

                    seen_uids.add(uid)
                    result[cat_name].append(article)

            logger.info(
                f"[{cat_name}] ✅ 채택 {len(result[cat_name])}건 "
                f"| 키워드 불일치 제외 {kw_filtered}건 "
                f"| 유사도 중복 제외 {dup_filtered}건"
            )

        return result

    @staticmethod
    def _exact_match(keyword: str, text: str) -> bool:
        """대소문자 무시하고 키워드가 텍스트에 포함되는지 확인"""
        return keyword.strip().lower() in text.strip().lower()

    @staticmethod
    def _clean_html(text: str) -> str:
        return re.sub(r"<[^>]+>", "", text) \
            .replace("&amp;", "&").replace("&lt;", "<") \
            .replace("&gt;", ">").replace("&quot;", '"')

    @staticmethod
    def _extract_source(url: str) -> str:
        try:
            return urllib.parse.urlparse(url).netloc.replace("www.", "")
        except Exception:
            return "알 수 없음"


# ============================================================
# JSON 저장
# ============================================================

def save_json(results: Dict[str, List[Article]], output_dir: str, label: str = ""):
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    tag = f"_{label}" if label else ""
    serializable = {cat: [a.to_dict() for a in arts] for cat, arts in results.items()}
    for path in [
        os.path.join(output_dir, f"briefing_{timestamp}{tag}.json"),
        os.path.join(output_dir, "latest.json"),
    ]:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
    logger.info(f"JSON 저장: briefing_{timestamp}{tag}.json")


# ============================================================
# 메인 수집 함수
# ============================================================

def run_collection(initial: bool = False):
    logger.info("=" * 60)
    mode = "【1차 전체 수집】" if initial else "【정기 수집】"
    logger.info(f"{mode} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    if NAVER_CLIENT_ID == "여기에_Client_ID":
        logger.error("config.py에 네이버 API 키를 입력하세요.")
        return {}

    naver = NaverNewsCollector(NAVER_CLIENT_ID, NAVER_CLIENT_SECRET)

    # 3월 1일 이후 기사만 수집 (초기/정기 모두 동일 기준)
    date_from = datetime(2026, 3, 1, 0, 0, 0)
    date_to   = datetime.now()
    logger.info(f"수집 기간: {date_from.strftime('%Y-%m-%d')} ~ {date_to.strftime('%Y-%m-%d %H:%M')}")

    if initial:
        # 1차 전체 수집 — 페이지네이션으로 최대한 많이
        results = naver.collect_by_category(
            CATEGORIES, date_from=date_from, date_to=date_to, initial=True
        )
        label = "initial"
    else:
        # 정기 수집 — 최신순으로 수집 후 날짜 필터 적용
        results = naver.collect_by_category(
            CATEGORIES, date_from=date_from, date_to=date_to, initial=False
        )
        label = ""

    total = sum(len(v) for v in results.values())
    logger.info(f"최종 채택 {total}건")
    save_json(results, OUTPUT_DIR, label)

    from renderer import render_html
    html_path = render_html(results, OUTPUT_DIR)
    logger.info(f"HTML 생성: {html_path}")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--initial", action="store_true", help="3월 1일부터 전체 수집")
    args = parser.parse_args()
    run_collection(initial=args.initial)
