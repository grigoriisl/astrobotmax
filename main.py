import time
import asyncio
import datetime
from datetime import timedelta
import random
from aiohttp import web
import database as db
import api_client as api
import tarot_logic as tarot
from config import WEBHOOK_URL, START_CREDITS, DAILY_BONUS_CHANCE, PORT
from logger_config import logger

WEBHOOK_PATH = "/webhook"

COST_CARD_DAY = 1
COST_YES_NO = 1
COST_3_CARDS = 2
COST_CELTIC_CROSS = 3

class WebhookHandler:
    def __init__(self):
        self.app = web.Application()
        self.app.router.add_post(WEBHOOK_PATH, self.handle_max_webhook)

    async def handle_max_webhook(self, request):
        try:
            data = await request.json()
            update_type = data.get('update_type')

            msg_timestamp_ms = data.get('timestamp') or data.get('message', {}).get('timestamp', 0)
            msg_timestamp = msg_timestamp_ms / 1000
            if msg_timestamp > 0 and (time.time() - msg_timestamp > 60):
                logger.info(f"Игнорирую старое сообщение (отставание: {int(time.time() - msg_timestamp)} сек)")
                return web.Response(status=200)

            if update_type == 'bot_started':
                user_id = data.get('user_id') or data.get('chat_id')
                if user_id:
                    user_id = str(user_id)
                    logger.info(f"Пользователь {user_id} нажал Начать")
                    await initiate_start_flow(user_id, "/start")
                return web.Response(status=200)

            elif update_type == 'message_created':
                message = data.get('message', {})
                sender = message.get('sender', {})
                user_id = sender.get('user_id')
                text = message.get('body', {}).get('text', '').strip()

                if not user_id:
                    logger.warning("Не удалось извлечь user_id из message_created")
                    return web.Response(status=200)

                user_id = str(user_id)
                logger.info(f"Сообщение от {user_id}: {text}")
                await process_message(user_id, text)

            elif update_type == 'message_callback':
                callback = data.get('callback', {})
                user_obj = callback.get('user', {})
                user_id = user_obj.get('user_id')
                payload = callback.get('payload', '')
                callback_id = callback.get('callback_id')

                if not user_id:
                    logger.warning("Не удалось извлечь user_id из message_callback")
                    return web.Response(status=200)

                user_id = str(user_id)
                logger.info(f"Callback от {user_id}: {payload}")
                if callback_id:
                    await api.answer_callback(callback_id)
                await process_callback(user_id, payload, callback_id)

            return web.Response(status=200)

        except Exception as e:
            logger.error(f"Ошибка в вебхуке: {e}", exc_info=True)
            return web.Response(status=200)

async def passive_credits_worker():
    while True:
        await asyncio.sleep(86400)
        pass

def get_menu_keyboard():
    return [
        [{"type": "callback", "text": "Карта дня", "payload": "menu_card_day"},
         {"type": "callback", "text": "Да или нет?", "payload": "menu_yes_no"}],
        [{"type": "callback", "text": "Таро – 3 карты", "payload": "menu_3_cards"},
         {"type": "callback", "text": "Кельтский крест (10)", "payload": "menu_celtic"}],
        [{"type": "callback", "text": "Купить кредиты", "payload": "menu_buy_credits"},
         {"type": "callback", "text": "Получить кредиты", "payload": "menu_ref"}],
        [{"type": "callback", "text": "Настройки", "payload": "menu_settings"},
         {"type": "callback", "text": "Бонусы", "payload": "menu_bonus"}]
    ]

def get_cancel_keyboard():
    return [[{"type": "callback", "text": "⬅️ Отмена (В меню)", "payload": "menu_main"}]]

async def mark_active(user_id: str, user):
    if user:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        try:
            if user['last_active_date'] != today:
                await db.update_user(user_id, last_active_date=today)
        except KeyError:
            await db.update_user(user_id, last_active_date=today)

