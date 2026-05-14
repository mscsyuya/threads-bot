"""
Threads自動投稿スクリプト v3 (200本対応版)
- クールダウン期間: 14日
- 120日以上前の履歴を自動削除
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
COOLDOWN_DAYS = 14         # 同じ投稿を再利用しないクールダウン期間
HISTORY_RETENTION_DAYS = 120  # 履歴ファイルの保持期間


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


def clean_old_history(history):
    """120日以上前の履歴を自動削除"""
    now = datetime.now(timezone.utc)
    retention = timedelta(days=HISTORY_RETENTION_DAYS)
    cleaned = {}
    removed_count = 0
    for post_id, posted_iso in history.items():
        try:
            posted_dt = datetime.fromisoformat(posted_iso)
            if now - posted_dt <= retention:
                cleaned[post_id] = posted_iso
            else:
                removed_count += 1
        except (ValueError, TypeError):
            # 不正な日時フォーマットは保持(壊さない)
            cleaned[post_id] = posted_iso
    if removed_count > 0:
        print(f"履歴から古い記録を {removed_count} 件削除 (保持期間: {HISTORY_RETENTION_DAYS}日)")
    return cleaned


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
            available.append(p)
        else:
            try:
                last_dt = datetime.fromisoformat(last_posted)
                if now - last_dt > cooldown:
                    available.append(p)
            except (ValueError, TypeError):
                # 履歴日付が壊れてたら未投稿扱い
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

    # 履歴ロード & 古いデータ削除
    history = load_history()
    history = clean_old_history(history)

    # 投稿選択
    selected = select_post(posts, history)
    text = selected["text"]
    post_id = selected["id"]

    print(f"=== 選択された投稿: {post_id} ({len(text)}字) ===")
    print(text)
    print(f"=" * 40)

    # 投稿実行
    post_text(text)

    # 履歴更新
    history[post_id] = datetime.now(timezone.utc).isoformat()
    save_history(history)
    print(f"履歴に記録: {post_id}")


if __name__ == "__main__":
    main()
