import streamlit as st
import requests

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
# 共通関数
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


def api_patch(table, record_id, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {"id": f"eq.{record_id}"}
    response = requests.patch(url, headers=HEADERS, params=params, json=data)
    if response.status_code >= 400:
        st.error(response.text)
        return None
    return response.json()


# =========================
# プレイヤー
# =========================
def get_players(active_only=False):
    params = {
        "select": "id,name,created_at,is_active",
        "order": "id.asc",
    }
    if active_only:
        params["is_active"] = "eq.true"
    return api_get("players", params)


def add_player(name):
    name = name.strip()
    if not name:
        return False, "名前を入力してください。"

    players = get_players(active_only=False)
    if any(p["name"] == name and p.get("is_active", True) for p in players):
        return False, "同じ名前がすでに登録されています。"

    result = api_post("players", {"name": name, "is_active": True})
    if result is None:
        return False, "登録に失敗しました。"
    return True, f"{name} を登録しました。"


def update_player_name(player_id, new_name):
    new_name = new_name.strip()
    if not new_name:
        return False, "名前を入力してください。"

    players = get_players(active_only=False)
    for p in players:
        if p["id"] != player_id and p["name"] == new_name and p.get("is_active", True):
            return False, "同じ名前がすでに登録されています。"

    result = api_patch("players", player_id, {"name": new_name})
    if result is None:
        return False, "名前変更に失敗しました。"
    return True, "名前を変更しました。"


def set_player_active(player_id, is_active):
    result = api_patch("players", player_id, {"is_active": is_active})
    if result is None:
        return False, "更新に失敗しました。"
    return True, "更新しました。"


# =========================
# 対戦保存・取得
# =========================
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
        rows.append({
            "game_id": game_id,
            "player_id": player_id,
            "point": int(point),
        })

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
# 表作成
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
            stats[name] = {
                "名前": name,
                "対戦数": 0,
                "プラス回数": 0,
                "マイナス回数": 0,
                "合計点": 0,
                "最高点": point,
                "最低点": point,
            }
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
        table.append({
            "名前": data["名前"],
            "対戦数": count,
            "合計点": data["合計点"],
            "平均点": round(avg, 1),
            "プラス率": f"{plus_rate:.1f}%",
            "最高点": data["最高点"],
            "最低点": data["最低点"],
        })
    table.sort(key=lambda x: x["合計点"], reverse=True)
    return table


def menu_button(label, icon, key):
    return st.button(f"{icon}\n\n{label}", key=key, use_container_width=True)


# =========================
# 画面設定
# =========================
st.set_page_config(page_title="麻雀スコア管理", page_icon="🀄", layout="wide")

st.markdown(
    """
    <style>
    .stButton > button {
        height: 110px;
        font-size: 18px;
        border-radius: 18px;
        font-weight: 700;
        white-space: pre-line;
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
# 名前登録・編集
# =========================
elif st.session_state.page == "players":
    st.title("✏️ 名前登録")
    if st.button("← メニューへ戻る"):
        go("home")

    st.subheader("参加者を登録")
    new_name = st.text_input("名前")
    if st.button("登録する", type="primary"):
        ok, msg = add_player(new_name)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.warning(msg)

    st.divider()
    st.subheader("登録済みメンバー")

    players = get_players(active_only=False)
    active_players = [p for p in players if p.get("is_active", True)]
    inactive_players = [p for p in players if not p.get("is_active", True)]

    if active_players:
        st.write("表示中のメンバー")
        for p in active_players:
            c1, c2, c3, c4 = st.columns([1, 4, 2, 2])
            c1.write(f"ID: {p['id']}")
            new_value = c2.text_input(
                "名前",
                value=p["name"],
                key=f"edit_name_{p['id']}",
                label_visibility="collapsed",
            )
            if c3.button("名前変更", key=f"update_{p['id']}"):
                ok, msg = update_player_name(p["id"], new_value)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)

            if c4.button("非表示", key=f"inactive_{p['id']}"):
                ok, msg = set_player_active(p["id"], False)
                if ok:
                    st.success("非表示にしました。過去データは残ります。")
                    st.rerun()
                else:
                    st.warning(msg)
    else:
        st.info("表示中のメンバーはいません。")

    st.divider()
    st.subheader("非表示メンバー")
    if inactive_players:
        for p in inactive_players:
            c1, c2, c3 = st.columns([1, 4, 2])
            c1.write(f"ID: {p['id']}")
            c2.write(p["name"])
            if c3.button("復活", key=f"active_{p['id']}"):
                ok, msg = set_player_active(p["id"], True)
                if ok:
                    st.success("復活しました。")
                    st.rerun()
                else:
                    st.warning(msg)
    else:
        st.info("非表示メンバーはいません。")


# =========================
# 対戦スタート
# =========================
elif st.session_state.page == "start":
    st.title("🎮 対戦スタート")
    if st.button("← メニューへ戻る"):
        go("home")

    players = get_players(active_only=True)
    if len(players) < 4:
        st.warning("先に4人以上の名前を登録してください。")
    else:
        player_names = [p["name"] for p in players]
        selected_names = st.multiselect(
            "今回の4人を選択",
            player_names,
            default=player_names[:4],
            max_selections=4,
        )
        selected_players = [p for p in players if p["name"] in selected_names]

        if len(selected_players) != 4:
            st.info("4人選択してください。")
        else:
            st.write("上から3人分を入力すると、4人目は自動で合計0になります。")
            points = {}
            total_manual = 0
            cols = st.columns(4)
            for i, player in enumerate(selected_players):
                with cols[i]:
                    if i < 3:
                        point = st.number_input(
                            f"{player['name']} の点数",
                            value=0,
                            step=5,
                            key=f"point_{player['id']}",
                        )
                        points[player["id"]] = int(point)
                        total_manual += int(point)
                    else:
                        auto_point = -total_manual
                        st.metric(f"{player['name']} の点数", auto_point)
                        points[player["id"]] = int(auto_point)

            total = sum(points.values())
            st.write(f"合計：**{total}**")
            memo = st.text_input("メモ", placeholder="例：6/7 1回目、休日麻雀 など")

            preview = []
            id_to_name = {p["id"]: p["name"] for p in selected_players}
            for pid, point in points.items():
                preview.append({"名前": id_to_name[pid], "点数": point})
            preview.sort(key=lambda x: x["点数"], reverse=True)
            st.subheader("登録前確認")
            st.table(preview)

            if st.button("この対戦を登録する", type="primary"):
                if total != 0:
                    st.error("合計が0になっていません。")
                else:
                    ok = save_game(points, memo)
                    if ok:
                        st.success("登録しました。")
                        st.balloons()
                    else:
                        st.error("登録に失敗しました。")


# =========================
# 点数一覧
# =========================
elif st.session_state.page == "score_list":
    st.title("📋 点数一覧")
    if st.button("← メニューへ戻る"):
        go("home")

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
    if st.button("← メニューへ戻る"):
        go("home")

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
    if st.button("← メニューへ戻る"):
        go("home")

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
        st.table([
            {"回戦": r["game_no"], "点数": r["point"], "メモ": r["memo"] or ""}
            for r in personal
        ])


# =========================
# 過去の対戦履歴
# =========================
elif st.session_state.page == "history":
    st.title("🕘 過去の対戦履歴")
    if st.button("← メニューへ戻る"):
        go("home")

    results = get_results()
    if not results:
        st.info("まだ履歴がありません。")
    else:
        history = []
        for r in results:
            history.append({
                "回戦": r["game_no"],
                "名前": r["name"],
                "点数": r["point"],
                "メモ": r["memo"] or "",
            })
        st.table(history)


# =========================
# 相性分析・設定は後で追加
# =========================
elif st.session_state.page == "matchup":
    st.title("🤝 相性分析")
    if st.button("← メニューへ戻る"):
        go("home")
    st.info("次の追加機能として作ります。")

elif st.session_state.page == "settings":
    st.title("⚙️ 設定")
    if st.button("← メニューへ戻る"):
        go("home")
    st.info("次の追加機能として作ります。")