async def initiate_start_flow(user_id: str, text: str):
    user = await db.get_user(user_id)
    text_lower = text.lower()
    referrer_id = None

    parts = text.split()
    if len(parts) > 1 and (text_lower.startswith("/start") or text_lower.startswith("старт")):
        potential_ref = parts[1].strip()
        if potential_ref != user_id:
            referrer_id = potential_ref

    if not user:
        await db.create_user(user_id, referrer_id)
        user = await db.get_user(user_id)

    if user['agreement_date']:
        await db.update_user(user_id, state="registered")
        await api.send_max_message(
            user_id,
            "С возвращением! Макс снова с вами 🔮",
            keyboard=get_menu_keyboard()
        )
        return

    await db.update_user(user_id, state="wait_agreement")
    agreement_kb = [[{"type": "callback", "text": "🤝 Принимаю условия", "payload": "agree_terms"}]]

    msg = (
        "⚖️ Безопасность и конфиденциальность\n\n"
        "В соответствии с законодательством Российской Федерации, для продолжения работы с ИИ-Тарологом необходимо выразить согласие на обработку вашего имени и ID профиля.\n\n"
        "Ваши данные находятся в полной безопасности и используются исключительно внутри приложения для сохранения вашей истории раскладов.\n\n"
        "📝 Ознакомиться с полным текстом соглашения можно здесь:\n"
        "https://github.com/astro-ai-bot-max/docs/blob/main/README.md\n\n"
        "Нажмите кнопку ниже, чтобы принять условия и открыть завесу тайны:"
    )

    await api.send_max_message(user_id, msg, keyboard=agreement_kb)

