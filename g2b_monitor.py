"""
나라장터(G2B) 입찰공고 모니터링 프로그램
- 5분마다 건강보험심사평가원 클라우드 관련 입찰공고 건수를 체크
- 변경 시 Windows 토스트 알림 발송
- 세부절차상태 변경 시 Discord 웹훅 알림 발송
- 상태는 state.json 파일에 저장

[주의] JSESSIONID 등 세션 쿠키는 일정 시간 후 만료됩니다.
       만료 시 config.json 의 cookies.JSESSIONID 값을 업데이트하세요.

실행 방법:
  python g2b_monitor.py           # 5분 주기 모니터링 루프
  python g2b_monitor.py --state   # 세부절차상태 1회 체크 후 종료
"""

import requests
import json
import time
import logging
import subprocess
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple, List, Set, Dict
from winotify import Notification


# ─────────────────────────────────────────────
# 고정 설정값
# ─────────────────────────────────────────────
INTERVAL_SECONDS = 5 * 60
STATE_FILE  = Path("state.json")
LOG_FILE    = Path("g2b_monitor.log")
CONFIG_FILE = Path("config.json")

# Discord embed 색상
COLOR_STATUS_CHANGED = 0xFF8C00
COLOR_NEW_BID        = 0x57F287
COLOR_INFO           = 0x5865F2

# 세부절차상태 필드 — "사업처리진행구분명" ("진행중"/"진행완료" 등)
STATUS_FIELD = "bsnePrssPrgrsSeNm"

URL = "https://www.g2b.go.kr/pn/pnp/pnpe/BidPbac/selectBidPbacScrollTypeList.do"

HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Content-Type": "application/json;charset=UTF-8",
    "Menu-Info": '{"menuNo":"01175","menuCangVal":"PNPE001_01","bsneClsfCd":"%EC%97%85130026","scrnNo":"00941"}',
    "Origin": "https://www.g2b.go.kr",
    "Referer": "https://www.g2b.go.kr/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Target-Id": "btnS0004",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/30.0 Chrome/143.0.0.0 Safari/537.36",
    "Usr-Id": "null",
    "sec-ch-ua": '"Not=A?Brand";v="8", "Chromium";v="143", "Samsung Browser";v="30.0"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "submissionid": "mf_wfm_container_tacBidPbancLst_contents_tab2_body_sbmPbancBidPbancLst",
}

# ─────────────────────────────────────────────
# config.json 로드 — COOKIES, PAYLOAD, Discord URL
# ─────────────────────────────────────────────
def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"{CONFIG_FILE} 파일이 없습니다. "
            "config.json.example 을 참고해 config.json 을 생성하세요."
        )
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))

_config = load_config()
DISCORD_WEBHOOK_URL: str      = _config["discord_webhook_url"]
COOKIES: dict                 = _config["cookies"]
PAYLOAD: dict                 = _config["payload"]

# ─────────────────────────────────────────────
# 로깅 설정
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Discord 웹훅 알림
# ─────────────────────────────────────────────
def send_discord(title: str, description: str, color: int = COLOR_INFO, fields: Optional[List[dict]] = None) -> bool:
    embed: dict = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "나라장터 G2B 모니터"},
    }
    if fields:
        embed["fields"] = fields

    try:
        resp = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"embeds": [embed]},
            timeout=10,
        )
        resp.raise_for_status()
        logger.info(f"[Discord] {title}")
        return True
    except Exception as e:
        logger.error(f"Discord 알림 실패: {e}")
        return False


# ─────────────────────────────────────────────
# Windows 토스트 알림
# ─────────────────────────────────────────────
def send_toast(title: str, message: str) -> None:
    toast = Notification(
        app_id="G2B Monitor",
        title=title,
        msg=message,
        duration="long",
    )
    toast.show()

def send_toast2(title: str, message: str) -> None:
    """Windows 알림 센터에 토스트 알림을 발송합니다."""
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=10, threaded=True)
        logger.info(f"[토스트] {title} — {message}")
        return
    except ImportError:
        pass

    try:
        ps_script = (
            f"Import-Module BurntToast -ErrorAction SilentlyContinue; "
            f"New-BurntToastNotification -Text '{title}', '{message}'"
        )
        subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            timeout=10,
        )
        logger.info(f"[PowerShell 토스트] {title} — {message}")
        return
    except Exception:
        pass

    try:
        ps_script = (
            f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; "
            f"$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
            f"[Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
            f"$textNodes = $template.GetElementsByTagName('text'); "
            f"$textNodes.Item(0).AppendChild($template.CreateTextNode('{title}')) | Out-Null; "
            f"$textNodes.Item(1).AppendChild($template.CreateTextNode('{message}')) | Out-Null; "
            f"$toast = [Windows.UI.Notifications.ToastNotification]::new($template); "
            f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('G2B Monitor').Show($toast);"
        )
        subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            timeout=10,
        )
        logger.info(f"[WinRT 토스트] {title} — {message}")
        return
    except Exception as e:
        logger.warning(f"모든 토스트 방법 실패: {e}")

    print(f"\n{'='*50}")
    print(f"🔔 알림: {title}")
    print(f"   {message}")
    print(f"{'='*50}\n")


