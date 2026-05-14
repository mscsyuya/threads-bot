"""
Threadsの新着コメントを検知してLINEに通知するスクリプト
- 自分の最新10投稿のコメントをチェック
- 過去に通知済みのコメントはスキップ(notified_comments.json)
- 新着があればLINEに通知
"""
import os
import json
import sys
from datetime import datetime, timezone
import requests

# 環境変数
THREADS_ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN")
THREADS_USER_ID = os.environ.get("THREADS_USER_ID")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

THREADS_BASE = "https://graph.threads.net/v1.0"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
NOTIFIED_FILE = "notified_comments.json"
CHECK_LATEST_POSTS = 10  # 直近何件の自分の投稿をチェックするか
NOTIFIED_RETENTION = 200  # 通知済みID履歴の保持上限


def load_notified():
    """通知済みコメントID履歴を読み込み"""
    if not os.path.exists(NOTIFIED_FILE):
        return []
    try:
        with open(NOTIFIED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"警告: {NOTIFIED_FILE}が壊れているのでリセット")
        return []


def save_notified(notified_list):
    """通知済みコメントID履歴を保存(最新N件のみ)"""
    # 最新N件だけ保持
    trimmed = notified_list[-NOTIFIED_RETENTION:]
    with open(NOTIFIED_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)


def get_my_recent_posts():
    """自分の最新N投稿を取得"""
    res = requests.get(
        f"{THREADS_BASE}/{THREADS_USER_ID}/threads",
        params={
            "fields": "id,text,permalink,timestamp",
            "limit": CHECK_LATEST_POSTS,
            "access_token": THREADS_ACCESS_TOKEN,
        },
        timeout=30,
    )
    if res.status_code != 200:
        print(f"エラー: 自分の投稿取得失敗 [{res.status_code}]")
        print(res.text)
        sys.exit(1)
    return res.json().get("data", [])


def get_replies(media_id):
    """指定投稿のリプライ(コメント)を取得"""
    res = requests.get(
        f"{THREADS_BASE}/{media_id}/replies",
        params={
            "fields": "id,text,username,timestamp,from",
            "access_token": THREADS_ACCESS_TOKEN,
        },
        timeout=30,
    )
    if res.status_code != 200:
        # 投稿によってはリプライ取得できないことがある(削除済みなど)
        print(f"  リプライ取得スキップ [{res.status_code}] media_id={media_id}")
        return []
    return res.json().get("data", [])


def send_line_notification(message):
    """LINEに通知を送る"""
    res = requests.post(
        LINE_PUSH_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        },
        json={
            "to": LINE_USER_ID,
            "messages": [{"type": "text", "text": message}],
        },
        timeout=30,
    )
    if res.status_code != 200:
        print(f"エラー: LINE通知失敗 [{res.status_code}]")
        print(res.text)
        return False
    return True


def main():
    if not all([THREADS_ACCESS_TOKEN, THREADS_USER_ID, LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID]):
        print("エラー: 環境変数が未設定")
        sys.exit(1)

    notified = load_notified()
    notified_set = set(notified)
    new_notified = []
    new_count = 0

    print(f"自分の最新{CHECK_LATEST_POSTS}投稿を確認中...")
    my_posts = get_my_recent_posts()
    print(f"取得した自分の投稿: {len(my_posts)}件")

    for post in my_posts:
        post_id = post["id"]
        post_text = post.get("text", "")[:60]
        replies = get_replies(post_id)

        if not replies:
            continue

        print(f"  投稿 {post_id}: コメント{len(replies)}件")

        for reply in replies:
            reply_id = reply["id"]

            # 既に通知済みならスキップ
            if reply_id in notified_set:
                continue

            # 新着コメント発見
            reply_text = reply.get("text", "(本文なし)")
            username = reply.get("username", "(不明)")

            # 自分自身のリプライならスキップ
            from_user = reply.get("from", {})
            if from_user.get("id") == THREADS_USER_ID:
                # 自分のリプライも通知済みリストに追加(2度処理しないため)
                new_notified.append(reply_id)
                continue

            # LINE通知メッセージ作成
            permalink = post.get("permalink", "")
            notification = (
                f"💬 新着コメント\n"
                f"\n"
                f"From: @{username}\n"
                f"\n"
                f"【コメント本文】\n"
                f"{reply_text}\n"
                f"\n"
                f"【元の自分の投稿】\n"
                f"{post_text}...\n"
                f"\n"
                f"投稿URL:\n"
                f"{permalink}"
            )

            success = send_line_notification(notification)
            if success:
                print(f"  ✅ LINE通知送信: {reply_id} from @{username}")
                new_notified.append(reply_id)
                new_count += 1
            else:
                print(f"  ❌ LINE通知失敗: {reply_id}")

    # 履歴に追加
    if new_notified:
        notified.extend(new_notified)
        save_notified(notified)
        print(f"履歴に {len(new_notified)} 件追加")

    print(f"=== 完了: 新着 {new_count} 件 ===")


if __name__ == "__main__":
    main()