async def process_message(user_id: str, text: str):
    if not user_id or user_id == "None":
        return

    user = await db.get_user(user_id)
    logger.info(f"Пользователь {user_id} в стейте: {user['state'] if user else 'Новый'}")

    text_lower = text.lower()
    is_start_cmd = (
            text_lower in ["/start", "старт", "начать", "start", "get_started"] or
            text_lower.startswith("/start ") or
            text_lower.startswith("старт ")
    )

    if not user or is_start_cmd or (user and user['state'] == 'wait_agreement'):
        await initiate_start_flow(user_id, text)
        return

    if user.get('agreement_date'):
        today = datetime.date.today()
        last_active = user.get('last_active_date')
        if last_active:
            try:
                last_date = datetime.datetime.strptime(last_active, "%Y-%m-%d").date()
                days_inactive = (today - last_date).days
                if days_inactive > 2 and user['credits'] == 0:
                    await db.add_credits(user_id, 1)
                    await api.send_max_message(
                        user_id,
                        "🌙 Звёзды заметили твоё долгое отсутствие… Дарят 1 кредит, чтобы ты мог снова заглянуть в завтрашний день. 🔮"
                    )
                    logger.info(f"Начислен 1 кредит за неактивность пользователю {user_id}")
            except Exception as e:
                logger.error(f"Ошибка при проверке неактивности {user_id}: {e}")

    await mark_active(user_id, user)

    if text_lower == "/id":
        await api.send_max_message(user_id, f"Ваш уникальный ID: {user_id}\n\nЕсли у вас возникли вопросы, передайте этот ID поддержке.", keyboard=get_menu_keyboard())
        return

    if text_lower in ["/menu", "меню", "/cancel", "/reset", "отмена", "сброс"]:
        await db.update_user(user_id, state="registered")
        await api.send_max_message(user_id, "🔮 Вы вернулись в главное меню. Что подскажут карты сегодня?", keyboard=get_menu_keyboard())
        return

    if text_lower == "/stats":
        if user['is_admin']:
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            stats = await db.get_stats(today)
            msg = (f"📊 Статистика Бота:\n\n"
                   f"👥 Всего пользователей: {stats['total']}\n"
                   f"💎 VIP-пользователей: {stats['vip']}\n"
                   f"🔥 Активных сегодня (DAU): {stats['active']}")
            await api.send_max_message(user_id, msg, keyboard=get_menu_keyboard())
        else:
            await api.send_max_message(user_id, "❌ У вас нет прав администратора.", keyboard=get_menu_keyboard())
        return

    if text_lower.startswith("/admin"):
        parts = text.split()
        if len(parts) > 1 and parts[1] == "7777":
            await db.update_user(user_id, is_admin=1)
            await api.send_max_message(user_id, "👑 Доступ администратора получен!\nТеперь вам доступна команда /stats для просмотра аналитики, а также обход VIP-блокировок.", keyboard=get_menu_keyboard())
        else:
            await api.send_max_message(user_id, "❌ Неверный пароль доступа.")
        return

    if text_lower.startswith("/addcredits"):
        if user['is_admin']:
            parts = text.split()
            if len(parts) == 3:
                target_id = parts[1]
                try:
                    amount = int(parts[2])
                    target_user = await db.get_user(target_id)
                    if target_user:
                        await db.add_credits(target_id, amount)
                        await api.send_max_message(user_id, f"✅ Пользователю {target_id} начислено {amount} кредитов.")
                        try:
                            await api.send_max_message(target_id, f"💰 Администратор начислил вам {amount} кредитов! Баланс обновлён.")
                        except:
                            pass
                    else:
                        await api.send_max_message(user_id, "❌ Пользователь с таким ID не найден.")
                except ValueError:
                    await api.send_max_message(user_id, "❌ Неверная сумма. Используйте: /addcredits ID СУММА")
            else:
                await api.send_max_message(user_id, "❌ Использование: /addcredits ID СУММА")
        else:
            await api.send_max_message(user_id, "❌ У вас нет прав администратора.")
        return

    if text_lower == "/secrettrikredita":
        await db.add_credits(user_id, 3)
        await api.send_max_message(user_id, "🤫 Вы активировали тайный код! Карты дарят вам 3 кредита.", keyboard=get_menu_keyboard())
        return

    if user['state'] == 'wait_name':
        await db.update_user(user_id, name=text, state="wait_dob")
        await api.send_max_message(user_id, f"Прекрасное имя, {text}! ✨\nТеперь введите дату своего рождения в формате ДД.ММ.ГГГГ (Например, 30.01.2000). Это поможет мне настроиться на ваш поток энергии:")
        return

    if user['state'] == 'wait_dob':
        zodiac = tarot.get_zodiac(text)
        await db.update_user(user_id, birth_date=text, zodiac=zodiac, state="registered", credits=START_CREDITS)
        msg = f"Добро пожаловать в мир Таро, {user['name']}! 🌙\nЯ начислил вам {START_CREDITS} кредита.\nВаша судьба уже начала открывать свои тайны... Что вы хотите узнать прямо сейчас?"
        await api.send_max_message(user_id, msg, keyboard=get_menu_keyboard())

        if user['referrer_id']:
            ref_id = user['referrer_id']
            await db.add_credits(ref_id, 3)
            ref_notification = (
                f"🎉 По вашей ссылке зарегистрировался новый искатель истины ({user['name']})!\n"
                f"Вам начислено 3 бонусных кредита. Карты благосклонны к вам!"
            )
            await api.send_max_message(ref_id, ref_notification)
        return

    if user['state'] == 'edit_name':
        await db.update_user(user_id, name=text, state="registered")
        await api.send_max_message(user_id, f"✨ Ваше имя успешно изменено на {text}. Как я могу помочь вам сегодня?", keyboard=get_menu_keyboard())
        return

    if user['state'] == 'edit_dob':
        zodiac = tarot.get_zodiac(text)
        await db.update_user(user_id, birth_date=text, zodiac=zodiac, state="registered")
        await api.send_max_message(user_id, f"✨ Дата рождения обновлена! Я вижу, ваш знак: {zodiac}. Карты ждут ваших вопросов:", keyboard=get_menu_keyboard())
        return

    if user['state'] == 'wait_yes_no':
        if user['credits'] < COST_YES_NO:
            await api.send_max_message(user_id, "❌ Недостаточно кредитов. Пожалуйста, выберите другой пункт или пополните баланс.", keyboard=get_menu_keyboard())
            await db.update_user(user_id, state="registered")
            return

        await db.add_credits(user_id, -COST_YES_NO)
        await db.update_user(user_id, state="registered")
        await api.send_max_message(user_id, "✨ Раскидываю карты, вслушиваюсь в линии вероятностей...")

        card = tarot.get_random_cards(1)[0]
        path = tarot.get_card_path(card['name'], card['is_reversed'])
        image_token = await api.upload_local_image_to_max(path)

        await api.send_max_message(user_id, f"Ваш ответ кроется здесь: {card['name']} ({card['position']})", image_token=image_token)

        prompt = (
            f"Вопрос человека: {text}. Выпала карта {card['name']} ({card['position']}). "
            f"Дай четкий мистический ответ (Да или Нет) и краткую затягивающую расшифровку на 2-3 предложения. "
            f"ПРАВИЛА ОФОРМЛЕНИЯ: Категорически запрещено использовать markdown (* или #). Вместо жирного шрифта или выделений используй эмодзи (🔮, ✨, 🌙). Никаких звездочек в тексте! "
            f"Пиши СРАЗУ по дело, начни с интригующего эмодзи-заголовка, без приветствий. "
            f"В самом конце добавь одну сильную интригующую фразу, побуждая человека сделать детальный расклад на 3 карты."
        )

        ans = await api.ask_ai(prompt)
        await api.send_max_message(user_id, ans, keyboard=get_menu_keyboard())
        return

    if text_lower in ["карта дня", "карта"]:
        await process_callback(user_id, "menu_card_day")
        return

    if user['state'] == 'registered':
        await api.send_max_message(user_id, "Я понимаю только магические команды или запросы из меню. Пожалуйста, выберите нужное действие 👇", keyboard=get_menu_keyboard())

