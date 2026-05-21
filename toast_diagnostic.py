"""
Windows 토스트 알림 진단 스크립트
각 방법을 순서대로 시도하고 결과를 출력합니다.
실행: python toast_diagnostic.py
"""
import subprocess
import sys

print("=" * 60)
print("Windows 토스트 알림 진단")
print("=" * 60)

# ─────────────────────────────────────────────
# 진단 1: win10toast 패키지
# ─────────────────────────────────────────────
print("\n[1] win10toast 패키지 확인...")
try:
    from win10toast import ToastNotifier
    print("   ✅ win10toast 설치됨 — 알림 시도 중...")
    toaster = ToastNotifier()
    result = toaster.show_toast(
        "G2B 진단 1/3",
        "win10toast 방식 테스트입니다.",
        duration=5,
        threaded=True,
    )
    import time; time.sleep(6)
    print("   ✅ win10toast 알림 전송 완료 (화면에 떴나요?)")
except ImportError:
    print("   ❌ win10toast 미설치 → pip install win10toast 로 설치하세요")
except Exception as e:
    print(f"   ❌ win10toast 오류: {e}")

# ─────────────────────────────────────────────
# 진단 2: PowerShell WinRT (BurntToast 없이)
# ─────────────────────────────────────────────
print("\n[2] PowerShell WinRT 방식 확인...")
ps_script = r"""
[Windows.UI.Notifications.ToastNotificationManager,
 Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
    [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$nodes = $template.GetElementsByTagName('text')
$nodes.Item(0).AppendChild($template.CreateTextNode('G2B 진단 2/3')) | Out-Null
$nodes.Item(1).AppendChild($template.CreateTextNode('PowerShell WinRT 방식 테스트')) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('G2B Monitor')
$notifier.Show($toast)
Write-Output "SUCCESS"
"""
try:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True, text=True, timeout=15
    )
    if "SUCCESS" in result.stdout:
        print("   ✅ PowerShell WinRT 알림 전송 완료 (화면에 떴나요?)")
    else:
        print(f"   ❌ PowerShell WinRT 실패")
        print(f"      stdout: {result.stdout.strip()}")
        print(f"      stderr: {result.stderr.strip()[:200]}")
except Exception as e:
    print(f"   ❌ PowerShell 실행 오류: {e}")

# ─────────────────────────────────────────────
# 진단 3: PowerShell BurntToast 모듈
# ─────────────────────────────────────────────
print("\n[3] PowerShell BurntToast 모듈 확인...")
check_script = "if (Get-Module -ListAvailable -Name BurntToast) { Write-Output 'FOUND' } else { Write-Output 'NOT_FOUND' }"
try:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", check_script],
        capture_output=True, text=True, timeout=10
    )
    if "FOUND" in result.stdout:
        print("   ✅ BurntToast 설치됨 — 알림 시도 중...")
        toast_script = "Import-Module BurntToast; New-BurntToastNotification -Text 'G2B 진단 3/3', 'BurntToast 방식 테스트'; Write-Output 'SUCCESS'"
        r2 = subprocess.run(
            ["powershell", "-NoProfile", "-Command", toast_script],
            capture_output=True, text=True, timeout=15
        )
        if "SUCCESS" in r2.stdout:
            print("   ✅ BurntToast 알림 전송 완료")
        else:
            print(f"   ❌ BurntToast 실행 실패: {r2.stderr.strip()[:200]}")
    else:
        print("   ℹ️  BurntToast 미설치 (선택사항)")
        print("      설치하려면 PowerShell(관리자)에서: Install-Module BurntToast -Force")
except Exception as e:
    print(f"   ❌ BurntToast 확인 오류: {e}")

# ─────────────────────────────────────────────
# 진단 4: Windows 알림 설정 확인
# ─────────────────────────────────────────────
print("\n[4] Windows 알림 레지스트리 설정 확인...")
reg_script = r"""
$path = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\PushNotifications'
$val  = (Get-ItemProperty -Path $path -Name 'ToastEnabled' -ErrorAction SilentlyContinue).ToastEnabled
if ($null -eq $val) { Write-Output 'DEFAULT_ON' }
elseif ($val -eq 1)  { Write-Output 'ENABLED' }
else                 { Write-Output 'DISABLED' }
"""
try:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", reg_script],
        capture_output=True, text=True, timeout=10
    )
    status = result.stdout.strip()
    if status in ("ENABLED", "DEFAULT_ON"):
        print(f"   ✅ Windows 알림 설정: 활성화됨 ({status})")
    else:
        print("   ❌ Windows 알림이 시스템 설정에서 비활성화돼 있습니다!")
        print("      설정 → 시스템 → 알림 → '앱 알림 받기' 를 켜세요.")
except Exception as e:
    print(f"   ❌ 레지스트리 확인 오류: {e}")

# ─────────────────────────────────────────────
# 진단 5: Focus Assist (집중 지원) 상태
# ─────────────────────────────────────────────
print("\n[5] Focus Assist (집중 지원) 상태 확인...")
focus_script = r"""
$path = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\CloudStore\Store\DefaultAccount\Current\default$windows.data.notifications.quiethourssettings\windows.data.notifications.quiethourssettings'
if (Test-Path $path) { Write-Output 'QUIET_HOURS_ACTIVE' }
else { Write-Output 'QUIET_HOURS_OFF' }
"""
try:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", focus_script],
        capture_output=True, text=True, timeout=10
    )
    status = result.stdout.strip()
    if "OFF" in status:
        print("   ✅ 집중 지원 비활성화 — 알림 차단 없음")
    else:
        print("   ⚠️  집중 지원이 활성화 중일 수 있습니다.")
        print("      우측 하단 알림 센터(🌙)를 클릭해서 집중 지원을 끄세요.")
except Exception as e:
    print(f"   ℹ️  집중 지원 확인 불가: {e}")

# ─────────────────────────────────────────────
# Python / Windows 버전 정보
# ─────────────────────────────────────────────
print("\n[정보]")
print(f"   Python 버전: {sys.version}")
try:
    ver = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "[System.Environment]::OSVersion.Version.ToString()"],
        capture_output=True, text=True, timeout=5
    )
    print(f"   Windows 버전: {ver.stdout.strip()}")
except Exception:
    pass

print("\n" + "=" * 60)
print("진단 완료. 위 결과를 확인하세요.")
print("=" * 60)
