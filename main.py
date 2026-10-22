"""
Slack メッセージ投稿プログラム（課題：Slack API）

Slack API を使い、ターミナルで入力したメッセージを、
.env で指定したチャンネルに投稿する。

使い方：ターミナルで  python main.py  を実行する。
"""

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

# ============================================================
# 設定（ここをまとめて書いておく）
# ============================================================

# このプログラム（main.py）が置いてあるフォルダ
BASE_DIR = Path(__file__).resolve().parent

# トークンとチャンネル ID を書いておくファイルと、その中の項目名
ENV_FILE = BASE_DIR / ".env"
ENV_EXAMPLE_FILE = BASE_DIR / ".env.example"
TOKEN_NAME = "SLACK_BOT_TOKEN"
CHANNEL_NAME = "SLACK_CHANNEL_ID"

# Bot トークンの始まりの文字（User トークンは xoxp- で始まる）
BOT_TOKEN_PREFIX = "xoxb-"

# 使う Slack API の URL
POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"  # 投稿する
PERMALINK_URL = "https://slack.com/api/chat.getPermalink"  # 投稿のリンクをもらう

# Slack の返事を待つ秒数（これを過ぎたら「応答が無い」として終わる）
TIMEOUT_SECONDS = 10

# 投稿前に表示するメッセージの区切り線
SEPARATOR = "-" * 26


# ============================================================
# F1 設定の読み込み
# ============================================================
def load_settings():
    """
    .env から Bot トークンとチャンネル ID を読み込み、(トークン, チャンネル ID) を返す。
    .env が無い・項目が空・Bot トークンでない場合は、理由を表示して終了する（F6）。
    """
    # .env の中身を「環境変数」（プログラムが読める設定値）として読み込む
    load_dotenv(ENV_FILE)
    token = os.getenv(TOKEN_NAME, "").strip()
    channel = os.getenv(CHANNEL_NAME, "").strip()

    # 空の項目を集めて、まとめて知らせる
    missing = [name for name, value in ((TOKEN_NAME, token), (CHANNEL_NAME, channel)) if not value]
    if missing:
        show_error_and_exit(
            f"{'、'.join(missing)} が設定されていません。\n"
            f"{ENV_EXAMPLE_FILE.name} をコピーして「{ENV_FILE.name}」という名前にし、\n"
            f"Bot トークンとチャンネル ID を書いてください。\n"
            f"置き場所: {BASE_DIR}"
        )
    if not token.startswith(BOT_TOKEN_PREFIX):
        show_error_and_exit(
            f"{TOKEN_NAME} が Bot トークンではありません（{BOT_TOKEN_PREFIX} で始まるはずです）。\n"
            "Slack アプリの「OAuth & Permissions」にある Bot User OAuth Token をコピーしてください。"
        )
    return token, channel


# ============================================================
# F2 メッセージの入力
# ============================================================
def ask_message():
    """
    メッセージを1行ずつ入力してもらい、改行でつないだ文字列を返す。
    空の行（何も入力せずに Enter）で入力を終わる。最初の行が空なら、もう一度聞く。
    """
    print("メッセージを入力してください（空の行で入力を終わります）")
    lines = []
    while True:
        line = input("> ")
        if line.strip() == "":
            if lines:
                break
            print("メッセージが空です。メッセージを入力してください。")
            continue
        lines.append(line)
    return "\n".join(lines)