# ─────────────────────────────────────────────
# 상태 저장/로드
# ─────────────────────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ─────────────────────────────────────────────
# API 호출 및 건수 추출
# ─────────────────────────────────────────────
def fetch_bid_count() -> Tuple[Optional[int], List]:
    """G2B API를 호출하여 (총 공고 건수, 공고 목록)을 반환합니다. 실패 시 (None, [])."""
    try:
        resp = requests.post(
            URL,
            headers=HEADERS,
            cookies=COOKIES,
            json=PAYLOAD,
            timeout=30,
            verify=True,
        )
        resp.raise_for_status()
        data = resp.json()

        inner = data.get("dlBidPbancLstM", data)

        count = None
        for key in ("totCnt", "totalCount", "totalCnt", "cnt", "count"):
            if key in inner:
                count = int(inner[key])
                break

        bid_list = inner.get("result", [])

        if count is None:
            count = len(bid_list)

        # 최초 1회: 응답 필드명을 로그에 기록 (세부절차상태 필드 파악용)
        if bid_list:
            logger.debug(f"응답 필드 목록: {list(bid_list[0].keys())}")

        return count, bid_list

    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code in (401, 403):
            logger.error("세션 만료 또는 인증 오류 (401/403). JSESSIONID 쿠키를 갱신하세요.")
            send_toast("⚠️ G2B 세션 만료", "JSESSIONID 쿠키를 갱신해야 합니다.")
        else:
            logger.error(f"HTTP 오류: {e}")
        return None, []
    except requests.exceptions.ConnectionError:
        logger.error("네트워크 연결 오류. 인터넷 연결을 확인하세요.")
        return None, []
    except requests.exceptions.Timeout:
        logger.error("요청 타임아웃 (30초 초과)")
        return None, []
    except Exception as e:
        logger.error(f"예상치 못한 오류: {e}")
        return None, []


# ─────────────────────────────────────────────
# 세부절차상태 관련 유틸
# ─────────────────────────────────────────────
def get_bid_status(bid: dict) -> Optional[str]:
    """공고 dict에서 세부절차상태(사업처리진행구분명)를 추출합니다."""
    val = bid.get(STATUS_FIELD)
    return str(val) if val is not None else None


def check_and_notify_status_changes(
    bid_list: List[dict],
    prev_statuses: Dict[str, str],
) -> Dict[str, str]:
    """
    각 공고의 세부절차상태를 이전 상태와 비교하여 변경분을 Discord로 알립니다.
    현재 상태 dict {bid_id: status}를 반환합니다.
    """
    current_statuses: Dict[str, str] = {}
    changed = []

    for bid in bid_list:
        bid_id = str(bid.get("bidPbancNo") or bid.get("untyBidPbancNo") or "")
        if not bid_id:
            continue
        status = get_bid_status(bid)
        if status is None:
            continue
        current_statuses[bid_id] = status

        prev = prev_statuses.get(bid_id)
        if prev is not None and prev != status:
            changed.append({
                "id": bid_id,
                "title": bid.get("bidPbancNm") or "제목 없음",
                "prev": prev,
                "curr": status,
            })

    if changed:
        desc_lines = []
        for c in changed:
            desc_lines.append(f"**{c['title']}**\n공고번호: `{c['id']}`\n`{c['prev']}` → **`{c['curr']}`**")
        send_discord(
            title="🔄 세부절차상태 변경",
            description="\n\n".join(desc_lines),
            color=COLOR_STATUS_CHANGED,
        )
        logger.info(f"세부절차상태 변경 {len(changed)}건 감지 → Discord 알림 발송")

    return current_statuses


# ─────────────────────────────────────────────
# 새 공고 상세 내용 포맷
# ─────────────────────────────────────────────
def format_new_bids(new_bids: list) -> str:
    if not new_bids:
        return ""
    lines = []
    for bid in new_bids[:3]:
        title = bid.get("bidPbancNm") or bid.get("title") or "제목 없음"
        no    = bid.get("bidPbancNo") or bid.get("untyBidPbancNo") or ""
        lines.append(f"• {title}" + (f" ({no})" if no else ""))
    if len(new_bids) > 3:
        lines.append(f"  ... 외 {len(new_bids) - 3}건")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# --state 모드: 1회 상태 체크 후 종료
