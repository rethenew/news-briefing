#!/usr/bin/env python3
# ============================================================
# renderer.py - HTML 브리핑 생성기
# ============================================================

import os
from datetime import datetime
from typing import Dict, List
from config import CATEGORIES, COLLECT_INTERVAL_MINUTES

ARTICLES_PER_PAGE = 7


def format_date(date_str: str) -> str:
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%m/%d %H:%M")
    except:
        return date_str[:16] if date_str else ""


def render_html(results: Dict, output_dir: str) -> str:
    now           = datetime.now()
    date_str      = now.strftime("%Y년 %m월 %d일")
    datetime_full = now.strftime("%Y-%m-%d %H:%M:%S")
    total_count   = sum(len(v) for v in results.values())
    interval_sec  = COLLECT_INTERVAL_MINUTES * 60

    # 다음 수집 시각을 Unix timestamp로 HTML에 고정 기록
    # → 새로고침해도 남은 시간이 정확하게 표시됨
    import time as _time
    # 다음 수집 시각 = 다음 정각 기준 15분 단위 (00, 15, 30, 45분)
    now_ts   = int(_time.time())
    now_min  = datetime.now().minute
    now_sec  = datetime.now().second
    # 현재 분에서 다음 15분 단위까지 남은 초 계산
    remain_min = 15 - (now_min % 15)
    remain_sec = remain_min * 60 - now_sec
    next_collect_ts = now_ts + remain_sec
    interval_sec = remain_sec  # 진행바 기준도 동일하게

    # ── 카테고리 섹션 HTML ──
    sections_html = ""
    stats_chips   = ""
    all_js_data   = []  # JS용 페이지 데이터

    cat_index = 0
    for cat_name, cat_info in CATEGORIES.items():
        articles = results.get(cat_name, [])
        if not articles:
            cat_index += 1
            continue

        color    = cat_info.get("color", "#555")
        icon     = cat_info.get("icon",  "📌")
        cat_id   = f"cat{cat_index}"  # 숫자 ID 사용 (한글 ID 충돌 방지)
        def parse_for_sort(article):
            try:
                from email.utils import parsedate_to_datetime
                return parsedate_to_datetime(article.pub_date)
            except:
                return datetime.min

        sorted_arts = sorted(articles, key=parse_for_sort, reverse=True)
        pages    = [sorted_arts[i:i+ARTICLES_PER_PAGE] for i in range(0, max(len(sorted_arts), 1), ARTICLES_PER_PAGE)]
        total_p  = len(pages)

        stats_chips += f'<span class="stat-chip">{icon} {cat_name} {len(articles)}건</span>\n'

        # 페이지별 기사 HTML
        pages_html = ""
        for p_idx, page_arts in enumerate(pages):
            items_html = ""
            for i, a in enumerate(page_arts):
                global_num = p_idx * ARTICLES_PER_PAGE + i + 1
                tags       = "".join(f'<span class="kw-tag">{kw}</span>' for kw in a.keywords_matched[:3])
                desc       = f'<div class="art-desc">{a.description}</div>' if a.description else ""
                featured   = ' featured' if (i == 0 and p_idx == 0) else ""
                items_html += f"""<div class="art-item{featured}">
              <div class="art-header"><span class="art-num">{str(global_num).zfill(2)}</span>{tags}</div>
              <a class="art-title" href="{a.link}" target="_blank" rel="noopener">{a.title}</a>
              {desc}
              <div class="art-meta"><span>📰 {a.source}</span><span>🕐 {format_date(a.pub_date)}</span><span class="art-link">→ 원문 보기</span></div>
            </div>"""

            # 첫 페이지만 visible, 나머지는 hidden (CSS 아닌 inline style로)
            vis = "block" if p_idx == 0 else "none"
            pages_html += f'<div id="{cat_id}-p{p_idx}" style="display:{vis}">{items_html}</div>'

        # 페이지네이션 컨트롤
        if total_p > 1:
            btns = "".join(
                f'<button id="{cat_id}-btn{i}" class="pg-btn{" pg-active" if i==0 else ""}" '
                f'onclick="goPage(\'{cat_id}\',{i},{total_p})">{i+1}</button>'
                for i in range(total_p)
            )
            pagination = f"""<div class="pagination">
            <button class="pg-arrow" onclick="goPage('{cat_id}', window.__pg_{cat_id}-1, {total_p})">&#8249;</button>
            {btns}
            <button class="pg-arrow" onclick="goPage('{cat_id}', window.__pg_{cat_id}+1, {total_p})">&#8250;</button>
            <span class="pg-info" id="{cat_id}-info">1 / {total_p} 페이지 &nbsp;·&nbsp; 총 {len(articles)}건</span>
          </div>"""
            all_js_data.append(f"window.__pg_{cat_id} = 0;")
        else:
            pagination = f'<div class="pg-single-info">총 {len(articles)}건</div>'

        sections_html += f"""<div class="section">
        <div class="sec-header" style="background:{color}">{icon}&nbsp; {cat_name}<span class="sec-count">{len(articles)}건</span></div>
        <div class="art-list">{pages_html}</div>
        {pagination}
      </div>"""

        cat_index += 1

    js_init = "\n".join(all_js_data)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>식품진흥원 뉴스 브리핑 {date_str}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:'Apple SD Gothic Neo','Noto Sans KR',sans-serif;background:#f2f0eb;color:#1a1814;font-size:14px;line-height:1.6;}}