def escape_for_slack(text):
    """
    Slack で特別な意味を持つ & < > を、入力どおりに表示される書き方に置き換える。
    （そのまま送ると <...> がリンクやメンションとして扱われることがある）
    & を最初に置き換えないと、&lt; の & まで置き換わってしまうので順番が大事。
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ============================================================
# F3 投稿前の確認
# ============================================================
def confirm_post(message):
    """
    投稿するメッセージを表示し、投稿してよいか聞く。y なら True、n なら False を返す。
    """
    print()
    print("--- 投稿するメッセージ ---")
    print(message)
    print(SEPARATOR)
    while True:
        answer = input("投稿しますか？ (y/n): ").strip().lower()
        if answer in ("y", "n"):
            return answer == "y"
        print("y か n を入力してください。")


# ============================================================
# F4 投稿
# ============================================================
def call_slack_api(url, token, data):
    """
    Slack API を1回呼び、返事（JSON）を辞書で返す。

    - トークンは「Authorization: Bearer トークン」というヘッダーで渡す
    - 中身はフォームの形（名前=値）で送る（chat.getPermalink は JSON の形を受け付けないため、そろえる）
    - Slack は失敗しても HTTP 200 を返し、中身の "ok": false と "error" で理由を知らせる
    """
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        data=data,
        timeout=TIMEOUT_SECONDS,
    )
    # 送りすぎたときだけは HTTP 429 が返る
    if response.status_code == 429:
        return {"ok": False, "error": "rate_limited"}
    return response.json()


def post_message(token, channel, message):
    """
    chat.postMessage でメッセージを投稿し、Slack の返事を返す。
    失敗したら、理由を表示して終了する（F6）。
    """
    result = call_slack_api(
        POST_MESSAGE_URL,
        token,
        {"channel": channel, "text": escape_for_slack(message)},
    )
    if not result.get("ok"):
        show_error_and_exit(explain_slack_error(result.get("error", "unknown_error")))
    return result


# ============================================================
# F5 結果の表示
# ============================================================
def show_result(token, result):
    """
    投稿できたことと、投稿のリンク（パーマリンク）を表示する。
    リンクは chat.getPermalink でもらう（スコープは要らない）。
    もらえなくても投稿はできているので、その場合はリンクを出さない。
    """
    print("投稿しました。")
    try:
        link = call_slack_api(
            PERMALINK_URL,
            token,
            # 投稿の返事の channel（チャンネル ID）と ts（投稿の番号）で、どの投稿かを指定する
            {"channel": result["channel"], "message_ts": result["ts"]},
        )
    except (requests.RequestException, ValueError):
        return
    if link.get("ok"):
        print(link["permalink"])


# ============================================================
# F6 エラー表示
# ============================================================
def show_error_and_exit(message):
    """
    原因が分かる日本語のエラーメッセージを表示して、プログラムを終了する。
    """
    print(f"エラー: {message}", file=sys.stderr)
    sys.exit(1)


def explain_slack_error(error):
    """
    Slack が返したエラーの名前（invalid_auth など）を、日本語の説明に直して返す。
    """
    # トークンが正しくない・取り消された・アプリが外された
    if error in ("invalid_auth", "not_authed", "token_revoked", "token_expired", "account_inactive"):
        return (
            "Bot トークンが正しくありません。\n"
            f"{ENV_FILE.name} の {TOKEN_NAME} が、Slack アプリの「OAuth & Permissions」にある\n"
            "Bot User OAuth Token と同じか確認してください。アプリを入れ直した場合はトークンが変わります。\n"
            f"詳細: {error}"
        )
    # チャンネルが見つからない
    # （ボットは招待されていないチャンネルを「見えない」扱いにするので、招待忘れでもこのエラーになる）
    if error == "channel_not_found":
        return (
            "投稿先のチャンネルが見つかりません。次の2つを確認してください。\n"
            "  ・ボットをそのチャンネルに招待したか（Slack でチャンネルを開き「/invite @アプリ名」と送る）\n"
            f"  ・{ENV_FILE.name} の {CHANNEL_NAME} が正しいか（チャンネル名をクリック →「チャンネル詳細」の\n"
            "    一番下にある C で始まる文字列）\n"
            f"詳細: {error}"
        )
    # ボットがチャンネルに参加していない
    if error == "not_in_channel":
        return (
            "ボットが投稿先のチャンネルに参加していません。\n"
            "Slack でそのチャンネルを開き、「/invite @アプリ名」と送ってボットを招待してください。\n"
            f"詳細: {error}"
        )
    # スコープ（できることの範囲）が足りない
    if error == "missing_scope":
        return (
            "トークンに投稿の許可（スコープ）がありません。\n"
            "Slack アプリの「OAuth & Permissions」→ Bot Token Scopes に chat:write を追加し、\n"
            "「Reinstall to ワークスペース」でアプリを入れ直してください。\n"
            f"詳細: {error}"
        )
    # 短い時間に送りすぎた
    if error == "rate_limited":
        return (
            "短い時間に送りすぎたため、Slack に止められました。少し待ってからやり直してください。\n"
            f"詳細: {error}"
        )
    return f"Slack への投稿に失敗しました。\n詳細: {error}"


# ============================================================
# メインの処理（上の関数を順番に呼ぶ）
# ============================================================
def main():
    """
    プログラム全体の流れ：
    設定の読み込み → メッセージの入力 → 投稿前の確認 → 投稿 → 結果の表示
    """
    try:
        # F1 設定の読み込み（入力より先に確かめる）
        token, channel = load_settings()
        print(f"投稿先のチャンネル：{channel}")

        # F2 メッセージの入力
        message = ask_message()

        # F3 投稿前の確認
        if not confirm_post(message):
            print("投稿をやめました。")
            return

        # F4 投稿
        result = post_message(token, channel, message)

        # F5 結果の表示
        show_result(token, result)

    except requests.Timeout:
        # 決めた秒数のうちに Slack から返事が無かった（F6）
        show_error_and_exit(
            f"Slack から {TIMEOUT_SECONDS} 秒たっても応答がありませんでした。時間をおいてやり直してください。\n"
            "（投稿されている場合もあるので、Slack のチャンネルを確認してください）"
        )
    except requests.RequestException as error:
        # インターネットにつながらない など（F6）
        show_error_and_exit(
            "Slack につながりませんでした。インターネット接続を確認してください。\n"
            f"詳細: {error}"
        )
    except (KeyboardInterrupt, EOFError):
        # Ctrl + C で途中でやめた場合
        print("\n中断しました。")
        sys.exit(1)


# このファイルを直接実行したときだけ main() を動かす
if __name__ == "__main__":
    main()
