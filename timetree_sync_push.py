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
from datetime import date, datetime, timedelta, timezone

import requests
from icalendar import Calendar

EMAIL = os.environ["TIMETREE_EMAIL"]
PASSWORD = os.environ["TIMETREE_PASSWORD"]
CALENDAR_CODE = os.environ["TIMETREE_CALENDAR_CODE"]
GAS_WEBHOOK_URL = os.environ["GAS_WEBHOOK_URL"]
SYNC_SECRET = os.environ["TIMETREE_SYNC_SECRET"]

ICS_PATH = "calendar.ics"
TAIPEI_TZ = timezone(timedelta(hours=8))
SYNC_WINDOW_DAYS = 100  # 只同步「今天」起算 100 天內的行程（含今天），過去的行程不同步


def export_ics():
    # timetree-exporter 安裝後會提供一個同名的指令列工具，
    # 帳號密碼建議用環境變數傳入（工具會自動讀取 TIMETREE_EMAIL / TIMETREE_PASSWORD），
    # 這裡額外用 -e / -c 明確指定信箱與行事曆代碼，避免互動式提示卡住自動化流程。
    env = os.environ.copy()
    env["TIMETREE_EMAIL"] = EMAIL
    env["TIMETREE_PASSWORD"] = PASSWORD

    result = subprocess.run(
        [
            "timetree-exporter",
            "-e", EMAIL,
            "-c", CALENDAR_CODE,
            "-o", ICS_PATH,
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"TimeTree 匯出失敗:\nstdout: {result.stdout}\nstderr: {result.stderr}")


def parse_events():
    with open(ICS_PATH, "rb") as f:
        cal = Calendar.from_ical(f.read())

    today = datetime.now(TAIPEI_TZ).date()
    cutoff = today + timedelta(days=SYNC_WINDOW_DAYS)

    events = []
    skipped_past = 0
    skipped_future = 0

    for component in cal.walk("VEVENT"):
        start = component.get("DTSTART").dt
        end = component.get("DTEND").dt
        all_day = not hasattr(start, "hour")

        # 統一換算成台北時間的日期，才能跟 today / cutoff 比較
        start_date = start if all_day else start.astimezone(TAIPEI_TZ).date()

        if start_date < today:
            skipped_past += 1
            continue
        if start_date > cutoff:
            skipped_future += 1
            continue

        uid = str(component.get("UID"))
        events.append({
            "uid": uid,
            "title": str(component.get("SUMMARY", "")),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "location": str(component.get("LOCATION", "")),
            "allDay": all_day,
        })

    print(f"篩選後保留 {len(events)} 筆（今天 {today} 起 {SYNC_WINDOW_DAYS} 天內），"
          f"略過過去 {skipped_past} 筆、超出範圍 {skipped_future} 筆")
    return events


def push_to_gas(events):
    payload = {
        "source": "timetree_sync",
        "secret": SYNC_SECRET,
        "events": events,
    }
    resp = requests.post(GAS_WEBHOOK_URL, json=payload, timeout=120)
    resp.raise_for_status()
    print(f"已送出 {len(events)} 筆行程到 GAS，回應狀態碼: {resp.status_code}")


def main():
    export_ics()
    events = parse_events()
    push_to_gas(events)


if __name__ == "__main__":
    main()