.masthead{{background:#1a237e;color:#fff;}}
.mast-top{{display:flex;justify-content:space-between;align-items:center;padding:7px 24px;border-bottom:1px solid rgba(255,255,255,.12);font-size:11px;opacity:.85;}}
.live{{display:flex;align-items:center;gap:5px;color:#ffd740;font-weight:600;}}
.dot{{width:7px;height:7px;background:#ffd740;border-radius:50%;animation:blink 1.4s infinite;}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.15}}}}
.mast-body{{text-align:center;padding:16px 24px 10px;}}
.mast-body h1{{font-size:22px;font-weight:700;}}
.mast-body .sub{{font-size:11px;opacity:.7;margin-top:4px;}}
.mast-meta{{display:flex;justify-content:space-between;align-items:center;padding:8px 24px;border-top:1px solid rgba(255,255,255,.1);font-size:12px;}}
.countdown-wrap{{display:flex;align-items:center;gap:8px;}}
.countdown-label{{opacity:.75;}}
.countdown-box{{display:flex;align-items:center;gap:4px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.2);border-radius:8px;padding:3px 12px;font-size:15px;font-weight:700;letter-spacing:.04em;}}
.cd-sep{{opacity:.5;}}
.progress-bar-wrap{{height:3px;background:rgba(255,255,255,.15);}}
.progress-bar{{height:3px;background:#ffd740;transition:width 1s linear;}}
.container{{max-width:820px;margin:0 auto;padding:18px 14px 48px;}}
.update-bar{{background:#e8f5e9;border-left:4px solid #43a047;padding:8px 14px;margin-bottom:12px;font-size:12px;color:#2e7d32;border-radius:0 6px 6px 0;}}
.copy-notice{{background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:8px 14px;font-size:11px;color:#795548;margin-bottom:14px;}}
.stats{{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:16px;}}
.stat-chip{{background:#fff;border-radius:20px;padding:4px 13px;font-size:11.5px;box-shadow:0 1px 3px rgba(0,0,0,.1);color:#444;}}
.section{{background:#fff;border-radius:10px;margin-bottom:14px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08);}}
.sec-header{{display:flex;align-items:center;gap:8px;padding:10px 16px;color:#fff;font-weight:700;font-size:13px;}}
.sec-count{{margin-left:auto;background:rgba(255,255,255,.2);border-radius:10px;padding:1px 10px;font-size:11px;font-weight:500;}}
.art-item{{padding:11px 16px;border-bottom:1px solid #f0f0f0;transition:background .12s;}}
.art-item:hover{{background:#fafaf7;}}
.art-item:last-child{{border-bottom:none;}}
.art-item.featured{{background:linear-gradient(135deg,#fffdf9,#faf7f0);border-bottom:2px solid #e8e4dc;}}
.art-header{{display:flex;align-items:center;gap:6px;margin-bottom:4px;flex-wrap:wrap;}}
.art-num{{font-size:10px;color:#bbb;font-weight:700;min-width:20px;}}
.kw-tag{{background:#e3f2fd;color:#1565c0;font-size:10px;padding:1px 7px;border-radius:8px;font-weight:600;}}
.art-title{{font-size:13.5px;font-weight:600;color:#1a237e;text-decoration:none;display:block;line-height:1.45;margin-bottom:3px;}}
.art-title:hover{{color:#c0392b;text-decoration:underline;}}
.art-item.featured .art-title{{font-size:14.5px;}}
.art-desc{{font-size:12px;color:#666;margin-bottom:4px;line-height:1.5;}}
.art-meta{{display:flex;gap:10px;font-size:10.5px;color:#bbb;flex-wrap:wrap;}}
.art-link{{color:#1565c0;}}
.pagination{{display:flex;align-items:center;gap:4px;padding:10px 16px;border-top:1px solid #f0f0f0;background:#fafafa;flex-wrap:wrap;}}
.pg-btn{{min-width:30px;height:30px;border:1px solid #ddd;background:#fff;border-radius:6px;font-size:12px;font-weight:600;color:#555;cursor:pointer;transition:all .15s;}}
.pg-btn:hover{{border-color:#1a237e;color:#1a237e;background:#f0f4ff;}}
.pg-active{{background:#1a237e !important;color:#fff !important;border-color:#1a237e !important;}}
.pg-arrow{{min-width:30px;height:30px;border:1px solid #ddd;background:#fff;border-radius:6px;font-size:18px;line-height:1;color:#555;cursor:pointer;transition:all .15s;}}
.pg-arrow:hover{{border-color:#1a237e;color:#1a237e;background:#f0f4ff;}}
.pg-info{{margin-left:auto;font-size:11px;color:#aaa;}}
.pg-single-info{{padding:8px 16px;font-size:11px;color:#aaa;border-top:1px solid #f0f0f0;background:#fafafa;}}
.footer{{text-align:center;font-size:11px;color:#aaa;padding:20px;border-top:1px solid #e0ddd6;line-height:1.9;}}
</style>
</head>
<body>
<header class="masthead">
  <div class="mast-top">
    <span>한국식품산업클러스터진흥원 내부 자료</span>
    <span class="live"><span class="dot"></span>LIVE &nbsp;·&nbsp; 자동수집</span>
    <span>{datetime_full} 기준</span>
  </div>
  <div class="mast-body">
    <h1>🍱 식품진흥원 뉴스 브리핑</h1>
    <div class="sub">네이버 뉴스 API &nbsp;·&nbsp; 키워드 100% 일치 &nbsp;·&nbsp; 유사도 중복 제거 &nbsp;·&nbsp; {COLLECT_INTERVAL_MINUTES}분 간격</div>
  </div>
  <div class="mast-meta">
    <span>{date_str} &nbsp;·&nbsp; 총 <strong>{total_count}건</strong></span>
    <div class="countdown-wrap">
      <span class="countdown-label">다음 수집까지</span>
      <div class="countdown-box">
        <span id="cd-min">00</span><span class="cd-sep">:</span><span id="cd-sec">00</span>
      </div>
    </div>
  </div>
  <div class="progress-bar-wrap"><div class="progress-bar" id="prog" style="width:100%"></div></div>
</header>

<div class="container">
  <div class="update-bar">🔄 마지막 업데이트: <strong>{datetime_full}</strong> &nbsp;·&nbsp; 총 <strong>{total_count}건</strong></div>
  <div class="copy-notice">⚖️ <strong>저작권 안내:</strong> 공식 API를 통해 수집된 기사 제목과 요약만 표시합니다. 본문은 원문 링크를 통해 확인하세요.</div>
  <div class="stats">{stats_chips}</div>
  {sections_html}
</div>

<footer class="footer">
  수집 출처: 네이버 뉴스 검색 API &nbsp;|&nbsp; 제목·요약·링크만 수집, 본문 저장·재배포 없음<br/>
  한국식품산업클러스터진흥원 &nbsp;|&nbsp; 자동 생성: {datetime_full}
</footer>

<script>
// ── 페이지 상태 초기화 ──
{js_init}

function goPage(catId, page, total) {{
  if (page < 0 || page >= total) return;

  // 현재 페이지 숨기기
  var cur = window["__pg_" + catId];
  var curEl = document.getElementById(catId + "-p" + cur);
  if (curEl) curEl.style.display = "none";
  var curBtn = document.getElementById(catId + "-btn" + cur);
  if (curBtn) curBtn.className = "pg-btn";

  // 새 페이지 보이기
  var newEl = document.getElementById(catId + "-p" + page);
  if (newEl) newEl.style.display = "block";
  var newBtn = document.getElementById(catId + "-btn" + page);
  if (newBtn) newBtn.className = "pg-btn pg-active";

  window["__pg_" + catId] = page;

  // 페이지 정보 업데이트
  var info = document.getElementById(catId + "-info");
  if (info) info.textContent = (page+1) + " / " + total + " 페이지";

  // 해당 섹션 상단으로 스크롤
  var sec = newEl.closest(".section");
  if (sec) sec.scrollIntoView({{behavior:"smooth", block:"nearest"}});
}}

// ── 카운트다운 타이머 ──
var NEXT_TS = {next_collect_ts};
var INTERVAL = 15 * 60;  // 15분 = 900초

function tick() {{
  var now = Math.floor(Date.now() / 1000);

  // 현재 시각이 NEXT_TS를 지나면 다음 15분 단위로 자동 갱신
  while (now >= NEXT_TS) {{
    NEXT_TS += INTERVAL;
  }}

  var remaining = NEXT_TS - now;
  var m = String(Math.floor(remaining / 60)).padStart(2, "0");
  var s = String(remaining % 60).padStart(2, "0");
  document.getElementById("cd-min").textContent = m;
  document.getElementById("cd-sec").textContent = s;
  var pct = (remaining / INTERVAL) * 100;
  document.getElementById("prog").style.width = pct + "%";
}}
tick();
setInterval(tick, 1000);
</script>
</body>
</html>"""

    os.makedirs(output_dir, exist_ok=True)
    timestamp = now.strftime("%Y%m%d_%H%M")
    for path in [
        os.path.join(output_dir, f"briefing_{timestamp}.html"),
        os.path.join(output_dir, "latest.html"),
    ]:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    return os.path.join(output_dir, f"briefing_{timestamp}.html")