async def process_callback(user_id: str, payload: str, callback_id: str = None):
    if payload.lower() in ["start", "/start", "старт", "начать", "get_started"]:
        await initiate_start_flow(user_id, "/start")
        return

    user = await db.get_user(user_id)
    if not user:
        return

    if user.get('agreement_date'):
        today = datetime.date.today()
        last_active = user.get('last_active_date')
        if last_active:
            try:
                last_date = datetime.datetime.strptime(last_active, "%Y-%m-%d").date()
                days_inactive = (today - last_date).days
                if days_inactive > 2 and user['credits'] == 0:
                    await db.add_credits(user_id, 1)
                    await api.send_max_message(
                        user_id,
                        "🌙 Звёзды заметили твоё долгое отсутствие… Дарят 1 кредит, чтобы ты мог снова заглянуть в завтрашний день. 🔮"
                    )
                    logger.info(f"Начислен 1 кредит за неактивность пользователю {user_id}")
            except Exception as e:
                logger.error(f"Ошибка при проверке неактивности {user_id}: {e}")

    await mark_active(user_id, user)

    if payload == "agree_terms":
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.update_user(user_id, agreement_date=now_str, state="wait_name")
        logger.info(f"Пользователь {user_id} принял условия соглашения в {now_str}")
        await api.send_max_message(user_id, "✨ Согласие успешно принято и зафиксировано.\n\nЯ готов настроиться на ваше энергополе. Напишите, пожалуйста, ваше имя:")
        return

    if payload == "menu_card_day":
        if user['credits'] < COST_CARD_DAY:
            await api.send_max_message(user_id, f"❌ Недостаточно кредитов. Для расклада Карта Дня необходим {COST_CARD_DAY} кредит. Пополните ваш баланс в меню покупки 👇", keyboard=get_menu_keyboard())
            return

        await db.add_credits(user_id, -COST_CARD_DAY)
        await api.send_max_message(user_id, "✨ Тасую колоду, чтобы вытянуть карту вашей судьбы на сегодня...")

        card = tarot.get_random_cards(1)[0]
        path = tarot.get_card_path(card['name'], card['is_reversed'])
        image_token = await api.upload_local_image_to_max(path)

        await api.send_max_message(user_id, f"Карта этого дня: {card['name']} ({card['position']})", image_token=image_token)

        prompt = (
            f"Человека зовут {user['name']}, выпала карта дня: {card['name']} ({card['position']}). "
            f"Напиши захватывающий и интригующий прогноз на этот day. "
            f"ПРАВИЛА ОФОРМЛЕНИЯ: Категорически запрещено использовать markdown (* или #). Вместо выделений и заголовков используй смысловые эмодзи. Никаких звездочек в тексте! "
            f"Пиши СРАЗУ по делу. Разбей текст на 2 логических блока, каждый начни с цепляющего эмодзи-заголовка. "
            f"В самом конце добавь скрытое пророчество-интригу или острый вопрос, который заставит человека размышлять о судьбе."
        )

        ans = await api.ask_ai(prompt)
        await asyncio.sleep(1)
        await api.send_max_message(user_id, ans, keyboard=get_menu_keyboard())

    elif payload == "menu_yes_no":
        if user['credits'] < COST_YES_NO:
            await api.send_max_message(user_id, f"❌ Недостаточно кредитов. Для ответа Да или Нет необходим {COST_YES_NO} кредит. Пополните ваш баланс 👇", keyboard=get_menu_keyboard())
            return
        await db.update_user(user_id, state="wait_yes_no")
        await api.send_max_message(user_id, "Сформулируйте ваш вопрос так, чтобы на него можно было ответить 'Да' или 'Нет', и отправьте мне:", keyboard=get_cancel_keyboard())

    elif payload == "menu_3_cards":
        if user['credits'] < COST_3_CARDS:
            await api.send_max_message(user_id, f"❌ Недостаточно кредитов. Для расклада необходимо {COST_3_CARDS} кредита. Пополните ваш баланс 👇", keyboard=get_menu_keyboard())
            return

        await db.add_credits(user_id, -COST_3_CARDS)
        await api.send_max_message(user_id, "✨ Погружаюсь в линии вашего Прошлого, Настоящего и Будущего...")

        cards = tarot.get_random_cards(3)
        positions_text = ["Прошлое", "Настоящее", "Будущее"]

        for i in range(3):
            card = cards[i]
            path = tarot.get_card_path(card['name'], card['is_reversed'])
            image_token = await api.upload_local_image_to_max(path)
            await api.send_max_message(user_id, f"⏳ {positions_text[i]}: {card['name']} ({card['position']})", image_token=image_token)
            await asyncio.sleep(0.3)

        await api.send_max_message(user_id, "Вплетаю нити 3 карт в единый узор вашей судьбы. Вслушиваюсь в их шепот...")

        prompt = (
            f"Имя человека: {user['name']}. Сделай глубокий, загадочный анализ расклада на 3 карты: "
            f"1 (Прошлое) - {cards[0]['name']} ({cards[0]['position']}), "
            f"2 (Настоящее) - {cards[1]['name']} ({cards[1]['position']}), "
            f"3 (Будущее) - {cards[2]['name']} ({cards[2]['position']}). "
            f"Свяжи их в единую захватывающую историю. "
            f"ПРАВИЛА ОФОРМЛЕНИЯ: Категорически запрещено использовать markdown (* или #). Вместо жирного шрифта используй эмодзи-маркеры. Ни одной звездочки в тексте! "
            f"Пиши СРАЗУ по делу. Каждую позицию выдели интригующим заголовком с эмодзи. "
            f"В конце добавь мощную интригующую фразу-крючок, намекающую, что для полной картины необходим великий Кельтский крест."
        )

        ans = await api.ask_ai(prompt)
        await api.send_max_message(user_id, ans, keyboard=get_menu_keyboard())

    elif payload == "menu_celtic":
        if not user['is_vip'] and not user['is_admin']:
            vip_kb = [
                [{"type": "callback", "text": "💎 Оформить VIP", "payload": "menu_buy_credits"}],
                [{"type": "callback", "text": "⬅️ В меню", "payload": "menu_main"}]
            ]
            await api.send_max_message(user_id, "🔮 Доступ закрыт.\nДля использования глубокого и мощного расклада «Кельтский крест» требуется VIP-подписка «Оракул».\nОна откроет вам все тайны без ограничений.", keyboard=vip_kb)
            return

        if user['credits'] < COST_CELTIC_CROSS:
            await api.send_max_message(user_id, f"❌ Недостаточно кредитов. Великий расклад требует {COST_CELTIC_CROSS} кредита. Пополните ваш баланс 👇", keyboard=get_menu_keyboard())
            return

        await db.add_credits(user_id, -COST_CELTIC_CROSS)
        await api.send_max_message(user_id, "✨ Разворачиваю великий Кельтский крест. 10 карт ложатся на алтарь судьбы...")

        cards = tarot.get_random_cards(10)
        positions_text = [
            "1. Суть проблемы", "2. Препятствие", "3. Корень (подсознание)",
            "4. Недавнее прошлое", "5. Венец (сознательное)", "6. Ближайшее будущее",
            "7. Ваша позиция", "8. Внешнее окружение", "9. Надежды и страхи", "10. Итог"
        ]

        for i in range(10):
            card = cards[i]
            path = tarot.get_card_path(card['name'], card['is_reversed'])
            image_token = await api.upload_local_image_to_max(path)
            await api.send_max_message(user_id, f"🎴 {positions_text[i]}: {card['name']} ({card['position']})", image_token=image_token)
            await asyncio.sleep(0.3)

        await api.send_max_message(user_id, "Вслушиваюсь в шепот карт, чтобы связать их воедино...")

        prompt = (
            f"Имя человека: {user['name']}. Сделай монументальный, глубокий и безумно интригующий анализ расклада 'Кельтский крест' (10 карт):\n"
            f"1 (Суть) - {cards[0]['name']} ({cards[0]['position']})\n"
            f"2 (Препятствие) - {cards[1]['name']} ({cards[1]['position']})\n"
            f"3 (Корень/База) - {cards[2]['name']} ({cards[2]['position']})\n"
            f"4 (Прошлое) - {cards[3]['name']} ({cards[3]['position']})\n"
            f"5 (Венец/Цели) - {cards[4]['name']} ({cards[4]['position']})\n"
            f"6 (Будущее) - {cards[5]['name']} ({cards[5]['position']})\n"
            f"7 (Сам человек) - {cards[6]['name']} ({cards[6]['position']})\n"
            f"8 (Окружение) - {cards[7]['name']} ({cards[7]['position']})\n"
            f"9 (Надежды/Страхи) - {cards[8]['name']} ({cards[8]['position']})\n"
            f"10 (Итог) - {cards[9]['name']} ({cards[9]['position']}).\n"
            f"ПРАВИЛА ОФОРМЛЕНИЯ: Категорически запрещено использовать markdown (* или #). Вместо них используй мощные эмодзи. Ни одной звездочки в тексте! "
            f"Пиши СРАЗУ по делу. Структурируй текст загадочными эмодзи-заголовками для блоков (без цифр позиций). "
            f"Описывай тайные сплетения карт как раскрытие древнего свитка. Закончи грандиозным, завораживающим пророческим советом. Не ограничивай себя в символах."
        )

        ans = await api.ask_ai(prompt)

        chunk_size = 3900
        if len(ans) <= chunk_size:
            await api.send_max_message(user_id, ans, keyboard=get_menu_keyboard())
        else:
            for i in range(0, len(ans), chunk_size):
                chunk = ans[i:i + chunk_size]
                if i + chunk_size >= len(ans):
                    await api.send_max_message(user_id, chunk, keyboard=get_menu_keyboard())
                else:
                    await api.send_max_message(user_id, chunk)
                    await asyncio.sleep(0.3)

    elif payload == "menu_buy_credits":
        try: vip_until = user['vip_until']
        except Exception: vip_until = None

        if user['is_vip']: vip_status = f"✅ Активна (до {vip_until})" if vip_until else "✅ Активна"
        else: vip_status = "❌ Нет (Базовый доступ)"

        shop_text = (
            f"💰 Ваш баланс: {user['credits']} кредитов\n"
            f"👑 VIP-статус: {vip_status}\n"
            "➖➖➖➖➖➖➖➖➖➖\n\n"
            "🔮 Выберите свой узел силы и откройте тайны будущего!\n"
            "Кредиты позволяют делать глубокие расклады и получать самые точные подсказки от ИИ-Таролога.\n\n"
            "✨ Пакет «Искра» — 49 руб.\n"
            "▫️ 2 кредита (хватит на 2 обычных расклада)\n\n"
            "🔸 Пакет «Проблеск» — 99 руб.\n"
            "▫️ 5 кредитов (хватит на 5 обычных раскладов)\n"
            "▫️ Выгода 20%\n\n"
            "🔸 Пакет «Погружение» 🔥 — 199 руб.\n"
            "▫️ 15 кредитов (15 обычных раскладов или 5 Кельтских крестов)\n"
            "▫️ Выгода 45%\n\n"
            "🔸 Пакет «Магистр» — 399 руб.\n"
            "▫️ 40 кредитов (40 обычных раскладов или 13 Кельтских крестов)\n"
            "▫️ Выгода 60%\n\n"
            "👑 VIP-Подписка «Оракул» 🌟 — 499 руб / мес\n"
            "▫️ 60 кредитов на месяц + Полный доступ к мощному раскладу «Кельтский крест»."
        )
        shop_kb = [
            [
                {"type": "link", "text": "✨ Искра — 49₽", "url": "https://yoursite.ru/pay?pack=iskra"},
                {"type": "link", "text": "🔸 Проблеск — 99₽", "url": "https://yoursite.ru/pay?pack=problesk"}
            ],
            [
                {"type": "link", "text": "🔥 Погружение — 199₽", "url": "https://yoursite.ru/pay?pack=pogruzhenie"},
                {"type": "link", "text": "🔸 Магистр — 399₽", "url": "https://yoursite.ru/pay?pack=magistr"}
            ],
            [{"type": "link", "text": "👑 VIP «Оракул» — 499₽/мес", "url": "https://yoursite.ru/pay?pack=vip"}],
            [{"type": "callback", "text": "⬅️ В меню", "payload": "menu_main"}]
        ]
        await api.send_max_message(user_id, shop_text, keyboard=shop_kb)

    elif payload == "menu_ref":
        msg = (
            f"👥 У вас {user['credits']} кредитов.\n\n"
            f"Зовите друзей и получайте 3 бонусных кредита за каждого, кто пройдет регистрацию! Своим друзьям вы также подарите стартовые 3 кредита.\n\n"
            f"🔗 Ваша личная ссылка для платформы MAX:\n"
            f"https://max.ru/id772881857206_bot?start={user_id}"
        )
        await api.send_max_message(user_id, msg, keyboard=get_menu_keyboard())

    elif payload == "menu_settings":
        settings_text = f"⚙️ Настройки профиля\nВаше имя: {user['name']}\nДата рождения: {user['birth_date']}\nЗнак зодиака: {user['zodiac']}\n\nЧто вы хотите изменить?"
        settings_kb = [
            [{"type": "callback", "text": "Изменить имя", "payload": "settings_name"}],
            [{"type": "callback", "text": "Изменить дату рождения", "payload": "settings_dob"}],
            [{"type": "callback", "text": "⬅️ Назад в меню", "payload": "menu_main"}]
        ]
        await api.send_max_message(user_id, settings_text, keyboard=settings_kb)

    elif payload == "settings_name":
        await db.update_user(user_id, state="edit_name")
        await api.send_max_message(user_id, "Введите ваше новое имя:", keyboard=get_cancel_keyboard())

    elif payload == "settings_dob":
        await db.update_user(user_id, state="edit_dob")
        await api.send_max_message(user_id, "Введите новую дату рождения в формате ДД.ММ.ГГГГ (Например, 30.01.2000):", keyboard=get_cancel_keyboard())

    elif payload == "menu_bonus":
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        if user['last_bonus_date'] == today:
            await api.send_max_message(user_id, "Вы уже забирали дар сегодня. Звезды просят подождать до завтра.", keyboard=get_menu_keyboard())
        else:
            await db.update_user(user_id, last_bonus_date=today)
            if random.random() <= DAILY_BONUS_CHANCE:
                await db.add_credits(user_id, 1)
                await api.send_max_message(user_id, "Поздравляю! Карты благосклонны, вам выпал 1 бонусный кредит 🔮", keyboard=get_menu_keyboard())
            else:
                await api.send_max_message(user_id, "Сегодня бонус не выпал, но судьба изменчива. Попробуйте завтра!", keyboard=get_menu_keyboard())

    elif payload == "menu_main":
        await db.update_user(user_id, state="registered")
        await api.send_max_message(user_id, "🔮 Карты ждут твоих вопросов. Выбери, что мы узнаем сегодня:", keyboard=get_menu_keyboard())

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.init_db())

    handler = WebhookHandler()
    app = handler.app

    async def on_startup(app):
        res = await api.register_webhook(WEBHOOK_URL)
        logger.info(f"Подписка Webhook результат: {res}")
        asyncio.create_task(passive_credits_worker())

    app.on_startup.append(on_startup)

    logger.info(f"Запуск бота на порту {PORT}...")
    web.run_app(app, host="127.0.0.1", port=PORT)