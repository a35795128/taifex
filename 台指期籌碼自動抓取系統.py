#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台指期籌碼自動抓取系統 v7
新增：週選支撐壓力、histock 月選支撐壓力
"""

import os, json, time, requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# ────────────────────────────────────────────
# 設定區
# ────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE   = os.path.join(BASE_DIR, "歷史快取.json")
KEY_FILE       = os.path.join(BASE_DIR, "google金鑰.json")
SPREADSHEET_ID = "1X7WrPCRSni0bubmh7_VlTWAm-eMIAXKbUUpkXhkUPdk"

def get_headers(referer="https://www.taifex.com.tw/"):
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer":    referer,
        "Accept":     "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://www.taifex.com.tw",
    }

# ────────────────────────────────────────────
# 工具函數
# ────────────────────────────────────────────
def safe_int(s):
    try:
        return int(str(s).replace(",","").replace(" ","").replace("\xa0","").strip())
    except:
        return 0

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_history(data):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def prev_weekday(dt):
    d = dt - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d

def calc_diff(today, yesterday):
    if isinstance(today, dict):
        return {k: calc_diff(today[k], yesterday.get(k, 0) if isinstance(yesterday, dict) else 0)
                for k in today}
    if isinstance(today, (int, float)):
        y = yesterday if isinstance(yesterday, (int, float)) else 0
        return today - y
    return today

# ────────────────────────────────────────────
# 1. 抓期貨未平倉餘額
# ────────────────────────────────────────────
def fetch_futures(date_str):
    url = "https://www.taifex.com.tw/cht/3/futContractsDate"
    products = {"TXF":"大台", "MXF":"小台", "TMF":"微台"}
    result = {name: {"外資":{"多單":0,"空單":0}, "自營":{"多單":0,"空單":0}}
              for name in products.values()}

    s = requests.Session()
    s.get(url, headers=get_headers(url), timeout=20)
    time.sleep(0.5)

    for code, name in products.items():
        try:
            resp = s.post(url, timeout=20, headers=get_headers(url),
                          data={"queryStartDate":date_str, "queryEndDate":date_str, "commodityId":code})
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")

            target_table = None
            for t in soup.find_all("table"):
                if "未平倉" in t.get_text():
                    target_table = t
                    break

            if not target_table:
                print(f"  ⚠️  {name} 今日無資料")
                continue

            for row in target_table.find_all("tr"):
                tds = row.find_all("td")
                texts = [td.get_text(strip=True) for td in tds]
                n = len(tds)
                row_text = " ".join(texts)

                if n == 15 and "自營商" in row_text:
                    result[name]["自營"]["多單"] = safe_int(texts[9])
                    result[name]["自營"]["空單"] = safe_int(texts[11])
                elif n == 13 and ("外資及陸資" in row_text or "外資" in row_text):
                    result[name]["外資"]["多單"] = safe_int(texts[7])
                    result[name]["外資"]["空單"] = safe_int(texts[9])

            print(f"  ✅ {name}  外資多:{result[name]['外資']['多單']:,} 空:{result[name]['外資']['空單']:,}  "
                  f"自營多:{result[name]['自營']['多單']:,} 空:{result[name]['自營']['空單']:,}")
            time.sleep(0.8)

        except Exception as e:
            print(f"  ❌ {name} 失敗：{e}")

    return result

# ────────────────────────────────────────────
# 2. 抓選擇權未平倉餘額
# ────────────────────────────────────────────
def fetch_options(date_str):
    url = "https://www.taifex.com.tw/cht/3/callsAndPutsDate"
    result = {
        "外資": {"BC":0,"SC":0,"BP":0,"SP":0},
        "自營": {"BC":0,"SC":0,"BP":0,"SP":0},
    }

    s = requests.Session()
    s.get(url, headers=get_headers(url), timeout=20)
    time.sleep(0.5)

    try:
        resp = s.post(url, timeout=20, headers=get_headers(url),
                      data={"queryStartDate":date_str, "queryEndDate":date_str, "commodityId":"TXO"})
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        target_table = None
        for t in soup.find_all("table"):
            txt = t.get_text()
            if "自營商" in txt and "買權" in txt and "賣權" in txt:
                target_table = t
                break

        if not target_table:
            print("  ⚠️  選擇權今日無資料")
            return result

        current_type = None
        for row in target_table.find_all("tr"):
            tds = row.find_all("td")
            texts = [td.get_text(strip=True) for td in tds]
            n = len(tds)
            row_text = " ".join(texts)

            if "買權" in row_text:
                current_type = "call"
            elif "賣權" in row_text:
                current_type = "put"

            if current_type is None:
                continue

            if current_type == "call":
                if n == 16 and "自營商" in row_text:
                    result["自營"]["BC"] = safe_int(texts[10])
                    result["自營"]["SC"] = safe_int(texts[12])
                elif n == 13 and "外資" in row_text and "投信" not in row_text:
                    result["外資"]["BC"] = safe_int(texts[7])
                    result["外資"]["SC"] = safe_int(texts[9])
            elif current_type == "put":
                if n == 14 and "自營商" in row_text:
                    result["自營"]["BP"] = safe_int(texts[8])
                    result["自營"]["SP"] = safe_int(texts[10])
                elif n == 13 and "外資" in row_text and "投信" not in row_text:
                    result["外資"]["BP"] = safe_int(texts[7])
                    result["外資"]["SP"] = safe_int(texts[9])

        print(f"  ✅ 外資選擇權  BC:{result['外資']['BC']:,} SC:{result['外資']['SC']:,} "
              f"BP:{result['外資']['BP']:,} SP:{result['外資']['SP']:,}")
        print(f"  ✅ 自營選擇權  BC:{result['自營']['BC']:,} SC:{result['自營']['SC']:,} "
              f"BP:{result['自營']['BP']:,} SP:{result['自營']['SP']:,}")

    except Exception as e:
        print(f"  ❌ 選擇權失敗：{e}")

    return result

# ────────────────────────────────────────────
# 3a. 抓月選支撐壓力（從 histock）
# ────────────────────────────────────────────
def fetch_support_resistance(date_str):
    url = "https://histock.tw/stock/option.aspx?m=month"
    result = {}

    try:
        s = requests.Session()
        resp = s.get(url, headers=get_headers("https://histock.tw/"), timeout=20)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        table = soup.find("table", class_="tb-stock")
        if not table:
            print("  ⚠️  找不到月選支撐壓力表格")
            return []

        rows = table.find_all("tr")
        for row in rows:
            tds = row.find_all("td")
            if not tds:
                continue
            
            texts = [td.get_text(strip=True) for td in tds]
            
            strike_th = row.find("th")
            if not strike_th:
                continue
            
            strike_text = strike_th.get_text(strip=True).replace(",", "").replace("@", "")
            
            try:
                strike = int(float(strike_text))
            except:
                continue
            
            if strike < 1000 or strike > 100000:
                continue
            
            if len(texts) < 14:
                continue
            
            call_oi = safe_int(texts[6])
            put_oi = safe_int(texts[13])
            
            result[strike] = {"call_oi": call_oi, "put_oi": put_oi}

        sr_list = [{"履約價":k, "call_oi":v["call_oi"], "put_oi":v["put_oi"]}
                   for k, v in sorted(result.items())
                   if v["call_oi"] + v["put_oi"] > 0]

        print(f"  ✅ 月選支撐壓力：抓到 {len(sr_list)} 個履約價")
        return sr_list

    except Exception as e:
        print(f"  ❌ 月選支撐壓力失敗：{e}")
        return []

# ────────────────────────────────────────────
# 3b. 抓週選支撐壓力（從 histock）
# ────────────────────────────────────────────
def fetch_weekly_support_resistance(date_str):
    url = "https://histock.tw/stock/option.aspx?m=week"
    result = {}

    try:
        s = requests.Session()
        resp = s.get(url, headers=get_headers("https://histock.tw/"), timeout=20)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        table = soup.find("table", class_="tb-stock")
        if not table:
            print("  ⚠️  找不到週選支撐壓力表格")
            return []

        rows = table.find_all("tr")
        for row in rows:
            tds = row.find_all("td")
            if not tds:
                continue
            
            texts = [td.get_text(strip=True) for td in tds]
            
            strike_th = row.find("th")
            if not strike_th:
                continue
            
            strike_text = strike_th.get_text(strip=True).replace(",", "").replace("@", "")
            
            try:
                strike = int(float(strike_text))
            except:
                continue
            
            if strike < 1000 or strike > 100000:
                continue
            
            if len(texts) < 14:
                continue
            
            call_oi = safe_int(texts[6])
            put_oi = safe_int(texts[13])
            
            result[strike] = {"call_oi": call_oi, "put_oi": put_oi}

        sr_list = [{"履約價":k, "call_oi":v["call_oi"], "put_oi":v["put_oi"]}
                   for k, v in sorted(result.items())
                   if v["call_oi"] + v["put_oi"] > 0]

        print(f"  ✅ 週選支撐壓力：抓到 {len(sr_list)} 個履約價")
        return sr_list

    except Exception as e:
        print(f"  ❌ 週選支撐壓力失敗：{e}")
        return []

# ────────────────────────────────────────────
# 4. GEX 計算
# ────────────────────────────────────────────
def calc_gex(sr_list):
    if not sr_list:
        return []

    result = []
    total_oi = sum(d["call_oi"] + d["put_oi"] for d in sr_list)

    for d in sr_list:
        c    = d["call_oi"]
        p    = d["put_oi"]
        gex  = c - p
        ratio = round(c / p, 2) if p > 0 else 999.0
        weight = round((c + p) / total_oi * 100, 1) if total_oi > 0 else 0

        if ratio > 3.0:     nature = "⬆️強壓力"
        elif ratio > 1.8:   nature = "↑壓力"
        elif ratio > 1.3:   nature = "↑弱壓力"
        elif ratio < 0.33:  nature = "⬇️強支撐"
        elif ratio < 0.6:   nature = "↓支撐"
        elif ratio < 0.77:  nature = "↓弱支撐"
        else:               nature = "－中性"

        result.append({
            **d,
            "gex":      gex,
            "cp_ratio": ratio,
            "weight":   weight,
            "nature":   nature,
        })

    min_abs = min(abs(r["gex"]) for r in result)
    for r in result:
        r["is_zero_gamma"] = (abs(r["gex"]) == min_abs)

    for r in result:
        r["is_big_money"] = r["weight"] >= 5.0

    return result

# ────────────────────────────────────────────
# 5. 產生 TradingView 字串
# ────────────────────────────────────────────
def generate_tv_string(sr_with_gex):
    parts = []
    for d in sorted(sr_with_gex, key=lambda x: x["履約價"], reverse=True):
        ratio = d["cp_ratio"]
        zg    = 1 if d["is_zero_gamma"] else 0
        if ratio > 1.3 or ratio < 0.77 or zg == 1:
            parts.append(
                f"{d['履約價']},{d['call_oi']},{d['put_oi']},{d['gex']},{d['cp_ratio']},{zg}"
            )
    return ";".join(parts)

# ────────────────────────────────────────────
# 6. 連線 Google 試算表
# ────────────────────────────────────────────
def connect_google_sheet():
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        
        creds_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
        
        if creds_json:
            creds_dict = json.loads(creds_json)
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        else:
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(KEY_FILE, scopes=scopes)
        
        client = gspread.authorize(creds)
        sh = client.open_by_key(SPREADSHEET_ID)
        print("  ✅ Google 試算表連線成功")
        return sh
    except Exception as e:
        print(f"  ❌ 連線失敗：{e}")
        return None

# ────────────────────────────────────────────
# 7. 確保工作表存在
# ────────────────────────────────────────────
HEADER_ROW = ["日期","大台多","大台空","小台多","小台空","微台多","微台空","SC","BC","SP","BP"]

def ensure_sheet(sh, name, headers=None):
    headers = headers or HEADER_ROW
    try:
        ws = sh.worksheet(name)
    except:
        ws = sh.add_worksheet(title=name, rows=500, cols=15)
        ws.append_row(headers)
        print(f"  ✅ 新建工作表：{name}")
    return ws

# ────────────────────────────────────────────
# 8. 寫入籌碼資料
# ────────────────────────────────────────────
def write_chips_to_google(sh, date_str, futures_diff, options_diff):
    def gf(product, identity, key):
        return futures_diff.get(product,{}).get(identity,{}).get(key, 0)
    def go(identity, key):
        return options_diff.get(identity,{}).get(key, 0)

    sheets_data = {
        "外資總表": [date_str,
            gf("大台","外資","多單"), gf("大台","外資","空單"),
            gf("小台","外資","多單"), gf("小台","外資","空單"),
            gf("微台","外資","多單"), gf("微台","外資","空單"),
            go("外資","SC"), go("外資","BC"), go("外資","SP"), go("外資","BP")],
        "自營總表": [date_str,
            gf("大台","自營","多單"), gf("大台","自營","空單"),
            gf("小台","自營","多單"), gf("小台","自營","空單"),
            gf("微台","自營","多單"), gf("微台","自營","空單"),
            go("自營","SC"), go("自營","BC"), go("自營","SP"), go("自營","BP")],
    }

    for sheet_name, row_data in sheets_data.items():
        try:
            ws = ensure_sheet(sh, sheet_name)
            all_dates = ws.col_values(1)
            if date_str in all_dates:
                idx = all_dates.index(date_str) + 1
                ws.update(values=[row_data], range_name=f"A{idx}:K{idx}")
                print(f"  🔄 {sheet_name}：更新第{idx}行")
            else:
                ws.append_row(row_data)
                print(f"  ✅ {sheet_name}：新增今日資料")
            time.sleep(1.2)
        except Exception as e:
            print(f"  ❌ {sheet_name} 失敗：{e}")

# ────────────────────────────────────────────
# 9a. 寫入月選支撐壓力
# ────────────────────────────────────────────
def write_sr_to_google(sh, date_str, sr_with_gex):
    if not sr_with_gex:
        print("  ⚠️  無月選支撐壓力資料，跳過")
        return

    try:
        sheet_name = "支撐壓力"
        try:
            ws = sh.worksheet(sheet_name)
            ws.clear()
        except:
            ws = sh.add_worksheet(title=sheet_name, rows=500, cols=12)

        ws.append_row(["📋 月選 TradingView 數據字串（每天複製 A2 這格貼到指標）"])
        tv_string = generate_tv_string(sr_with_gex)
        ws.append_row([tv_string])
        ws.append_row([""])

        headers = ["更新日期","履約價","Call未平倉","Put未平倉","GEX(C-P)","C/P比","佔比%","性質","Zero Gamma","大資金"]
        ws.append_row(headers)

        rows_to_write = []
        for d in sorted(sr_with_gex, key=lambda x: x["履約價"], reverse=True):
            rows_to_write.append([
                date_str,
                d["履約價"],
                d["call_oi"],
                d["put_oi"],
                d["gex"],
                d["cp_ratio"],
                d["weight"],
                d["nature"],
                "✅ 多空分界" if d["is_zero_gamma"] else "",
                "💰 大資金" if d["is_big_money"] else "",
            ])

        if rows_to_write:
            ws.append_rows(rows_to_write)

        top_call = sorted(sr_with_gex, key=lambda x: x["call_oi"], reverse=True)[:3]
        top_put  = sorted(sr_with_gex, key=lambda x: x["put_oi"],  reverse=True)[:3]
        zero_gex = [d for d in sr_with_gex if d["is_zero_gamma"]]
        big_money = [d for d in sr_with_gex if d["is_big_money"]]

        print(f"  ✅ 月選支撐壓力：寫入 {len(rows_to_write)} 筆")
        print(f"  🔴 最大壓力位：{[d['履約價'] for d in top_call]}")
        print(f"  🟢 最大支撐位：{[d['履約價'] for d in top_put]}")
        print(f"  ⚪ Zero Gamma（多空分界）：{[d['履約價'] for d in zero_gex]}")
        print(f"  💰 大資金位置：{[d['履約價'] for d in big_money]}")
        time.sleep(1.2)

    except Exception as e:
        print(f"  ❌ 月選支撐壓力寫入失敗：{e}")

# ────────────────────────────────────────────
# 9b. 寫入週選支撐壓力
# ────────────────────────────────────────────
def write_sr_weekly_to_google(sh, date_str, sr_with_gex):
    if not sr_with_gex:
        print("  ⚠️  無週選支撐壓力資料，跳過")
        return

    try:
        sheet_name = "支撐壓力_週選"
        try:
            ws = sh.worksheet(sheet_name)
            ws.clear()
        except:
            ws = sh.add_worksheet(title=sheet_name, rows=500, cols=12)

        ws.append_row(["📋 週選 TradingView 數據字串（每天複製 A2 這格貼到指標）"])
        tv_string = generate_tv_string(sr_with_gex)
        ws.append_row([tv_string])
        ws.append_row([""])

        headers = ["更新日期","履約價","Call未平倉","Put未平倉","GEX(C-P)","C/P比","佔比%","性質","Zero Gamma","大資金"]
        ws.append_row(headers)

        rows_to_write = []
        for d in sorted(sr_with_gex, key=lambda x: x["履約價"], reverse=True):
            rows_to_write.append([
                date_str,
                d["履約價"],
                d["call_oi"],
                d["put_oi"],
                d["gex"],
                d["cp_ratio"],
                d["weight"],
                d["nature"],
                "✅ 多空分界" if d["is_zero_gamma"] else "",
                "💰 大資金" if d["is_big_money"] else "",
            ])

        if rows_to_write:
            ws.append_rows(rows_to_write)

        print(f"  ✅ 週選支撐壓力：寫入 {len(rows_to_write)} 筆")
        time.sleep(1.2)

    except Exception as e:
        print(f"  ❌ 週選支撐壓力寫入失敗：{e}")

# ────────────────────────────────────────────
# 10. 主程式
# ────────────────────────────────────────────
def main():
    now      = datetime.now()
    today    = now.strftime("%Y/%m/%d")
    prev_day = prev_weekday(now).strftime("%Y/%m/%d")

    print("=" * 55)
    print(f"  台指期籌碼自動抓取 v7  {today}")
    print(f"  計算：今日未平倉 − {prev_day} 未平倉")
    print("=" * 55)

    history = load_history()

    # ── 抓取今日資料 ──
    print("\n📊 抓取期貨未平倉口數...")
    futures_today = fetch_futures(today)

    print("\n📊 抓取選擇權未平倉口數...")
    options_today = fetch_options(today)

    print("\n📊 抓取月選支撐壓力...")
    sr_list = fetch_support_resistance(today)

    print("\n📊 抓取週選支撐壓力...")
    sr_weekly_list = fetch_weekly_support_resistance(today)

    # ── GEX 計算 ──
    print("\n🔢 計算月選 GEX / C/P比 / Zero Gamma...")
    sr_with_gex = calc_gex(sr_list)

    print("🔢 計算週選 GEX / C/P比 / Zero Gamma...")
    sr_weekly_with_gex = calc_gex(sr_weekly_list)

    # ── 存入歷史快取 ──
    history[today] = {"futures": futures_today, "options": options_today}
    sorted_keys = sorted(history.keys())[-90:]
    history = {k: history[k] for k in sorted_keys}
    save_history(history)
    print(f"\n💾 已存入歷史快取（共{len(history)}筆）")

    # ── 計算今日 − 昨日 ──
    print(f"\n🔢 計算期貨增減...")
    y_data       = history.get(prev_day, {})
    futures_diff = calc_diff(futures_today, y_data.get("futures", {}))
    options_diff = calc_diff(options_today, y_data.get("options", {}))

    # ── 寫入 Google 試算表 ──
    print("\n📝 寫入 Google 試算表...")
    sh = connect_google_sheet()
    if sh:
        write_chips_to_google(sh, today, futures_diff, options_diff)
        write_sr_to_google(sh, today, sr_with_gex)
        write_sr_weekly_to_google(sh, today, sr_weekly_with_gex)

    # ── 摘要 ──
    def gf(p,i,k): return futures_diff.get(p,{}).get(i,{}).get(k,0)
    def go(i,k):   return options_diff.get(i,{}).get(k,0)

    print("\n" + "─" * 55)
    print("📋 今日籌碼增減摘要（正=增加  負=減少）")
    print("─" * 55)
    print(f"【外資】大台  多{gf('大台','外資','多單'):+,}  空{gf('大台','外資','空單'):+,}")
    print(f"【外資】小台  多{gf('小台','外資','多單'):+,}  空{gf('小台','外資','空單'):+,}")
    print(f"【外資】微台  多{gf('微台','外資','多單'):+,}  空{gf('微台','外資','空單'):+,}")
    print(f"【外資】選擇權  BC{go('外資','BC'):+,}  SC{go('外資','SC'):+,}  BP{go('外資','BP'):+,}  SP{go('外資','SP'):+,}")
    print("─" * 55)
    print(f"【自營】大台  多{gf('大台','自營','多單'):+,}  空{gf('大台','自營','空單'):+,}")
    print(f"【自營】小台  多{gf('小台','自營','多單'):+,}  空{gf('小台','自營','空單'):+,}")
    print(f"【自營】微台  多{gf('微台','自營','多單'):+,}  空{gf('微台','自營','空單'):+,}")
    print(f"【自營】選擇權  BC{go('自營','BC'):+,}  SC{go('自營','SC'):+,}  BP{go('自營','BP'):+,}  SP{go('自營','SP'):+,}")
    print("─" * 55)
    print("\n✅ 全部完成！")

if __name__ == "__main__":
    main()
    print("\n視窗將在 10 秒後自動關閉...")
    time.sleep(10)
