"""
Threads長期トークンを自動リフレッシュするスクリプト
- 現在のトークンをリフレッシュエンドポイントで延長
- 新しいトークンをGitHub APIでSecretに書き込む
"""
import os
import sys
import requests
from nacl import encoding, public

CURRENT_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN")
GH_PAT = os.environ.get("GH_PAT")
GH_REPO = os.environ.get("GH_REPO", "mscsyuya/threads-bot")


def refresh_token():
    """Threadsトークンをリフレッシュ"""
    print("トークンリフレッシュ実行中...")
    url = "https://graph.threads.net/refresh_access_token"
    params = {
        "grant_type": "th_refresh_token",
        "access_token": CURRENT_TOKEN,
    }
    res = requests.get(url, params=params, timeout=30)
    if res.status_code != 200:
        print(f"エラー: リフレッシュ失敗 [{res.status_code}]")
        print(res.text)
        sys.exit(1)
    data = res.json()
    new_token = data["access_token"]
    expires_in = data.get("expires_in", 0)
    print(f"新しいトークン取得成功 (有効期限: {expires_in}秒 ≒ {expires_in // 86400}日)")
    return new_token


def get_repo_public_key():
    """リポジトリの暗号化用公開鍵を取得"""
    url = f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key"
    headers = {
        "Authorization": f"Bearer {GH_PAT}",
        "Accept": "application/vnd.github+json",
    }
    res = requests.get(url, headers=headers, timeout=30)
    if res.status_code != 200:
        print(f"エラー: 公開鍵取得失敗 [{res.status_code}]")
        print(res.text)
        sys.exit(1)
    return res.json()


def encrypt_secret(public_key_b64, secret_value):
    """Secretを公開鍵で暗号化"""
    public_key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return encoding.Base64Encoder().encode(encrypted).decode("utf-8")


def update_secret(secret_name, secret_value):
    """GitHub Secretを更新"""
    print(f"Secret '{secret_name}' を更新中...")
    key_info = get_repo_public_key()
    encrypted_value = encrypt_secret(key_info["key"], secret_value)
    url = f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{secret_name}"
    headers = {
        "Authorization": f"Bearer {GH_PAT}",
        "Accept": "application/vnd.github+json",
    }
    data = {
        "encrypted_value": encrypted_value,
        "key_id": key_info["key_id"],
    }
    res = requests.put(url, headers=headers, json=data, timeout=30)
    if res.status_code not in (201, 204):
        print(f"エラー: Secret更新失敗 [{res.status_code}]")
        print(res.text)
        sys.exit(1)
    print(f"✅ Secret '{secret_name}' 更新完了")


def main():
    if not all([CURRENT_TOKEN, GH_PAT]):
        print("エラー: 環境変数 THREADS_ACCESS_TOKEN または GH_PAT が未設定")
        sys.exit(1)
    new_token = refresh_token()
    update_secret("THREADS_ACCESS_TOKEN", new_token)
    print("=== トークンリフレッシュ完了 ===")


if __name__ == "__main__":
    main()
