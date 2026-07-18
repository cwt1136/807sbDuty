"""
timetree_sync_push.py

用法：
  1. pip install TimeTree-Exporter icalendar requests
  2. 設定環境變數：
       TIMETREE_EMAIL          TimeTree 登入信箱
       TIMETREE_PASSWORD       TimeTree 登入密碼
       TIMETREE_CALENDAR_CODE  行事曆代碼（在 TimeTree 網頁版網址列可找到）
       GAS_WEBHOOK_URL         你的 GAS Web App 網址（doPost 的部署 URL）
       TIMETREE_SYNC_SECRET    跟 GAS 指令碼屬性裡設定的同一組密鑰
  3. 排程執行（例如 GitHub Actions schedule，每 15 分鐘一次）：
       python timetree_sync_push.py

注意：TimeTree-Exporter 是社群逆向工程專案，非官方支援，介面隨時可能失效。
"""

import os
import subprocess
import sys
import requests
from icalendar import Calendar

EMAIL = os.environ["TIMETREE_EMAIL"]
PASSWORD = os.environ["TIMETREE_PASSWORD"]
CALENDAR_CODE = os.environ["TIMETREE_CALENDAR_CODE"]
GAS_WEBHOOK_URL = os.environ["GAS_WEBHOOK_URL"]
SYNC_SECRET = os.environ["TIMETREE_SYNC_SECRET"]

ICS_PATH = "calendar.ics"


def export_ics():
    # 呼叫 TimeTree-Exporter CLI 產生 ICS（實際參數請以套件當前文件為準）
    result = subprocess.run(
        [
            sys.executable, "-m", "timetree_exporter",
            "-e", EMAIL,
            "-p", PASSWORD,
            "-c", CALENDAR_CODE,
            "-o", ICS_PATH,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"TimeTree 匯出失敗: {result.stderr}")


def parse_events():
    with open(ICS_PATH, "rb") as f:
        cal = Calendar.from_ical(f.read())

    events = []
    for component in cal.walk("VEVENT"):
        uid = str(component.get("UID"))
        start = component.get("DTSTART").dt
        end = component.get("DTEND").dt
        all_day = not hasattr(start, "hour")

        events.append({
            "uid": uid,
            "title": str(component.get("SUMMARY", "")),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "location": str(component.get("LOCATION", "")),
            "allDay": all_day,
        })
    return events


def push_to_gas(events):
    payload = {
        "source": "timetree_sync",
        "secret": SYNC_SECRET,
        "events": events,
    }
    resp = requests.post(GAS_WEBHOOK_URL, json=payload, timeout=30)
    resp.raise_for_status()
    print(f"已送出 {len(events)} 筆行程到 GAS，回應狀態碼: {resp.status_code}")


def main():
    export_ics()
    events = parse_events()
    push_to_gas(events)


if __name__ == "__main__":
    main()
