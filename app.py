import streamlit as st
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# =========================
# Supabase設定
# =========================
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "https://uguwadlazrawhxkdtkhl.supabase.co")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "sb_publishable_r6wvPjR4FWfoJAWEKTiB5A_A-w1UWZv")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

APP_PASSWORD = st.secrets.get("APP_PASSWORD", "mahjong")
ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", "19831219")


# =========================
# Supabase API
# =========================
def api_get(table, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    response = requests.get(url, headers=HEADERS, params=params or {})
    if response.status_code >= 400:
        st.error(response.text)
        return []
    return response.json()


def api_post(table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    response = requests.post(url, headers=HEADERS, json=data)
    if response.status_code >= 400:
        st.error(response.text)
        return None
    return response.json()


def api_patch(table, row_id, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {"id": f"eq.{row_id}"}
    response = requests.patch(url, headers=HEADERS, params=params, json=data)
    if response.status_code >= 400:
        st.error(response.text)
        return None
    return response.json()


def api_delete(table, row_id):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {"id": f"eq.{row_id}"}
    response = requests.delete(url, headers=HEADERS, params=params)
    if response.status_code >= 400:
        st.error(response.text)
        return False
    return True


def api_delete_where(table, params):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    response = requests.delete(url, headers=HEADERS, params=params)
    if response.status_code >= 400:
        st.error(response.text)
        return False
    return True


# =========================
# データ操作
# =========================
def get_players(include_hidden=False):
    select_cols = "id,name,created_at,is_active"
    params = {"select": select_cols, "order": "id.asc"}
    if not include_hidden:
        params["is_active"] = "eq.true"
    return api_get("players", params)


def add_player(name):
    name = name.strip()
    if not name:
        return False, "名前を入力してください。"

    players = get_players(include_hidden=True)
    active_same = [p for p in players if p.get("name") == name and p.get("is_active", True)]
    if active_same:
        return False, "同じ名前がすでに登録されています。"

    result = api_post("players", {"name": name, "is_active": True})
    if result is None:
        return False, "登録に失敗しました。"
    return True, f"{name} を登録しました。"


def update_player_name(player_id, new_name):
    new_name = new_name.strip()
    if not new_name:
        return False, "名前を入力してください。"
    result = api_patch("players", player_id, {"name": new_name})
    if result is None:
        return False, "名前変更に失敗しました。"
    return True, "名前を変更しました。"


def set_player_active(player_id, is_active):
    result = api_patch("players", player_id, {"is_active": is_active})
    if result is None:
        return False, "更新に失敗しました。"
    return True, "更新しました。"


def player_has_results(player_id):
    rows = api_get("game_results", {"select": "id", "player_id": f"eq.{player_id}", "limit": "1"})
    return len(rows) > 0


def delete_player(player_id):
    if player_has_results(player_id):
        return False, "このメンバーは対戦データがあるため削除できません。過去データを残すため、非表示を使ってください。"
    ok = api_delete("players", player_id)
    if not ok:
        return False, "削除に失敗しました。"
    return True, "削除しました。"


def clear_score_data():
    # 名前マスタ(players)は消さず、対戦結果だけ削除する
    # 外部キーの関係があるため、game_results → games の順番で削除
    ok_results = api_delete_where("game_results", {"id": "gte.0"})
    if not ok_results:
        return False, "点数データの削除に失敗しました。"

    ok_games = api_delete_where("games", {"id": "gte.0"})
    if not ok_games:
        return False, "対戦履歴の削除に失敗しました。"

    return True, "点数一覧・ランキング・個人成績・対戦履歴のデータを全て削除しました。"


def delete_single_game(game_id):
    # 指定した1対戦だけ削除する。名前マスタ(players)は削除しない。
    # 外部キーの関係があるため、game_results → games の順番で削除。
    ok_results = api_delete_where("game_results", {"game_id": f"eq.{game_id}"})
    if not ok_results:
        return False, "この対戦の点数データ削除に失敗しました。"

    ok_game = api_delete("games", game_id)
    if not ok_game:
        return False, "この対戦履歴の削除に失敗しました。"

    return True, "指定した対戦を削除しました。"


def make_game_summary(results):
    if not results:
        return []

    games = {}
    for row in results:
        game_id = row.get("game_id")
        if game_id is None:
            continue
        if game_id not in games:
            games[game_id] = {
                "game_id": game_id,
                "game_no": row.get("game_no"),
                "memo": row.get("memo") or "",
                "played_at": row.get("played_at") or "",
                "members": [],
            }
        games[game_id]["members"].append({
            "name": row.get("name") or "",
            "point": int(row.get("point") or 0),
        })

    summary = []
    for game in games.values():
        members_sorted = sorted(game["members"], key=lambda x: x["point"], reverse=True)
        member_text = " / ".join([f"{m['name']} {m['point']:+d}" for m in members_sorted])
        label = f"{game['game_no']}回戦　{member_text}"
        if game["memo"]:
            label += f"　メモ：{game['memo']}"
        summary.append({
            "game_id": game["game_id"],
            "game_no": game["game_no"],
            "label": label,
            "members": members_sorted,
            "memo": game["memo"],
            "played_at": game["played_at"],
        })

    summary.sort(key=lambda x: x["game_no"] or 0, reverse=True)
    return summary


def get_game_count():
    rows = api_get("games", {"select": "id"})
    return len(rows)


def get_result_count():
    rows = api_get("game_results", {"select": "id"})
    return len(rows)


def get_next_game_no():
    games = api_get("games", {"select": "game_no", "order": "game_no.desc", "limit": "1"})
    if not games:
        return 1
    return int(games[0]["game_no"]) + 1


def save_game(points, memo):
    game_no = get_next_game_no()
    game = api_post("games", {"game_no": game_no, "memo": memo})
    if not game:
        return False

    game_id = game[0]["id"]
    rows = []
    for player_id, point in points.items():
        rows.append({"game_id": game_id, "player_id": player_id, "point": int(point)})

    result = api_post("game_results", rows)
    return result is not None


def get_results():
    rows = api_get(
        "game_results",
        {
            "select": "id,point,created_at,games(id,game_no,memo,created_at),players(id,name)",
            "order": "id.asc",
        },
    )

    results = []
    for row in rows:
        game = row.get("games") or {}
        player = row.get("players") or {}
        results.append({
            "result_id": row.get("id"),
            "game_id": game.get("id"),
            "game_no": game.get("game_no"),
            "memo": game.get("memo"),
            "played_at": game.get("created_at"),
            "player_id": player.get("id"),
            "name": player.get("name"),
            "point": row.get("point", 0),
        })
    return results


# =========================
# 集計
# =========================
def make_score_table(results):
    if not results:
        return []
    names = []
    for row in results:
        if row["name"] not in names:
            names.append(row["name"])
    game_nos = sorted(set(row["game_no"] for row in results if row["game_no"] is not None))
    table = []
    for name in names:
        line = {"名前": name}
        total = 0
        for game_no in game_nos:
            value = ""
            for row in results:
                if row["name"] == name and row["game_no"] == game_no:
                    value = row["point"]
                    total += row["point"]
                    break
            line[f"{game_no}回戦"] = value
        line["累計"] = total
        table.append(line)
    table.sort(key=lambda x: x["累計"], reverse=True)
    return table


def make_ranking(results):
    stats = {}
    for row in results:
        name = row["name"]
        point = int(row["point"])
        if name not in stats:
            stats[name] = {"名前": name, "対戦数": 0, "プラス回数": 0, "マイナス回数": 0, "合計点": 0, "最高点": point, "最低点": point}
        stats[name]["対戦数"] += 1
        stats[name]["合計点"] += point
        stats[name]["最高点"] = max(stats[name]["最高点"], point)
        stats[name]["最低点"] = min(stats[name]["最低点"], point)
        if point > 0:
            stats[name]["プラス回数"] += 1
        elif point < 0:
            stats[name]["マイナス回数"] += 1

    table = []
    for data in stats.values():
        count = data["対戦数"]
        plus_rate = data["プラス回数"] / count * 100 if count else 0
        avg = data["合計点"] / count if count else 0
        table.append({"名前": data["名前"], "対戦数": count, "合計点": data["合計点"], "平均点": round(avg, 1), "プラス率": f"{plus_rate:.1f}%", "最高点": data["最高点"], "最低点": data["最低点"]})
    table.sort(key=lambda x: x["合計点"], reverse=True)
    return table


def group_results_by_game(results):
    games = {}
    for row in results:
        game_id = row.get("game_id")
        if game_id is None:
            continue
        if game_id not in games:
            games[game_id] = {
                "game_id": game_id,
                "game_no": row.get("game_no"),
                "memo": row.get("memo") or "",
                "played_at": row.get("played_at") or "",
                "members": [],
            }
        games[game_id]["members"].append({
            "player_id": row.get("player_id"),
            "name": row.get("name") or "",
            "point": int(row.get("point") or 0),
        })
    return games


def add_rank_to_games(games):
    for game in games.values():
        members = sorted(game["members"], key=lambda x: x["point"], reverse=True)
        prev_point = None
        current_rank = 0
        for idx, member in enumerate(members, start=1):
            if prev_point is None or member["point"] != prev_point:
                current_rank = idx
            member["rank"] = current_rank
            prev_point = member["point"]
        game["members"] = members
    return games


def build_player_stats(results):
    games = add_rank_to_games(group_results_by_game(results))
    stats = {}
    for game in games.values():
        member_count = len(game["members"])
        for member in game["members"]:
            pid = member["player_id"]
            name = member["name"]
            point = int(member["point"])
            rank = int(member.get("rank") or 0)
            if pid not in stats:
                stats[pid] = {
                    "player_id": pid,
                    "名前": name,
                    "対戦数": 0,
                    "トップ回数": 0,
                    "2着回数": 0,
                    "3着回数": 0,
                    "ラス回数": 0,
                    "プラス回数": 0,
                    "マイナス回数": 0,
                    "順位合計": 0,
                    "合計点": 0,
                    "最高点": point,
                    "最低点": point,
                }
            s = stats[pid]
            s["名前"] = name
            s["対戦数"] += 1
            s["合計点"] += point
            s["順位合計"] += rank
            s["最高点"] = max(s["最高点"], point)
            s["最低点"] = min(s["最低点"], point)
            if point > 0:
                s["プラス回数"] += 1
            elif point < 0:
                s["マイナス回数"] += 1
            if rank == 1:
                s["トップ回数"] += 1
            elif rank == 2:
                s["2着回数"] += 1
            elif rank == 3:
                s["3着回数"] += 1
            if rank == member_count:
                s["ラス回数"] += 1
    return stats, games


def make_enhanced_ranking(results):
    stats, _ = build_player_stats(results)
    table = []
    for data in stats.values():
        count = data["対戦数"]
        avg = data["合計点"] / count if count else 0
        avg_rank = data["順位合計"] / count if count else 0
        plus_rate = data["プラス回数"] / count * 100 if count else 0
        top_rate = data["トップ回数"] / count * 100 if count else 0
        last_rate = data["ラス回数"] / count * 100 if count else 0
        table.append({
            "順位": 0,
            "名前": data["名前"],
            "対戦数": count,
            "合計点": data["合計点"],
            "平均点": round(avg, 1),
            "平均順位": round(avg_rank, 2),
            "プラス率": f"{plus_rate:.1f}%",
            "トップ回数": data["トップ回数"],
            "トップ率": f"{top_rate:.1f}%",
            "ラス回数": data["ラス回数"],
            "ラス率": f"{last_rate:.1f}%",
            "最高点": data["最高点"],
            "最低点": data["最低点"],
        })
    table.sort(key=lambda x: (x["合計点"], x["平均点"]), reverse=True)
    for i, row in enumerate(table, start=1):
        row["順位"] = i
    return table


def make_personal_detail(results, target_name):
    stats, games = build_player_stats(results)
    personal_rows = []
    cumulative = 0
    for game in sorted(games.values(), key=lambda g: g.get("game_no") or 0):
        members = game["members"]
        target = next((m for m in members if m["name"] == target_name), None)
        if not target:
            continue
        cumulative += int(target["point"])
        personal_rows.append({
            "回戦": game.get("game_no"),
            "順位": target.get("rank"),
            "点数": int(target["point"]),
            "累計": cumulative,
            "メモ": game.get("memo") or "",
        })
    if not personal_rows:
        return None, [], []
    player_stat = None
    for s in stats.values():
        if s["名前"] == target_name:
            player_stat = s
            break
    chart_data = [{"回戦": r["回戦"], "累計": r["累計"]} for r in personal_rows]
    return player_stat, personal_rows, chart_data


def make_matchup_table(results, target_name):
    _, games = build_player_stats(results)
    matchup = {}
    for game in games.values():
        members = game["members"]
        me = next((m for m in members if m["name"] == target_name), None)
        if not me:
            continue
        for opp in members:
            if opp["name"] == target_name:
                continue
            name = opp["name"]
            if name not in matchup:
                matchup[name] = {
                    "相手": name,
                    "同卓回数": 0,
                    "自分合計": 0,
                    "相手合計": 0,
                    "勝ち回数": 0,
                    "負け回数": 0,
                    "自分順位合計": 0,
                    "相手順位合計": 0,
                }
            m = matchup[name]
            m["同卓回数"] += 1
            m["自分合計"] += int(me["point"])
            m["相手合計"] += int(opp["point"])
            m["自分順位合計"] += int(me.get("rank") or 0)
            m["相手順位合計"] += int(opp.get("rank") or 0)
            if int(me["point"]) > int(opp["point"]):
                m["勝ち回数"] += 1
            elif int(me["point"]) < int(opp["point"]):
                m["負け回数"] += 1

    table = []
    for m in matchup.values():
        count = m["同卓回数"]
        win_rate = m["勝ち回数"] / count * 100 if count else 0
        table.append({
            "相手": m["相手"],
            "同卓回数": count,
            "自分合計": m["自分合計"],
            "相手合計": m["相手合計"],
            "差分": m["自分合計"] - m["相手合計"],
            "自分平均": round(m["自分合計"] / count, 1) if count else 0,
            "相手平均": round(m["相手合計"] / count, 1) if count else 0,
            "勝ち回数": m["勝ち回数"],
            "勝率": f"{win_rate:.1f}%",
            "自分平均順位": round(m["自分順位合計"] / count, 2) if count else 0,
            "相手平均順位": round(m["相手順位合計"] / count, 2) if count else 0,
        })
    table.sort(key=lambda x: (x["差分"], x["同卓回数"]), reverse=True)
    return table


def make_history_table(results):
    games = add_rank_to_games(group_results_by_game(results))
    history = []
    for game in sorted(games.values(), key=lambda g: g.get("game_no") or 0, reverse=True):
        for m in game["members"]:
            history.append({
                "回戦": game.get("game_no"),
                "順位": m.get("rank"),
                "名前": m.get("name"),
                "点数": m.get("point"),
                "メモ": game.get("memo") or "",
            })
    return history


def build_dashboard_metrics(results, players):
    ranking = make_enhanced_ranking(results)
    game_count = len(group_results_by_game(results))
    active_count = len(players)
    recent_game = make_game_summary(results)
    recent_label = recent_game[0]["label"] if recent_game else "まだ対戦がありません"

    top4 = ranking[:4]
    top_name = top4[0]["名前"] if top4 else "-"
    top_point = top4[0]["合計点"] if top4 else 0

    return {
        "総対戦数": game_count,
        "登録メンバー": active_count,
        "現在1位": top_name,
        "1位合計点": top_point,
        "上位4名": top4,
        "直近対戦": recent_label,
    }


def make_excel_file(results):
    wb = Workbook()
    ws = wb.active
    ws.title = "点数一覧"

    sheets = {
        "点数一覧": make_score_table(results),
        "ランキング": make_enhanced_ranking(results),
        "対戦履歴": make_history_table(results),
    }

    # 個人成績サマリー
    personal_summary = []
    ranking = make_enhanced_ranking(results)
    for r in ranking:
        personal_summary.append(r.copy())
    sheets["個人成績"] = personal_summary

    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(color="FFFFFF", bold=True)
    border = Border(
        left=Side(style="thin", color="D9E2F3"),
        right=Side(style="thin", color="D9E2F3"),
        top=Side(style="thin", color="D9E2F3"),
        bottom=Side(style="thin", color="D9E2F3"),
    )

    first = True
    for sheet_name, rows in sheets.items():
        if first:
            ws = wb.active
            ws.title = sheet_name
            first = False
        else:
            ws = wb.create_sheet(sheet_name)
        if not rows:
            ws.append(["データなし"])
            continue
        headers = list(rows[0].keys())
        ws.append(headers)
        for row in rows:
            ws.append([row.get(h, "") for h in headers])
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")
        for row in ws.iter_rows():
            for cell in row:
                cell.border = border
        for col in ws.columns:
            max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max(max_len + 2, 10), 28)
        ws.freeze_panes = "A2"

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio.getvalue()



# =========================
# UI部品
# =========================

def zero_fill_point(current_player_id, selected_players):
    """指定した人の点数を、全体合計が0になる値に自動調整する。"""
    other_sum = 0
    for other in selected_players:
        if other["id"] == current_player_id:
            continue
        other_sum += int(st.session_state.get(f"manual_point_{other['id']}", 0))
    st.session_state[f"manual_point_{current_player_id}"] = -other_sum

def menu_button(label, icon, key):
    return st.button(f"{icon}\n\n{label}", key=key, use_container_width=True)


def back_button():
    if st.button("← メニューへ戻る", key="back_home"):
        go("home")


# =========================
# 画面設定・CSS
# =========================
st.set_page_config(page_title="麻雀スコア管理", page_icon="🀄", layout="wide")

st.markdown(
    """
    <style>
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    .block-container {
        padding-top: 1.1rem;
        padding-bottom: 2rem;
        max-width: 760px;
    }

    h1 {
        font-size: 2.2rem !important;
        margin-bottom: .8rem !important;
        font-weight: 800 !important;
    }

    h2, h3 {
        margin-top: 1rem !important;
        font-weight: 800 !important;
    }

    .stButton > button {
        border-radius: 12px;
        border: 1px solid #d1d5db;
        background: #ffffff;
        color: #111827;
        font-weight: 700;
        transition: 0.15s;
    }

    .stButton > button:hover {
        border-color: #ff4b4b;
        color: #ff4b4b;
    }

    .stButton > button[kind="primary"] {
        background: #ff4b4b;
        color: white;
        border-color: #ff4b4b;
        min-height: 54px;
        font-size: 1.05rem;
        border-radius: 16px;
    }

    div[data-testid="column"] .stButton > button[kind="secondary"] {
        min-height: 84px;
        white-space: pre-line;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 16px !important;
        border-color: #e5e7eb !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }

    .member-id-label {
        color: #6b7280;
        font-size: 0.82rem;
        line-height: 1.1;
        margin-bottom: 0.18rem;
    }

    .member-name-label {
        color: #111827;
        font-size: 1.25rem;
        font-weight: 800;
        line-height: 1.15;
        word-break: keep-all;
        overflow-wrap: anywhere;
    }

    .button-spacer {
        height: 1.25rem;
    }

    .inline-panel {
        margin-top: .5rem;
        margin-bottom: .2rem;
        color: #6b7280;
        font-size: .85rem;
        font-weight: 700;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] .stButton > button {
        min-height: 40px !important;
        height: 40px !important;
        padding: 0 .25rem !important;
        font-size: .9rem !important;
        border-radius: 10px !important;
        white-space: nowrap !important;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] input {
        min-height: 40px !important;
        height: 40px !important;
        border-radius: 10px !important;
    }

    /* ボタン色 */
    button[kind="secondary"][aria-label="非表示"] {
        border-color: #2563eb !important;
        color: #2563eb !important;
    }
    button[kind="secondary"][aria-label="削除"] {
        border-color: #ef4444 !important;
        color: #ef4444 !important;
    }

    /* 対戦スタート画面 */
    .score-card {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 14px;
        padding: 10px 12px;
        margin-bottom: 8px;
    }
    .score-order {
        color: #6b7280;
        font-size: .82rem;
        font-weight: 700;
        margin-bottom: 2px;
    }
    .score-name {
        font-size: 1.15rem;
        font-weight: 800;
        color: #111827;
    }

    .top-rank-name {
        font-size: 1.75rem;
        font-weight: 900;
        color: #111827;
        line-height: 1.15;
        margin-top: .2rem;
    }

    .top-rank-point {
        font-size: 2.1rem;
        font-weight: 900;
        color: #ff4b4b;
        line-height: 1.15;
        margin-top: .35rem;
    }

    .sub-rank-no {
        font-size: .95rem;
        font-weight: 800;
        color: #6b7280;
        padding-top: .25rem;
    }

    .sub-rank-name {
        font-size: 1.05rem;
        font-weight: 800;
        color: #111827;
        padding-top: .2rem;
    }

    .sub-rank-point {
        font-size: 1.05rem;
        font-weight: 900;
        color: #374151;
        text-align: right;
        padding-top: .2rem;
    }

    @media (max-width: 640px) {
        .block-container {
            padding-left: .85rem;
            padding-right: .85rem;
            max-width: 100% !important;
        }
        h1 { font-size: 1.75rem !important; }
        h2, h3 { font-size: 1.35rem !important; }
        div[data-testid="column"] .stButton > button[kind="secondary"] { min-height: 64px; }
        .member-id-label { font-size: .72rem; }
        .member-name-label { font-size: 1.05rem; }
        .button-spacer { height: 1.05rem; }
        div[data-testid="stVerticalBlockBorderWrapper"] { padding: .15rem !important; }
        div[data-testid="stVerticalBlockBorderWrapper"] .stButton > button {
            min-height: 34px !important;
            height: 34px !important;
            padding: 0 .12rem !important;
            font-size: .72rem !important;
            border-radius: 8px !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] input {
            min-height: 36px !important;
            height: 36px !important;
            font-size: .9rem !important;
        }
        .score-name { font-size: 1.05rem; }
        .score-order { font-size: .76rem; }
        .top-rank-name { font-size: 1.45rem; }
        .top-rank-point { font-size: 1.8rem; }
        .sub-rank-no { font-size: .82rem; }
        .sub-rank-name { font-size: .95rem; }
        .sub-rank-point { font-size: .95rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================
# 簡易ログイン
# =========================
if "login" not in st.session_state:
    st.session_state.login = False

if not st.session_state.login:
    st.title("🀄 麻雀スコア管理")
    st.write("合言葉を入力してください。")
    password = st.text_input("合言葉", type="password")
    if st.button("ログイン", type="primary"):
        if password == APP_PASSWORD:
            st.session_state.login = True
            st.rerun()
        else:
            st.error("合言葉が違います。")
    st.stop()


# =========================
# ページ状態
# =========================
if "page" not in st.session_state:
    st.session_state.page = "home"
if "delete_confirm_id" not in st.session_state:
    st.session_state.delete_confirm_id = None
if "edit_player_id" not in st.session_state:
    st.session_state.edit_player_id = None
if "clear_scores_step" not in st.session_state:
    st.session_state.clear_scores_step = 0
if "delete_game_confirm_id" not in st.session_state:
    st.session_state.delete_game_confirm_id = None
if "selected_player_ids" not in st.session_state:
    st.session_state.selected_player_ids = []
if "save_complete" not in st.session_state:
    st.session_state.save_complete = False


def go(page):
    st.session_state.page = page
    st.rerun()


# =========================
# トップ画面
# =========================
if st.session_state.page == "home":
    st.title("🀄 麻雀スコア管理")
    st.caption("メニューを選択してください。")

    results = get_results()
    players = get_players()
    metrics = build_dashboard_metrics(results, players)

    c1, c2 = st.columns(2)
    c1.metric("総対戦数", f"{metrics['総対戦数']}戦")
    c2.metric("登録メンバー", f"{metrics['登録メンバー']}人")

    top4 = metrics.get("上位4名", [])

    if top4:
        top = top4[0]
        with st.container(border=True):
            st.markdown("### 🏆 現在1位")
            st.markdown(
                f"""
                <div class="top-rank-name">{top['名前']}</div>
                <div class="top-rank-point">{top['合計点']:+d} 点</div>
                """,
                unsafe_allow_html=True,
            )

        if len(top4) >= 2:
            st.markdown("#### 2位〜4位")
            for row in top4[1:4]:
                with st.container(border=True):
                    rank_col, name_col, point_col = st.columns([0.55, 2.4, 1.05], gap="small")
                    with rank_col:
                        st.markdown(f"<div class='sub-rank-no'>{row['順位']}位</div>", unsafe_allow_html=True)
                    with name_col:
                        st.markdown(f"<div class='sub-rank-name'>{row['名前']}</div>", unsafe_allow_html=True)
                    with point_col:
                        st.markdown(f"<div class='sub-rank-point'>{row['合計点']:+d}</div>", unsafe_allow_html=True)
    else:
        with st.container(border=True):
            st.markdown("### 🏆 現在1位")
            st.write("まだランキングデータがありません。")

    with st.container(border=True):
        st.markdown("**直近の対戦**")
        st.write(metrics["直近対戦"])

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        if menu_button("対戦スタート", "🎮", "start"):
            go("start")
        if menu_button("点数一覧", "📋", "score_list"):
            go("score_list")
        if menu_button("個人成績", "👤", "personal"):
            go("personal")
        if menu_button("過去の対戦履歴", "🕘", "history"):
            go("history")
    with col2:
        if menu_button("名前登録", "✏️", "players"):
            go("players")
        if menu_button("ランキング", "🏆", "ranking"):
            go("ranking")
        if menu_button("相性分析", "🤝", "matchup"):
            go("matchup")
        if menu_button("設定", "⚙️", "settings"):
            go("settings")


# =========================
# 名前登録
# =========================
elif st.session_state.page == "players":
    st.title("✏️ 名前登録")
    back_button()

    st.markdown("### 参加者を登録")
    new_name = st.text_input("名前", placeholder="例：小野", label_visibility="collapsed")
    if st.button("＋ 登録する", type="primary", use_container_width=True):
        ok, msg = add_player(new_name)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.warning(msg)

    st.markdown("---")
    st.subheader("登録済みメンバー")

    players = get_players(include_hidden=False)
    hidden_players_all = get_players(include_hidden=True)
    hidden_players = [p for p in hidden_players_all if not p.get("is_active", True)]

    if players:
        for p in players:
            with st.container(border=True):
                name_col, change_col, hide_col, delete_col = st.columns([2.25, 1.05, 0.95, 0.85], gap="small")

                with name_col:
                    st.markdown(
                        f"""
                        <div class="member-id-label">ID: {p["id"]}</div>
                        <div class="member-name-label">{p["name"]}</div>
                        """,
                        unsafe_allow_html=True,
                    )

                with change_col:
                    st.markdown('<div class="button-spacer"></div>', unsafe_allow_html=True)
                    if st.button("名称変更", key=f"open_edit_{p['id']}", use_container_width=True):
                        st.session_state.edit_player_id = p["id"]
                        st.session_state.delete_confirm_id = None
                        st.rerun()

                with hide_col:
                    st.markdown('<div class="button-spacer"></div>', unsafe_allow_html=True)
                    if st.button("非表示", key=f"hide_{p['id']}", use_container_width=True):
                        ok, msg = set_player_active(p["id"], False)
                        if ok:
                            st.success("非表示にしました。")
                            st.rerun()
                        else:
                            st.warning(msg)

                with delete_col:
                    st.markdown('<div class="button-spacer"></div>', unsafe_allow_html=True)
                    if st.button("削除", key=f"delete_{p['id']}", use_container_width=True):
                        st.session_state.delete_confirm_id = p["id"]
                        st.session_state.edit_player_id = None
                        st.rerun()

                if st.session_state.edit_player_id == p["id"]:
                    st.markdown('<div class="inline-panel">名前を変更</div>', unsafe_allow_html=True)
                    edit_col, save_col, cancel_col = st.columns([3.0, 0.9, 0.9], gap="small")
                    with edit_col:
                        edited_name = st.text_input(
                            "新しい名前",
                            value=p["name"],
                            key=f"edit_name_{p['id']}",
                            label_visibility="collapsed",
                        )
                    with save_col:
                        if st.button("保存", key=f"save_edit_{p['id']}", use_container_width=True):
                            ok, msg = update_player_name(p["id"], edited_name)
                            if ok:
                                st.session_state.edit_player_id = None
                                st.success(msg)
                                st.rerun()
                            else:
                                st.warning(msg)
                    with cancel_col:
                        if st.button("取消", key=f"cancel_edit_{p['id']}", use_container_width=True):
                            st.session_state.edit_player_id = None
                            st.rerun()

                if st.session_state.delete_confirm_id == p["id"]:
                    st.warning(f"{p['name']} さんを削除しますか？")
                    yes_col, no_col, blank_col = st.columns([0.9, 0.9, 3.2], gap="small")
                    with yes_col:
                        if st.button("はい", key=f"delete_yes_{p['id']}", use_container_width=True):
                            ok, msg = delete_player(p["id"])
                            st.session_state.delete_confirm_id = None
                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.warning(msg)
                    with no_col:
                        if st.button("いいえ", key=f"delete_no_{p['id']}", use_container_width=True):
                            st.session_state.delete_confirm_id = None
                            st.rerun()
    else:
        st.info("表示中のメンバーはいません。")

    st.markdown("---")
    if hidden_players:
        with st.expander(f"非表示メンバー（{len(hidden_players)}人）"):
            for p in hidden_players:
                with st.container(border=True):
                    c1, c2 = st.columns([3.2, 0.8], gap="small")
                    with c1:
                        st.markdown(
                            f'<div class="member-id-label">ID: {p["id"]}</div><div class="member-name-label">{p["name"]}</div>',
                            unsafe_allow_html=True,
                        )
                    with c2:
                        st.markdown('<div class="button-spacer"></div>', unsafe_allow_html=True)
                        if st.button("復活", key=f"restore_{p['id']}", use_container_width=True):
                            ok, msg = set_player_active(p["id"], True)
                            if ok:
                                st.success("復活しました。")
                                st.rerun()
                            else:
                                st.warning(msg)


# =========================
# 対戦スタート
# =========================
elif st.session_state.page == "start":
    st.title("🎮 対戦スタート")
    back_button()

    if st.session_state.get("save_complete", False):
        st.session_state.selected_player_ids = []
        for key in list(st.session_state.keys()):
            if str(key).startswith("manual_point_"):
                del st.session_state[key]

        st.success("正常に登録されました。")
        st.info("下のボタンを押すと、点数一覧へ移動します。")
        if st.button("点数一覧を確認する", type="primary", use_container_width=True):
            st.session_state.save_complete = False
            go("score_list")
        st.stop()

    players = get_players()
    if len(players) < 4:
        st.warning("先に4人以上の名前を登録してください。")
    else:
        st.subheader("参加者を4人選択")
        st.caption("名前の横のボタンを押すだけで選択・解除できます。4人まで選択できます。")

        id_to_player = {p["id"]: p for p in players}

        # 非表示などで存在しなくなったIDは選択状態から外す
        valid_ids = {p["id"] for p in players}
        st.session_state.selected_player_ids = [
            pid for pid in st.session_state.selected_player_ids if pid in valid_ids
        ]

        selected_ids = st.session_state.selected_player_ids
        st.info(f"現在 {len(selected_ids)} / 4人 選択中")

        if selected_ids:
            selected_names_text = " / ".join([id_to_player[pid]["name"] for pid in selected_ids])
            st.success(f"選択中：{selected_names_text}")

        reset_col, _ = st.columns([1.2, 3.8])
        with reset_col:
            if st.button("選択リセット", use_container_width=True):
                st.session_state.selected_player_ids = []
                for p in players:
                    key = f"manual_point_{p['id']}"
                    if key in st.session_state:
                        st.session_state[key] = 0
                st.rerun()

        st.markdown("#### メンバー一覧")

        # 1行ずつカード表示。スマホでも反応が安定するようにmultiselectは使わない
        for p in players:
            pid = p["id"]
            is_selected = pid in st.session_state.selected_player_ids

            with st.container(border=True):
                name_col, btn_col = st.columns([3.2, 1.0], gap="small")
                with name_col:
                    order_text = ""
                    if is_selected:
                        order_text = f"　{st.session_state.selected_player_ids.index(pid) + 1}人目"
                    st.markdown(
                        f"""
                        <div class="member-id-label">ID: {pid}{order_text}</div>
                        <div class="member-name-label">{p['name']}</div>
                        """,
                        unsafe_allow_html=True,
                    )
                with btn_col:
                    st.markdown('<div class="button-spacer"></div>', unsafe_allow_html=True)
                    if is_selected:
                        if st.button("解除", key=f"unselect_{pid}", use_container_width=True):
                            st.session_state.selected_player_ids.remove(pid)
                            key = f"manual_point_{pid}"
                            if key in st.session_state:
                                st.session_state[key] = 0
                            st.rerun()
                    else:
                        disabled = len(st.session_state.selected_player_ids) >= 4
                        if st.button("選択", key=f"select_{pid}", use_container_width=True, disabled=disabled):
                            st.session_state.selected_player_ids.append(pid)
                            st.rerun()

        selected_ids = st.session_state.selected_player_ids

        if len(selected_ids) != 4:
            st.info("4人選択すると、半荘結果を入力できます。")
        else:
            selected_players = [id_to_player[pid] for pid in selected_ids]
            st.markdown("---")
            st.subheader("半荘結果を入力")
            st.caption("全員手入力できます。点数は1刻みです。最後に入力する人は『集計』ボタンで合計0になる値を自動入力できます。")

            points = {}
            for i, player in enumerate(selected_players, start=1):
                with st.container(border=True):
                    name_col, score_col, auto_col = st.columns([2.0, 1.35, 0.9], gap="small")
                    with name_col:
                        st.markdown(
                            f"""
                            <div class="score-order">{i}人目</div>
                            <div class="score-name">{player['name']}</div>
                            """,
                            unsafe_allow_html=True,
                        )
                    with score_col:
                        key = f"manual_point_{player['id']}"
                        if key not in st.session_state:
                            st.session_state[key] = 0
                        value = st.number_input(
                            "点数",
                            value=int(st.session_state[key]),
                            step=1,
                            key=key,
                            label_visibility="collapsed",
                        )
                        points[player["id"]] = int(value)
                    with auto_col:
                        st.markdown('<div class="button-spacer"></div>', unsafe_allow_html=True)
                        st.button(
                            "集計",
                            key=f"zero_fill_{player['id']}",
                            use_container_width=True,
                            on_click=zero_fill_point,
                            args=(player["id"], selected_players),
                        )

            total = sum(int(st.session_state.get(f"manual_point_{p['id']}", 0)) for p in selected_players)

            if total == 0:
                st.success("合計は0です。登録できます。")
            else:
                st.error(f"合計が {total} です。±0になっていないため登録できません。")

            memo = st.text_input("メモ", placeholder="例：6/7 1回目、休日麻雀 など")

            st.subheader("登録前確認")
            preview = []
            final_points = {}
            for p in selected_players:
                point = int(st.session_state.get(f"manual_point_{p['id']}", 0))
                final_points[p["id"]] = point
                preview.append({"名前": p["name"], "点数": point})
            preview.sort(key=lambda x: x["点数"], reverse=True)
            st.table(preview)

            if st.button("この対戦を登録する", type="primary", use_container_width=True):
                if total != 0:
                    st.error("合計が±0になっていないため登録できません。")
                else:
                    ok = save_game(final_points, memo)
                    if ok:
                        st.session_state.save_complete = True
                        st.rerun()
                    else:
                        st.error("登録に失敗しました。")


# =========================
# 点数一覧
# =========================
elif st.session_state.page == "score_list":
    st.title("📋 点数一覧")
    back_button()
    results = get_results()
    table = make_score_table(results)

    if table:
        st.subheader("点数一覧")
        st.table(table)

        st.markdown("---")
        st.subheader("対戦ごとの削除")
        st.caption("間違えて登録した対戦だけを削除できます。名前登録データは削除されません。")

        game_summary = make_game_summary(results)
        if game_summary:
            options = {g["label"]: g for g in game_summary}
            selected_label = st.selectbox("削除したい対戦を選択", list(options.keys()))
            selected_game = options[selected_label]

            st.markdown("**選択中の対戦**")
            st.table([
                {"名前": m["name"], "点数": m["point"]}
                for m in selected_game["members"]
            ])

            if selected_game.get("memo"):
                st.write(f"メモ：{selected_game['memo']}")

            if st.session_state.delete_game_confirm_id != selected_game["game_id"]:
                if st.button("この対戦を削除", use_container_width=True):
                    st.session_state.delete_game_confirm_id = selected_game["game_id"]
                    st.rerun()
            else:
                st.warning("この対戦を削除しますが、よろしいですか？")
                yes_col, no_col = st.columns(2, gap="small")
                with yes_col:
                    if st.button("はい、削除します", use_container_width=True):
                        ok, msg = delete_single_game(selected_game["game_id"])
                        st.session_state.delete_game_confirm_id = None
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.warning(msg)
                with no_col:
                    if st.button("いいえ", use_container_width=True):
                        st.session_state.delete_game_confirm_id = None
                        st.rerun()
    else:
        st.info("まだデータがありません。")


# =========================
# ランキング
# =========================
elif st.session_state.page == "ranking":
    st.title("🏆 ランキング")
    back_button()
    results = get_results()
    table = make_enhanced_ranking(results)
    if table:
        top = table[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("現在1位", top["名前"])
        c2.metric("1位合計点", f"{top['合計点']:+d}")
        c3.metric("平均点", top["平均点"])
        st.markdown("---")
        st.subheader("総合ランキング")
        st.table(table)
    else:
        st.info("まだデータがありません。")


# =========================
# 個人成績
# =========================
elif st.session_state.page == "personal":
    st.title("👤 個人成績")
    back_button()
    results = get_results()
    names = sorted(set(r["name"] for r in results if r["name"]))
    if not names:
        st.info("まだデータがありません。")
    else:
        target = st.selectbox("名前を選択", names)
        stat, personal_rows, chart_data = make_personal_detail(results, target)
        if not stat:
            st.info("データがありません。")
        else:
            count = stat["対戦数"]
            total = stat["合計点"]
            avg = total / count if count else 0
            avg_rank = stat["順位合計"] / count if count else 0
            top_rate = stat["トップ回数"] / count * 100 if count else 0
            last_rate = stat["ラス回数"] / count * 100 if count else 0
            plus_rate = stat["プラス回数"] / count * 100 if count else 0

            c1, c2, c3 = st.columns(3)
            c1.metric("対戦数", count)
            c2.metric("合計点", f"{total:+d}")
            c3.metric("平均点", f"{avg:.1f}")

            c4, c5, c6 = st.columns(3)
            c4.metric("平均順位", f"{avg_rank:.2f}")
            c5.metric("トップ率", f"{top_rate:.1f}%")
            c6.metric("ラス率", f"{last_rate:.1f}%")

            c7, c8, c9 = st.columns(3)
            c7.metric("プラス率", f"{plus_rate:.1f}%")
            c8.metric("最高点", f"{stat['最高点']:+d}")
            c9.metric("最低点", f"{stat['最低点']:+d}")

            st.markdown("---")
            st.subheader("順位内訳")
            rank_table = [{
                "トップ": stat["トップ回数"],
                "2着": stat["2着回数"],
                "3着": stat["3着回数"],
                "ラス": stat["ラス回数"],
            }]
            st.table(rank_table)

            st.subheader("累計推移")
            # Streamlit側で簡易グラフ化
            st.line_chart({"累計": [r["累計"] for r in personal_rows]})

            st.subheader("直近10戦")
            recent = list(reversed(personal_rows[-10:]))
            st.table(recent)


# =========================
# 過去の対戦履歴
# =========================
elif st.session_state.page == "history":
    st.title("🕘 過去の対戦履歴")
    back_button()
    results = get_results()
    history = make_history_table(results)
    if not history:
        st.info("まだ履歴がありません。")
    else:
        st.table(history)


# =========================
# 後で追加
# =========================
elif st.session_state.page == "matchup":
    st.title("🤝 相性分析")
    back_button()
    results = get_results()
    names = sorted(set(r["name"] for r in results if r["name"]))
    if not names:
        st.info("まだデータがありません。")
    else:
        target = st.selectbox("自分を選択", names)
        table = make_matchup_table(results, target)
        if table:
            best = table[0]
            worst = table[-1]
            c1, c2 = st.columns(2)
            c1.metric("相性が良い相手", best["相手"], f"差分 {best['差分']:+d}")
            c2.metric("苦手な相手", worst["相手"], f"差分 {worst['差分']:+d}")
            st.markdown("---")
            st.table(table)
        else:
            st.info("この人の同卓データがまだありません。")


elif st.session_state.page == "settings":
    st.title("⚙️ 設定")
    back_button()

    st.subheader("Excel出力")
    results_for_excel = get_results()
    if results_for_excel:
        excel_bytes = make_excel_file(results_for_excel)
        st.download_button(
            "Excelファイルをダウンロード",
            data=excel_bytes,
            file_name="mahjong_score_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    else:
        st.info("Excel出力できるデータがまだありません。")

    st.markdown("---")
    st.subheader("データ管理")
    st.warning("名前登録データは残したまま、点数一覧・ランキング・個人成績・過去の対戦履歴だけを削除します。")

    game_count = get_game_count()
    result_count = get_result_count()
    st.info(f"現在の対戦数：{game_count}戦 / 点数データ：{result_count}件")

    if st.session_state.clear_scores_step == 0:
        if st.button("点数データを全削除", type="primary", use_container_width=True):
            st.session_state.clear_scores_step = 1
            st.rerun()

    elif st.session_state.clear_scores_step == 1:
        st.subheader("管理者確認")
        admin_pw = st.text_input("管理者パスワード", type="password", key="admin_pw_clear_scores")
        c1, c2 = st.columns(2, gap="small")
        with c1:
            if st.button("確認する", use_container_width=True):
                if admin_pw == ADMIN_PASSWORD:
                    st.session_state.clear_scores_step = 2
                    st.rerun()
                else:
                    st.error("管理者パスワードが違います。")
        with c2:
            if st.button("キャンセル", use_container_width=True):
                st.session_state.clear_scores_step = 0
                st.rerun()

    elif st.session_state.clear_scores_step == 2:
        st.error("本当に点数データを全て削除しますか？この操作は元に戻せません。")
        st.write(f"削除対象：**{game_count}戦** / **{result_count}件**")
        st.write("削除されないもの：**名前登録データ**")

        yes_col, no_col = st.columns(2, gap="small")
        with yes_col:
            if st.button("はい、削除します", use_container_width=True):
                ok, msg = clear_score_data()
                st.session_state.clear_scores_step = 0
                if ok:
                    for key in list(st.session_state.keys()):
                        if key.startswith("score_input_") or key in ["selected_player_ids", "save_complete"]:
                            del st.session_state[key]
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)
        with no_col:
            if st.button("いいえ、やめます", use_container_width=True):
                st.session_state.clear_scores_step = 0
                st.rerun()
