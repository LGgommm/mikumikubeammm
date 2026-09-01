import os
import json
import asyncio
import requests

from datetime import timezone
from zoneinfo import ZoneInfo

from mercapi import Mercapi
from upstash_redis import Redis


# ============================================================
# 환경변수
# ============================================================

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

UPSTASH_URL = os.environ["UPSTASH_REDIS_REST_URL"]
UPSTASH_TOKEN = os.environ["UPSTASH_REDIS_REST_TOKEN"]

MAX_ITEMS = 20

SEARCH_KEY = f"mercari:searches:{CHAT_ID}"
OFFSET_KEY = f"telegram:offset:{CHAT_ID}"


# ============================================================
# Redis
# ============================================================

redis = Redis(
    url=UPSTASH_URL,
    token=UPSTASH_TOKEN
)


# ============================================================
# Telegram 기본 메시지
# ============================================================

def send_message(text):

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": text
            },
            timeout=20
        )

        if not response.ok:
            print("❌ Telegram 메시지 오류:", response.text)

        return response.ok

    except Exception as e:
        print("❌ Telegram 메시지 예외:", e)
        return False


# ============================================================
# 검색조건
# ============================================================

def load_searches():

    data = redis.get(SEARCH_KEY)

    if not data:
        return []

    try:
        return json.loads(data)

    except Exception as e:
        print("❌ 검색조건 로드 오류:", e)
        return []


def save_searches(searches):

    redis.set(
        SEARCH_KEY,
        json.dumps(
            searches,
            ensure_ascii=False
        )
    )


# ============================================================
# Telegram 명령어
# ============================================================

def process_command(text):

    searches = load_searches()

    # --------------------------------------------------------
    # /help
    # --------------------------------------------------------

    if text == "/help":

        send_message(
            "🤖 메루카리 알림 봇\n\n"

            "검색 조건 추가\n"
            "/add 키워드 최소가격 최대가격\n\n"

            "검색 목록\n"
            "/list\n\n"

            "검색 조건 삭제\n"
            "/delete 번호\n\n"

            "전체 삭제\n"
            "/clear\n\n"

            "예시\n"
            "/add 初音ミク 0 50000\n"
            "/add ピカチュウ PSA10 1000 30000"
        )

        return


    # --------------------------------------------------------
    # /list
    # --------------------------------------------------------

    if text == "/list":

        if not searches:

            send_message(
                "📭 등록된 검색 조건이 없습니다."
            )

            return

        message = "📋 현재 검색 조건\n\n"

        for i, search in enumerate(searches, start=1):

            message += (
                f"{i}. {search['keyword']}\n"
                f"   ¥{search['min_price']:,}"
                f" ~ ¥{search['max_price']:,}\n\n"
            )

        send_message(message)

        return


    # --------------------------------------------------------
    # /clear
    # --------------------------------------------------------

    if text == "/clear":

        save_searches([])

        send_message(
            "🗑 모든 검색 조건을 삭제했습니다."
        )

        return


    # --------------------------------------------------------
    # /delete
    # --------------------------------------------------------

    if text.startswith("/delete"):

        parts = text.split()

        if len(parts) != 2:

            send_message(
                "사용법: /delete 번호\n\n"
                "예: /delete 2"
            )

            return

        try:
            index = int(parts[1]) - 1

        except ValueError:

            send_message(
                "❌ 번호를 숫자로 입력해주세요."
            )

            return

        if index < 0 or index >= len(searches):

            send_message(
                "❌ 해당 번호의 검색 조건이 없습니다."
            )

            return

        removed = searches.pop(index)

        save_searches(searches)

        send_message(
            "🗑 검색 조건 삭제 완료\n\n"
            f"🔎 {removed['keyword']}"
        )

        return


    # --------------------------------------------------------
    # /add
    # --------------------------------------------------------

    if text.startswith("/add"):

        parts = text.split()

        if len(parts) < 4:

            send_message(
                "사용법\n\n"
                "/add 키워드 최소가격 최대가격\n\n"
                "예시\n"
                "/add 初音ミク 0 50000"
            )

            return

        try:

            min_price = int(
                parts[-2].replace(",", "")
            )

            max_price = int(
                parts[-1].replace(",", "")
            )

        except ValueError:

            send_message(
                "❌ 가격은 숫자로 입력해주세요.\n\n"
                "예: /add 初音ミク 0 50000"
            )

            return

        keyword = " ".join(parts[1:-2]).strip()

        if not keyword:

            send_message(
                "❌ 검색 키워드를 입력해주세요."
            )

            return

        if min_price < 0 or max_price < 0:

            send_message(
                "❌ 가격은 0 이상이어야 합니다."
            )

            return

        if min_price > max_price:

            send_message(
                "❌ 최소가격이 최대가격보다 클 수 없습니다."
            )

            return

        # 동일 조건 중복 방지
        for search in searches:

            if (
                search["keyword"] == keyword
                and search["min_price"] == min_price
                and search["max_price"] == max_price
            ):

                send_message(
                    "⚠️ 이미 동일한 검색 조건이 있습니다."
                )

                return

        searches.append({
            "keyword": keyword,
            "min_price": min_price,
            "max_price": max_price
        })

        save_searches(searches)

        send_message(
            "✅ 검색 조건 추가 완료\n\n"
            f"🔎 {keyword}\n"
            f"💴 ¥{min_price:,} ~ ¥{max_price:,}"
        )

        return


# ============================================================
# Telegram 명령어 확인
# ============================================================