# ─────────────────────────────────────────────
def check_state_once() -> None:
    """세부절차상태를 1회 조회하여 변경 시 Discord 알림 후 종료합니다."""
    logger.info("=" * 60)
    logger.info("[--state 모드] 세부절차상태 1회 체크")
    logger.info("=" * 60)

    state = load_state()
    prev_statuses: Dict[str, str] = state.get("bid_statuses", {})
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    count, bid_list = fetch_bid_count()
    if count is None:
        logger.error("API 조회 실패. 종료합니다.")
        return

    logger.info(f"현재 공고 건수: {count}건")

    if not bid_list:
        logger.info("공고 목록이 비어있습니다.")
        return

    # 세부절차상태 필드 감지 여부 확인
    sample_status = get_bid_status(bid_list[0])
    if sample_status is None:
        available_keys = list(bid_list[0].keys())
        logger.warning(
            f"세부절차상태 필드 '{STATUS_FIELD}'를 찾지 못했습니다. "
            f"응답 필드 목록: {available_keys}"
        )

    current_statuses = check_and_notify_status_changes(bid_list, prev_statuses)

    if not current_statuses:
        logger.info("세부절차상태를 추적할 수 있는 공고가 없습니다.")
    else:
        logger.info(f"상태 추적 중인 공고 {len(current_statuses)}건:")
        for bid_id, status in current_statuses.items():
            prev = prev_statuses.get(bid_id, "(신규)")
            changed_mark = " ← 변경됨" if prev != "(신규)" and prev != status else ""
            logger.info(f"  {bid_id}: {status}{changed_mark}")

    # 상태 저장
    state["bid_statuses"] = current_statuses
    state["last_check"] = now
    save_state(state)
    logger.info("상태 저장 완료. 종료합니다.")


# ─────────────────────────────────────────────
# 메인 모니터링 루프
# ─────────────────────────────────────────────
def monitor() -> None:
    logger.info("=" * 60)
    logger.info("나라장터 입찰공고 모니터링 시작")
    logger.info(f"검색 조건: 건강보험심사평가원 / 클라우드 / 공개경쟁")
    logger.info(f"체크 주기: {INTERVAL_SECONDS // 60}분")
    logger.info("=" * 60)

    state = load_state()
    prev_count: Optional[int] = state.get("count")
    prev_ids: Set[str] = set(state.get("bid_ids", []))
    prev_statuses: Dict[str, str] = state.get("bid_statuses", {})

    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"[{now}] API 조회 중...")

        count, bid_list = fetch_bid_count()

        if count is None:
            logger.warning("조회 실패 — 다음 주기에 재시도합니다.")
        else:
            logger.info(f"현재 공고 건수: {count}건 (이전: {prev_count}건)")

            current_ids = set()
            for bid in bid_list:
                bid_id = bid.get("bidPbancNo") or bid.get("untyBidPbancNo")
                if bid_id:
                    current_ids.add(str(bid_id))

            new_bids = [
                b for b in bid_list
                if str(b.get("bidPbancNo") or b.get("untyBidPbancNo") or "") not in prev_ids
            ]

            if prev_count is None:
                logger.info(f"최초 실행: 기준값 {count}건 저장")
                send_toast(
                    "🔍 G2B 모니터링 시작",
                    f"현재 공고 {count}건 기준으로 모니터링합니다.",
                )
            elif count != prev_count:
                diff = count - prev_count
                sign = "+" if diff > 0 else ""
                msg_title = f"📢 나라장터 공고 변경 ({sign}{diff}건)"
                msg_body = f"건강보험심사평가원 클라우드 공고: {prev_count}건 → {count}건"

                if new_bids:
                    new_bid_text = format_new_bids(new_bids)
                    msg_body += f"\n\n신규 공고:\n{new_bid_text}"
                    logger.info(f"신규 공고 {len(new_bids)}건 감지")
                    # 신규 공고도 Discord에 알림
                    discord_fields = [
                        {"name": "공고번호", "value": b.get("bidPbancNo") or b.get("untyBidPbancNo") or "-", "inline": True}
                        for b in new_bids[:5]
                    ]
                    send_discord(
                        title=f"📢 신규 공고 {len(new_bids)}건",
                        description=new_bid_text,
                        color=COLOR_NEW_BID,
                    )

                logger.info(f"변경 감지! {msg_body}")
                send_toast(msg_title, f"건강보험심사평가원 클라우드 공고: {prev_count}→{count}건")
            else:
                logger.info("변경 없음.")

            # 세부절차상태 변경 체크
            current_statuses = check_and_notify_status_changes(bid_list, prev_statuses)
            prev_statuses = current_statuses if current_statuses else prev_statuses

            # 상태 업데이트
            prev_count = count
            prev_ids = current_ids if current_ids else prev_ids
            save_state({
                "count": prev_count,
                "bid_ids": list(prev_ids),
                "bid_statuses": prev_statuses,
                "last_check": now,
            })

        logger.info(f"다음 체크: {INTERVAL_SECONDS // 60}분 후")
        time.sleep(INTERVAL_SECONDS)


# ─────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="나라장터 입찰공고 모니터")
    parser.add_argument(
        "--state",
        action="store_true",
        help="세부절차상태를 1회 체크하고 변경 시 Discord 알림 후 종료",
    )
    args = parser.parse_args()

    try:
        if args.state:
            check_state_once()
        else:
            monitor()
    except KeyboardInterrupt:
        logger.info("모니터링 종료 (Ctrl+C)")
