"""
Threads自動投稿スクリプト v4 (履歴最新N件保持版)
- クールダウン期間: 14日
- 履歴は最新100件のみ保持(古いものから自動削除)
- 120日以上前の履歴も自動削除(二重チェック)
- posts.json の構文エラーを先頭で検証
"""
import os
import time
import json
import random
import sys
from datetime import datetime, timedelta, timezone
import requests

ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN")
USER_ID = os.environ.get("THREADS_USER_ID")
BASE = "https://graph.threads.net/v1.0"

POSTS_FILE = "posts.json"
HISTORY_FILE = "posted_history.json"
COOLDOWN_DAYS = 14            # 同じ投稿を再利用しないクールダウン期間
HISTORY_RETENTION_DAYS = 120  # 履歴の最大保持日数(二重ガード)
HISTORY_MAX_ENTRIES = 100     # 履歴の最大保持件数(これを超えたら古いものから削除)


def validate_posts_json():
    """posts.json の構文チェックと内容検証"""
    if not os.path.exists(POSTS_FILE):
        print(f"エラー: {POSTS_FILE} が見つかりません")
        sys.exit(1)
    try:
        with open(POSTS_FILE, "r", encoding="utf-8") as f:
            posts = json.load(f)
    except json.JSONDecodeError as e:
        print(f"エラー: {POSTS_FILE} のJSON構文エラー")
        print(f"  行 {e.lineno}, 列 {e.colno}, 文字位置 {e.pos}")
        print(f"  詳細: {e.msg}")
        print(f"  対処: jsonlint.com で検証してください")
        sys.exit(1)
    if not isinstance(posts, list) or len(posts) == 0:
        print(f"エラー: {POSTS_FILE} は配列形式で、最低1件必要")
        sys.exit(1)
    for i, p in enumerate(posts):
        if not isinstance(p, dict) or "id" not in p or "text" not in p:
            print(f"エラー: {POSTS_FILE} の {i} 番目に id または text がない")
            sys.exit(1)
    print(f"posts.json 検証OK ({len(posts)}件)")
    return posts


def load_history():
    """投稿履歴を読み込み"""
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"警告: {HISTORY_FILE} が壊れているのでリセットします")
        return {}


def save_history(history):
    """投稿履歴を保存"""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def trim_history(history):
    """
    履歴を整理する2段階処理:
    1. 120日以上前の記録は削除(二重ガード)
    2. 件数が100件を超えてたら、古いものから順に削除して100件に保つ
    """
    now = datetime.now(timezone.utc)
    retention = timedelta(days=HISTORY_RETENTION_DAYS)

    # Step 1: 期間で削除
    period_cleaned = {}
    removed_by_age = 0
    for post_id, posted_iso in history.items():
        try:
            posted_dt = datetime.fromisoformat(posted_iso)
            if now - posted_dt <= retention:
                period_cleaned[post_id] = posted_iso
            else:
                removed_by_age += 1
        except (ValueError, TypeError):
            period_cleaned[post_id] = posted_iso

    # Step 2: 件数で削除(古い順にソートして上位N件だけ残す)
    if len(period_cleaned) > HISTORY_MAX_ENTRIES:
        # 日付の新しい順にソート(降順)
        sorted_items = sorted(
            period_cleaned.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        # 上位N件だけ残す
        trimmed = dict(sorted_items[:HISTORY_MAX_ENTRIES])
        removed_by_count = len(period_cleaned) - HISTORY_MAX_ENTRIES
        print(f"履歴削除: 期間超過 {removed_by_age}件、件数超過 {removed_by_count}件")
        print(f"履歴保持: {HISTORY_MAX_ENTRIES}件(最新)")
        return trimmed

    if removed_by_age > 0:
        print(f"履歴削除: 期間超過 {removed_by_age}件")
    print(f"履歴保持: {len(period_cleaned)}件")
    return period_cleaned


def select_post(posts, history):
    """
    クールダウン期間外の投稿からランダム選択。
    全部クールダウン中なら、最も古く使った投稿を再利用。
    """
    now = datetime.now(timezone.utc)
    cooldown = timedelta(days=COOLDOWN_DAYS)

    available = []
    for p in posts:
        last_posted = history.get(p["id"])
        if last_posted is None:
            # 履歴にない=未投稿 or 履歴から削除済み(再利用OK)
            available.append(p)
        else:
            try:
                last_dt = datetime.fromisoformat(last_posted)
                if now - last_dt > cooldown:
                    available.append(p)
            except (ValueError, TypeError):
                available.append(p)

    if available:
        print(f"利用可能な投稿: {len(available)}件 / 全{len(posts)}件")
        return random.choice(available)

    print(f"警告: 全投稿がクールダウン中 ({COOLDOWN_DAYS}日)。最も古い投稿を再利用")
    oldest = min(posts, key=lambda p: history.get(p["id"], "0"))
    return oldest


def post_text(text):
    """テキスト投稿: コンテナ作成 → 30秒待機 → publish"""
    print(f"[1/2] コンテナ作成中...")
    res = requests.post(
        f"{BASE}/{USER_ID}/threads",
        params={
            "media_type": "TEXT",
            "text": text,
            "access_token": ACCESS_TOKEN,
        },
        timeout=30,
    )
    if res.status_code != 200:
        print(f"エラー: コンテナ作成失敗 [{res.status_code}]")
        print(res.text)
        sys.exit(1)

    creation_id = res.json()["id"]
    print(f"コンテナID: {creation_id}")

    print(f"[2/2] 30秒待機後、publish...")
    time.sleep(30)

    pub = requests.post(
        f"{BASE}/{USER_ID}/threads_publish",
        params={
            "creation_id": creation_id,
            "access_token": ACCESS_TOKEN,
        },
        timeout=30,
    )
    if pub.status_code != 200:
        print(f"エラー: publish失敗 [{pub.status_code}]")
        print(pub.text)
        sys.exit(1)

    media_id = pub.json()["id"]
    print(f"投稿成功! media_id: {media_id}")
    return media_id


def main():
    if not ACCESS_TOKEN or not USER_ID:
        print("エラー: 環境変数 THREADS_ACCESS_TOKEN / THREADS_USER_ID が未設定")
        sys.exit(1)

    # JSON検証
    posts = validate_posts_json()

    # 履歴ロード
    history = load_history()

    # 投稿選択
    selected = select_post(posts, history)
    text = selected["text"]
    post_id = selected["id"]
    category = selected.get("category")

    if category:
        print(f"=== 選択された投稿: {post_id} (カテゴリ: {category}) ({len(text)}字) ===")
    else:
        print(f"=== 選択された投稿: {post_id} ({len(text)}字) ===")
    print(text)
    print(f"=" * 40)

    # 投稿実行
    post_text(text)

    # 履歴に追加してから整理(古い記録を削除して100件以下に)
    history[post_id] = datetime.now(timezone.utc).isoformat()
    history = trim_history(history)
    save_history(history)
    print(f"履歴に記録: {post_id}")


if __name__ == "__main__":
    main()
