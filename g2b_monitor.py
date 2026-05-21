"""
나라장터(G2B) 입찰공고 모니터링 프로그램
- 5분마다 건강보험심사평가원 클라우드 관련 입찰공고 건수를 체크
- 변경 시 Windows 토스트 알림 발송
- 상태는 state.json 파일에 저장

[주의] JSESSIONID 등 세션 쿠키는 일정 시간 후 만료됩니다.
       만료 시 브라우저에서 나라장터 접속 후 개발자도구(F12) → Network 탭에서
       새 쿠키 값을 복사하여 COOKIES 딕셔너리를 업데이트하세요.
"""

import requests
import json
import time
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List, Set
from winotify import Notification


# ─────────────────────────────────────────────
# 설정값
# ─────────────────────────────────────────────
INTERVAL_SECONDS = 5 * 60          # 5분
STATE_FILE = Path("state.json")    # 이전 결과 저장 파일
LOG_FILE = Path("g2b_monitor.log") # 로그 파일

# ─────────────────────────────────────────────
# API 요청 설정 (curl 명령에서 변환)
# ─────────────────────────────────────────────
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

# ⚠️ 세션 쿠키 — 만료 시 아래 값을 업데이트하세요
COOKIES = {
    "WHATAP": "x4lkk6d1fico9p",
    "XTVID": "A2604131756295436",
    "infoSysCd": "%EC%A0%95010029",
    "_harry_ref": "",
    "_harry_url": "https://www.g2b.go.kr/",
    "_harry_fid": "hh902405885",
    "xloc": "1920X1080",
    "_harry_lang": "ko-KR",
    "system_language": "ko",
    "lastAccess": "1778462245944",
    "globalDebug": "false",
    "JSESSIONID": "NzMyMjM2N2YtZjVkNC00YjQ2LWJhYjUtNzEwZmViNDNhNzA0",  # ⚠️ 만료 가능
    "poupR23AB00000134631": "done",
}

PAYLOAD = {
    "dlBidPbancLstM": {
        "untyBidPbancNo": "",
        "bidPbancNo": "",
        "bidPbancOrd": "",
        "prcmBsneUntyNoOrd": "",
        "prcmBsneSeCd": "조070002",
        "bidPbancNm": "클라우드",
        #"bidPbancNm": "",
        "pbancPstgDt": "",
        "ldocNoVal": "",
        "bidPrspPrce": "",
        "ctrtDmndRcptNo": "",
        "dmstcOvrsSeCd": "",
        "pbancKndCd": "공440002",
        "ctrtTyCd": "",
        "bidCtrtMthdCd": "",
        "scsbdMthdCd": "",
        "fromBidDt": "20260518",
        "toBidDt": "20260529",
        "minBidPrspPrce": "",
        "maxBidPrspPrce": "",
        "bsneAllYn": "Y",
        "frcpYn": "Y",
        "rsrvYn": "Y",
        "laseYn": "Y",
        "untyGrpGb": "DMST",
        "dmstNm": "건강보험심사평가원",
        "pbancPicNm": "",
        "odnLmtLgdngCd": "",
        "odnLmtLgdngNm": "",
        "intpCd": "",
        "intpNm": "",
        "dtlsPrnmNo": "",
        "dtlsPrnmNm": "",
        "slprRcptDdlnYn": "",
        "lcrtTyCd": "",
        "isMas": "",
        "isElpdt": "",
        "oderInstUntyGrpNo": "",
        "instSearchRangeYn": "",
        "esdacYn": "",
        "infoSysCd": "정010029",
        "contxtSeCd": "콘010006",
        "bidDateType": "R",
        "brcoOrgnCd": "",
        "deptOrgnCd": "",
        "isShop": "",
        "srchTy": "0",
        "cangParmVal": "",
        "currentPage": "",
        "recordCountPerPage": "10",
        "startIndex": 1,
        "endIndex": 10,
    }
}

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
    # 방법 1: win10toast 패키지 (pip install win10toast)
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=10, threaded=True)
        logger.info(f"[토스트] {title} — {message}")
        return
    except ImportError:
        pass

    # 방법 2: PowerShell BurntToast 모듈 (fallback)
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

    # 방법 3: Windows Script Host (최후 fallback)
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

    # 콘솔 출력으로 최종 대체
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
    """
    G2B API를 호출하여 (총 공고 건수, 공고 목록)을 반환합니다.
    실패 시 (None, [])를 반환합니다.
    """
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

        # G2B 응답 구조에서 건수 추출
        # 응답 구조 예: {"dlBidPbancLstM": {"totCnt": 5, "list": [...]}}
        inner = data.get("dlBidPbancLstM", data)
        #print(inner)
        # 총 건수 키 후보 (실제 응답 구조에 따라 자동 탐색)
        count = None
        for key in ("totCnt", "totalCount", "totalCnt", "cnt", "count"):
            if key in inner:
                count = int(inner[key])
                break

        bid_list = inner.get("result", [])
        #print(bid_list)
        # totCnt 키가 없으면 list 길이로 대체
        if count is None:
            count = len(bid_list)
        #    logger.warning("totCnt 키를 찾지 못해 list 길이로 대체합니다.")

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
# 새 공고 상세 내용 포맷
# ─────────────────────────────────────────────
def format_new_bids(new_bids: list) -> str:
    if not new_bids:
        return ""
    lines = []
    for bid in new_bids[:3]:  # 최대 3건만 표시
        title = bid.get("bidPbancNm") or bid.get("title") or "제목 없음"
        no    = bid.get("bidPbancNo") or bid.get("untyBidPbancNo") or ""
        lines.append(f"• {title}" + (f" ({no})" if no else ""))
    if len(new_bids) > 3:
        lines.append(f"  ... 외 {len(new_bids) - 3}건")
    return "\n".join(lines)


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

    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"[{now}] API 조회 중...")

        count, bid_list = fetch_bid_count()

        if count is None:
            logger.warning("조회 실패 — 다음 주기에 재시도합니다.")
        else:
            logger.info(f"현재 공고 건수: {count}건 (이전: {prev_count}건)")

            # 공고번호 목록으로 신규 건 탐지
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
                # 최초 실행 — 기준값 저장
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

                logger.info(f"변경 감지! {msg_body}")
                send_toast(msg_title, f"건강보험심사평가원 클라우드 공고: {prev_count}→{count}건")
            else:
                logger.info("변경 없음.")

            # 상태 업데이트
            prev_count = count
            prev_ids = current_ids if current_ids else prev_ids
            save_state({"count": prev_count, "bid_ids": list(prev_ids), "last_check": now})

        logger.info(f"다음 체크: {INTERVAL_SECONDS // 60}분 후")
        time.sleep(INTERVAL_SECONDS)


# ─────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────
if __name__ == "__main__":
    try:
        monitor()
    except KeyboardInterrupt:
        logger.info("모니터링 종료 (Ctrl+C)")