def check_telegram_commands():

    offset = redis.get(OFFSET_KEY)

    if offset:
        offset = int(offset)
    else:
        offset = 0

    try:

        response = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
            params={
                "offset": offset,
                "timeout": 0,
                "allowed_updates": json.dumps(["message"])
            },
            timeout=20
        )

        data = response.json()

    except Exception as e:

        print(
            "❌ Telegram getUpdates 오류:",
            e
        )

        return

    if not data.get("ok"):

        print(
            "❌ Telegram API 오류:",
            data
        )

        return

    for update in data.get("result", []):

        update_id = update["update_id"]

        # 먼저 다음 offset 기록
        redis.set(
            OFFSET_KEY,
            update_id + 1
        )

        message = update.get("message")

        if not message:
            continue

        chat = message.get(
            "chat",
            {}
        )

        # 본인만 사용 가능
        if str(chat.get("id")) != str(CHAT_ID):

            print(
                "⚠️ 다른 사용자 명령 무시:",
                chat.get("id")
            )

            continue

        text = message.get("text")

        if not text:
            continue

        text = text.strip()

        if text.startswith("/"):

            print(
                "📨 명령어:",
                text
            )

            process_command(text)


# ============================================================
# 신규 상품 Telegram 발송
# ============================================================

def send_product(item, keyword):

    item_id = item.id_

    item_url = (
        f"https://jp.mercari.com/item/{item_id}"
    )

    # mercapi 검색 결과가 UTC naive datetime으로 반환되는
    # 현재 구조를 기준으로 JST 변환
    if item.created.tzinfo is None:

        created_utc = item.created.replace(
            tzinfo=timezone.utc
        )

    else:

        created_utc = item.created.astimezone(
            timezone.utc
        )

    created_jst = created_utc.astimezone(
        ZoneInfo("Asia/Tokyo")
    )

    created_text = created_jst.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    caption = (
        "🔥 메루카리 신규 상품\n\n"
        f"🔎 검색어: {keyword}\n\n"
        f"{item.name}\n\n"
        f"💴 가격: ¥{item.price:,}\n"
        f"🕒 등록: {created_text}"
    )

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "🇯🇵 메루카리에서 보기",
                    "url": item_url
                }
            ]
        ]
    }

    try:

        # 썸네일 존재
        if item.thumbnails:

            response = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                data={
                    "chat_id": CHAT_ID,
                    "photo": item.thumbnails[0],
                    "caption": caption,
                    "reply_markup": json.dumps(
                        keyboard,
                        ensure_ascii=False
                    )
                },
                timeout=20
            )

        # 이미지 없음
        else:

            response = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                data={
                    "chat_id": CHAT_ID,
                    "text": caption,
                    "reply_markup": json.dumps(
                        keyboard,
                        ensure_ascii=False
                    )
                },
                timeout=20
            )

        if not response.ok:

            print(
                "❌ 상품 Telegram 오류:",
                response.text
            )

        return response.ok

    except Exception as e:

        print(
            "❌ Telegram 상품 전송 예외:",
            e
        )

        return False


# ============================================================
# Mercari 검색
# ============================================================

async def monitor_mercari():

    searches = load_searches()

    if not searches:

        print(
            "📭 등록된 검색 조건 없음"
        )

        return

    print(
        f"📋 등록된 검색 조건: {len(searches)}개"
    )

    mercari = Mercapi()

    for search in searches:

        keyword = search["keyword"]

        min_price = int(
            search["min_price"]
        )

        max_price = int(
            search["max_price"]
        )

        print()
        print("=" * 60)
        print(
            f"🔎 {keyword}"
        )
        print(
            f"💴 ¥{min_price:,} ~ ¥{max_price:,}"
        )

        try:

            results = await mercari.search(
                keyword
            )

        except Exception as e:

            print(
                f"❌ Mercari 검색 실패 [{keyword}]:",
                e
            )

            continue

        print(
            "검색 결과:",
            results.meta.num_found
        )

        # 너무 많은 API/처리 방지를 위해
        # 검색 결과 상위 MAX_ITEMS만 확인
        for item in results.items[:MAX_ITEMS]:

            try:

                # 판매중만
                if (
                    item.status
                    != "ITEM_STATUS_ON_SALE"
                ):
                    continue

                # 가격 없는 상품
                if item.price is None:
                    continue

                # 가격 필터
                if item.price < min_price:
                    continue

                if item.price > max_price:
                    continue

                redis_key = (
                    f"mercari:sent:{item.id_}"
                )

                # 이미 알림 보냄
                if redis.exists(redis_key):

                    print(
                        f"⏭ 중복: {item.name}"
                    )

                    continue

                print(
                    f"🆕 신규: {item.name}"
                )

                print(
                    f"   ¥{item.price:,}"
                )

                success = send_product(
                    item,
                    keyword
                )

                if success:

                    # 30일간 중복 방지
                    redis.set(
                        redis_key,
                        "1",
                        ex=60 * 60 * 24 * 30
                    )

                    print(
                        "   ✅ 발송 완료"
                    )

                else:

                    print(
                        "   ❌ 발송 실패"
                    )

            except Exception as e:

                print(
                    "❌ 상품 처리 오류:",
                    e
                )


# ============================================================
# Main
# ============================================================

async def main():

    print(
        "🚀 Mercari Alert 시작"
    )

    # 1. Telegram에서 보낸 설정 명령 처리
    check_telegram_commands()

    # 2. 저장된 조건으로 상품 검색
    await monitor_mercari()

    print(
        "✅ Mercari Alert 종료"
    )


if __name__ == "__main__":

    asyncio.run(main())
