# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

나라장터(G2B) 입찰공고 모니터 — a Windows Python script that polls the Korean government procurement API every 5 minutes and fires a Windows toast notification when bid counts change.

## Running

```powershell
# Start the monitor (runs indefinitely)
python g2b_monitor.py

# 세부절차상태 1회 체크 후 종료 (변경 시 Discord 알림)
python g2b_monitor.py --state

# Diagnose Windows toast notification issues
python toast_diagnostic.py
```

## Dependencies

```powershell
pip install requests winotify win10toast
# Optional: Install-Module BurntToast -Force  (PowerShell admin)
```

## Architecture

**`g2b_monitor.py`** — single-file monitor with these layers:
- `fetch_bid_count()` — POSTs to the G2B JSON API, extracts `totCnt` from `dlBidPbancLstM` response envelope
- `send_toast()` — primary path via `winotify`; `send_toast2()` is a legacy fallback chain (win10toast → BurntToast → WinRT PowerShell → console)
- `send_discord()` — Discord 웹훅으로 embed 메시지 발송 (세부절차상태 변경, 신규 공고 알림)
- `get_bid_status()` — 공고 dict에서 세부절차상태 필드를 후보 목록으로 탐색 추출
- `check_and_notify_status_changes()` — 이전/현재 세부절차상태 비교 후 변경분 Discord 알림
- `load_state()` / `save_state()` — persists `{count, bid_ids, bid_statuses, last_check}` in `state.json` across restarts
- `monitor()` — infinite loop: fetch → diff against state → notify on change → sleep 5 min
- `check_state_once()` — `--state` 모드: 1회 조회 → 세부절차상태 비교 → 알림 → 종료

**`toast_diagnostic.py`** — standalone script that tests all notification methods (win10toast, WinRT PowerShell, BurntToast, registry settings, Focus Assist) and prints pass/fail for each.

**`state.json`** — runtime state file, not config. Tracks previous bid count and individual bid IDs (`bidPbancNo`) to detect new entries even when total count doesn't change.

## Session cookie maintenance

`JSESSIONID` in the `COOKIES` dict expires periodically. When the monitor logs a 401/403 or fires a "세션 만료" toast:
1. Open 나라장터 in a browser
2. Open DevTools → Network tab → find any XHR request → copy the `Cookie` header
3. Update `COOKIES["JSESSIONID"]` in `g2b_monitor.py`

## Search parameters

The `PAYLOAD["dlBidPbancLstM"]` dict controls what bids are monitored:
- `bidPbancNm: "클라우드"` — keyword filter
- `dmstNm: "건강보험심사평가원"` — contracting agency
- `fromBidDt` / `toBidDt` — date window (format: `YYYYMMDD`), update when extending the monitoring period
- `pbancKndCd: "공440002"` — public competitive bid type
