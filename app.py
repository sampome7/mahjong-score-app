import streamlit as st
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

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
        st.table(table)
    else:
        st.info("まだデータがありません。")


# =========================
# ランキング
# =========================
elif st.session_state.page == "ranking":
    st.title("🏆 ランキング")
    back_button()
    results = get_results()
    table = make_ranking(results)
    if table:
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
        personal = [r for r in results if r["name"] == target]
        total = sum(int(r["point"]) for r in personal)
        count = len(personal)
        avg = total / count if count else 0
        plus = len([r for r in personal if int(r["point"]) > 0])
        c1, c2, c3 = st.columns(3)
        c1.metric("対戦数", count)
        c2.metric("合計点", total)
        c3.metric("平均点", f"{avg:.1f}")
        st.write(f"プラス回数：{plus}回")
        st.table([{"回戦": r["game_no"], "点数": r["point"], "メモ": r["memo"] or ""} for r in personal])


# =========================
# 過去の対戦履歴
# =========================
elif st.session_state.page == "history":
    st.title("🕘 過去の対戦履歴")
    back_button()
    results = get_results()
    if not results:
        st.info("まだ履歴がありません。")
    else:
        history = []
        for r in results:
            history.append({"回戦": r["game_no"], "名前": r["name"], "点数": r["point"], "メモ": r["memo"] or ""})
        st.table(history)


# =========================
# 後で追加
# =========================
elif st.session_state.page == "matchup":
    st.title("🤝 相性分析")
    back_button()
    st.info("次の追加機能として作ります。")

elif st.session_state.page == "settings":
    st.title("⚙️ 設定")
    back_button()
    st.info("次の追加機能として作ります。")
