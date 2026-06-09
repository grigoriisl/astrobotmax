import aiohttp
import asyncio
from config import MAX_API_KEY, NEURO_API_KEY, NEURO_API_URL
from logger_config import logger

def get_max_headers():
    return {
        "Authorization": MAX_API_KEY,
        "Content-Type": "application/json"
    }

async def register_webhook(url: str):
    api_url = "https://platform-api.max.ru/subscriptions"
    payload = {
        "url": f"{url}/webhook",
        "update_types": ["message_created", "message_callback", "bot_started"]
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json=payload, headers=get_max_headers()) as resp:
            return await resp.json()

async def upload_local_image_to_max(file_path: str):
    async with aiohttp.ClientSession() as session:
        upload_req_url = "https://platform-api.max.ru/uploads?type=image"
        url_resp = await session.post(upload_req_url, headers=get_max_headers())
        url_data = await url_resp.json()

        if "url" not in url_data:
            logger.error(f"Платформа MAX не выдала ссылку: {url_data}")
            return None

        target_upload_url = url_data["url"]

        form = aiohttp.FormData()
        try:
            loop = asyncio.get_event_loop()
            with open(file_path, 'rb') as f:
                file_data = await loop.run_in_executor(None, f.read)

            form.add_field('data', file_data, filename='card.jpg', content_type='image/jpeg')

            token_resp = await session.post(target_upload_url, data=form)
            token_data = await token_resp.json()

            photos_dict = token_data.get("photos", {})
            if not photos_dict:
                logger.error(f"В ответе нет блока 'photos': {token_data}")
                return None

            first_photo_id = list(photos_dict.keys())[0]
            token = photos_dict[first_photo_id].get("token")

            if token:
                logger.info("Токен картинки успешно извлечен!")
                return token
            else:
                logger.error("Токен не найден внутри объекта фотографии!")
                return None

        except Exception as e:
            logger.error(f"Сбой при отправке файла: {e}", exc_info=True)
            return None

async def send_max_message(user_id: str, text: str, keyboard=None, image_token=None):
    url = f"https://platform-api.max.ru/messages?user_id={user_id}"
    payload = {"text": text, "attachments": []}

    if image_token:
        payload["attachments"].append({
            "type": "image",
            "payload": {"token": image_token}
        })

    if keyboard:
        payload["attachments"].append({
            "type": "inline_keyboard",
            "payload": {"buttons": keyboard}
        })

    if not payload["attachments"]:
        del payload["attachments"]

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=get_max_headers()) as resp:
            result = await resp.json()
            if resp.status != 200:
                logger.error(f"Ошибка отправки MAX: {resp.status} - {result} | payload: {payload}")
            else:
                logger.info(f"Сообщение отправлено пользователю {user_id}")
            return result

async def ask_ai(prompt: str):
    headers = {
        "Authorization": f"Bearer {NEURO_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}]}
    async with aiohttp.ClientSession() as session:
        async with session.post(NEURO_API_URL, json=data, headers=headers) as resp:
            res = await resp.json()
            return res['choices'][0]['message']['content']

async def answer_callback(callback_id: str):
    url = f"https://platform-api.max.ru/answers?callback_id={callback_id}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={}, headers=get_max_headers()) as resp:
            return await resp.json()