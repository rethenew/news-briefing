#!/usr/bin/env python3
# ============================================================
# 식품진흥원 뉴스 브리핑 자동화 시스템
# scheduler.py - 스케줄러
# ============================================================
# 실행 방법:
#   python scheduler.py --initial   ← 3월 1일부터 1차 수집 후 매 정각 기준 15분마다 실행
#   python scheduler.py             ← 바로 매 정각 기준 15분마다 실행 (00, 15, 30, 45분)
#   python scheduler.py --now       ← 즉시 1회만 실행
# ============================================================

import logging
import argparse
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import COLLECT_INTERVAL_MINUTES
from collector import run_collection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def scheduled_job():
    logger.info(f"[정기 수집] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        run_collection(initial=False)
    except Exception as e:
        logger.error(f"수집 오류: {e}", exc_info=True)


def main():
    parser = argparse.ArgumentParser(description="식품진흥원 뉴스 브리핑 스케줄러")
    parser.add_argument("--initial", action="store_true",
                        help="3월 1일~현재 1차 전체 수집 후 정각 기준 15분마다 정기 수집")
    parser.add_argument("--now", action="store_true",
                        help="즉시 1회 수집만 실행")
    args = parser.parse_args()

    # ── 즉시 1회만 실행 ──
    if args.now:
        run_collection(initial=False)
        return

    # ── 1차 전체 수집 ──
    if args.initial:
        logger.info("=" * 60)
        logger.info("1차 전체 수집 시작 (2026-03-01 ~ 현재)")
        logger.info("=" * 60)
        run_collection(initial=True)
        logger.info("1차 수집 완료. 정기 수집 스케줄로 전환합니다.")

    # ── 정각 기준 15분마다 실행 (00, 15, 30, 45분) ──
    logger.info("정기 수집 스케줄러 시작 · 매시 00, 15, 30, 45분에 실행")

    scheduler = BlockingScheduler(timezone="Asia/Seoul")
    scheduler.add_job(
        scheduled_job,
        trigger=CronTrigger(minute="0,15,30,45", timezone="Asia/Seoul"),
        misfire_grace_time=60,
    )

    # 다음 실행 시각 안내
    from apscheduler.triggers.cron import CronTrigger as CT
    trigger = CT(minute="0,15,30,45", timezone="Asia/Seoul")
    next_run = trigger.get_next_fire_time(None, datetime.now().astimezone())
    logger.info(f"다음 수집 예정: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        logger.info("스케줄러 실행 중... 종료: Ctrl+C")
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("스케줄러 종료")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
