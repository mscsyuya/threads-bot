"""
Threads自動投稿スクリプト v2
- 重複防止:過去7日間に投稿したものは選ばない
- 履歴は posted_history.json に記録
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
COOLDOWN_DAYS = 7  # 同じ投稿を再利用しないクールダウン期間


def load_history():
    """投稿履歴を読み込む。なければ空辞書"""
    if not os.path.exists(HISTORY_FILE):
        return {}
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_history(history):
    """投稿履歴を保存"""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def select_post(posts, history):
    """
    クールダウン期間外の投稿からランダムに選ぶ。
    全部使い切ったら、一番古く使ったやつから再利用。
    """
    now = datetime.now(timezone.utc)
    cooldown = timedelta(days=COOLDOWN_DAYS)

    # 使える投稿を抽出
    available = []
    for p in posts:
        last_posted = history.get(p["id"])
        if last_posted is None:
            # 一度も投稿してない
            available.append(p)
        else:
            last_dt = datetime.fromisoformat(last_posted)
            if now - last_dt > cooldown:
                available.append(p)

    if available:
        return random.choice(available)

    # 全部クールダウン中なら、最も古く使った投稿を再利用
    print("警告: 全投稿がクールダウン中。最も古い投稿を再利用します")
    oldest = min(posts, key=lambda p: history.get(p["id"], "0"))
    return oldest


def post_text(text):
    """テキスト投稿:コンテナ作成→30秒待機→publish"""
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

    # 投稿候補と履歴を読み込み
    with open(POSTS_FILE, "r", encoding="utf-8") as f:
        posts = json.load(f)
    history = load_history()

    if not posts:
        print("エラー: posts.json が空")
        sys.exit(1)

    # クールダウンを考慮して選択
    selected = select_post(posts, history)
    text = selected["text"]
    post_id = selected["id"]

    print(f"=== 選択された投稿: {post_id} ({len(text)}字) ===")
    print(text)
    print(f"=" * 40)

    # 投稿実行
    post_text(text)

    # 履歴に記録
    history[post_id] = datetime.now(timezone.utc).isoformat()
    save_history(history)
    print(f"履歴に記録: {post_id}")


if __name__ == "__main__":
    main()
