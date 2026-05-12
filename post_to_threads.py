"""
Threads自動投稿スクリプト
posts.jsonからランダムに1件選んでThreadsに投稿する
"""
import os
import time
import json
import random
import sys
import requests

# 環境変数(GitHub Secretsから読み込まれる)
ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN")
USER_ID = os.environ.get("THREADS_USER_ID")

BASE = "https://graph.threads.net/v1.0"


def post_text(text):
    """
    テキスト投稿を実行
    1. メディアコンテナを作成
    2. 30秒待つ(Meta公式推奨)
    3. publish
    """
    # コンテナ作成
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

    # 公式推奨の30秒待機
    print(f"[2/2] 30秒待機後、publish...")
    time.sleep(30)

    # publish
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
    # 認証情報のチェック
    if not ACCESS_TOKEN or not USER_ID:
        print("エラー: 環境変数 THREADS_ACCESS_TOKEN / THREADS_USER_ID が未設定")
        sys.exit(1)

    # posts.json から投稿候補を読み込み
    with open("posts.json", "r", encoding="utf-8") as f:
        posts = json.load(f)

    if not posts:
        print("エラー: posts.json が空")
        sys.exit(1)

    # ランダムに1件選ぶ
    selected = random.choice(posts)
    text = selected["text"]
    print(f"=== 投稿内容 ({len(text)}字) ===")
    print(text)
    print(f"=" * 40)

    # 投稿実行
    post_text(text)


if __name__ == "__main__":
    main()
