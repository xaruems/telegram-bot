import asyncio
import os
import json
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import User, Channel, Chat
from telethon.types import Button
from dotenv import load_dotenv

load_dotenv()

api_id = int(os.getenv('API_ID'))
api_hash = os.getenv('API_HASH')
phone_number = os.getenv('PHONE_NUMBER')
password = os.getenv('PASSWORD', None)

# Проверяем, есть ли отдельные ID для каждой категории
admin_id_site = os.getenv('ADMIN_ID_SITE')
admin_id_design = os.getenv('ADMIN_ID_DESIGN')
admin_id_target = os.getenv('ADMIN_ID_TARGET')
admin_id_animation = os.getenv('ADMIN_ID_ANIMATION')

fallback_admin_id = os.getenv('ADMIN_ID')

# VIP ключевые слова
vip_keywords = [k.strip().lower() for k in os.getenv('VIP_KEYWORDS', '').split(',') if k.strip()]

# Разделяем ключевые слова по категориям
keywords_config = {
    'site': {
        'keywords': [k.strip().lower() for k in os.getenv('KEYWORDS_SITE', '').split(',') if k.strip()],
        'emoji': '🌐',
        'name': 'САЙТ',
        'admin_id': int(admin_id_site) if admin_id_site else int(fallback_admin_id)
    },
    'design': {
        'keywords': [k.strip().lower() for k in os.getenv('KEYWORDS_DESIGN', '').split(',') if k.strip()],
        'emoji': '🎨',
        'name': 'ДИЗАЙН',
        'admin_id': int(admin_id_design) if admin_id_design else int(fallback_admin_id)
    },
    'target': {
        'keywords': [k.strip().lower() for k in os.getenv('KEYWORDS_TARGET', '').split(',') if k.strip()],
        'emoji': '🎯',
        'name': 'ТАРГЕТ',
        'admin_id': int(admin_id_target) if admin_id_target else int(fallback_admin_id)
    },
    'animation': {
        'keywords': [k.strip().lower() for k in os.getenv('KEYWORDS_ANIMATION', '').split(',') if k.strip()],
        'emoji': '✨',
        'name': 'АНИМАЦИЯ',
        'admin_id': int(admin_id_animation) if admin_id_animation else int(fallback_admin_id)
    }
}

notified_messages = set()
monitored_chats = {}
blacklist_users = set()
invalid_users = set()


def load_blacklist():
    """Загрузить чёрный список из файла"""
    global blacklist_users, invalid_users
    try:
        if os.path.exists('blacklist.json'):
            with open('blacklist.json', 'r') as f:
                data = json.load(f)
                blacklist_users = set(data.get('blacklist', []))
                invalid_users = set(data.get('invalid', []))
                print(f"✅ Загружен чёрный список: {len(blacklist_users)} + {len(invalid_users)} неактуальных")
    except Exception as e:
        print(f"⚠️  Ошибка загрузки чёрного списка: {e}")


def save_blacklist():
    """Сохранить чёрный список в файл"""
    try:
        with open('blacklist.json', 'w') as f:
            json.dump({
                'blacklist': list(blacklist_users),
                'invalid': list(invalid_users)
            }, f, indent=2)
    except Exception as e:
        print(f"❌ Ошибка сохранения чёрного списка: {e}")


def is_vip_message(message_text):
    """Проверить, VIP ли сообщение"""
    message_lower = message_text.lower()
    for keyword in vip_keywords:
        if keyword in message_lower:
            return True
    return False


async def main():
    client = TelegramClient('session', api_id, api_hash)
    load_blacklist()

    async def get_chat_info(chat_id):
        """Получить информацию о чате с кешированием"""
        if chat_id in monitored_chats:
            return monitored_chats[chat_id]

        try:
            chat = await client.get_entity(chat_id)
            monitored_chats[chat_id] = chat
            return chat
        except Exception as e:
            print(f"⚠️  Ошибка получения информации о чате {chat_id}: {e}")
            return None

    def find_keyword_category(message_text):
        """Найти ключевое слово и вернуть его категорию"""
        message_lower = message_text.lower()
        for category, config in keywords_config.items():
            for keyword in config['keywords']:
                if keyword in message_lower:
                    return category, keyword
        return None, None

    @client.on(events.CallbackQuery())
    async def callback_handler(event):
        """Обработчик нажатий на кнопки"""
        try:
            data = event.data.decode()

            if data.startswith('blacklist_'):
                user_id = int(data.split('_')[1])
                blacklist_users.add(user_id)
                save_blacklist()

                await event.answer(f"✅ Пользователь {user_id} добавлен в ЧС", alert=True)

                await event.edit(
                    f"🚫 <b>ПОЛЬЗОВАТЕЛЬ В ЧЁРНОМ СПИСКЕ</b>\n"
                    f"ID: <code>{user_id}</code>\n"
                    f"Добавлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                    parse_mode='html',
                    buttons=None
                )
                print(f"🚫 Пользователь {user_id} добавлен в ЧС")

            elif data.startswith('invalid_'):
                user_id = int(data.split('_')[1])
                invalid_users.add(user_id)
                save_blacklist()

                await event.answer(f"❌ Пользователь {user_id} отмечен как неактуален", alert=True)

                await event.edit(
                    f"❌ <b>ПОЛЬЗОВАТЕЛЬ НЕАКТУАЛЕН</b>\n"
                    f"ID: <code>{user_id}</code>\n"
                    f"Отмечено: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                    parse_mode='html',
                    buttons=None
                )
                print(f"❌ Пользователь {user_id} отмечен как неактуален")

        except Exception as e:
            print(f"❌ Ошибка обработки кнопки: {e}")

    @client.on(events.NewMessage(incoming=True))
    async def handler(event):
        """Обработчик новых сообщений из всех источников"""
        try:
            message_text = (event.message.text or '')
            if not message_text:
                return

            chat_id = event.chat_id
            message_id = event.message.id
            unique_key = f"{chat_id}_{message_id}"

            if unique_key in notified_messages:
                return

            # Ищем ключевое слово и его категорию
            category, found_keyword = find_keyword_category(message_text)
            if not category:
                return

            print(f"🔍 Найдено ключевое слово '{found_keyword}' в категории '{category}'")

            try:
                # Получаем информацию об отправителе
                sender = await event.get_sender()
                if not sender:
                    print("⚠️  Не удалось получить информацию об отправителе")
                    return

                sender_name = sender.first_name or 'Пользователь'
                if hasattr(sender, 'last_name') and sender.last_name:
                    sender_name += ' ' + sender.last_name
                username = f"@{sender.username}" if hasattr(sender, 'username') and sender.username else "нет username"
                sender_id = sender.id

                # Проверяем чёрный список
                if sender_id in blacklist_users:
                    print(f"⛔ Пользователь {sender_name} в ЧС - игнорируем")
                    return

                # Получаем информацию о чате
                chat = await get_chat_info(chat_id)

                if chat is None:
                    chat_title = f'Чат {chat_id}'
                    chat_type = 'Неизвестный тип'
                elif isinstance(chat, User):
                    chat_title = chat.first_name or 'Приватный чат'
                    chat_type = 'Личное сообщение'
                elif isinstance(chat, Channel):
                    chat_title = chat.title or 'Канал'
                    chat_type = 'Канал' if chat.megagroup is False else 'Супергруппа'
                elif isinstance(chat, Chat):
                    chat_title = chat.title or 'Группа'
                    chat_type = 'Группа'
                else:
                    chat_title = getattr(chat, 'title', None) or getattr(chat, 'name', None) or f'Чат {chat_id}'
                    chat_type = 'Чат'

                # Формируем ссылку на сообщение
                if event.is_private:
                    if hasattr(sender, 'username') and sender.username:
                        message_link = f"https://t.me/{sender.username}/{message_id}"
                    else:
                        message_link = f"https://t.me/c/{abs(chat_id)}/{message_id}"
                else:
                    if isinstance(chat, Channel):
                        if hasattr(chat, 'username') and chat.username:
                            message_link = f"https://t.me/{chat.username}/{message_id}"
                        else:
                            message_link = f"https://t.me/c/{abs(chat_id)}/{message_id}"
                    else:
                        message_link = f"https://t.me/c/{abs(chat_id)}/{message_id}"

                # Получаем данные категории
                category_data = keywords_config[category]
                target_admin_id = category_data['admin_id']

                # Проверяем VIP статус
                is_vip = is_vip_message(message_text)
                vip_indicator = "⭐ <b>VIP!</b>\n" if is_vip else ""

                # Формируем уведомление
                notification = f"""🔔 <b>НАЙДЕН НОВЫЙ КЛИЕНТ!</b>

{vip_indicator}{category_data['emoji']} <b>КАТЕГОРИЯ:</b> {category_data['name']}

👤 <b>Клиент:</b> {sender_name}
🆔 <b>ID клиента:</b> <code>{sender_id}</code>
🆔 <b>Контакт:</b> {username}
💬 <b>Канал/Чат:</b> {chat_title}
🏷️ <b>Тип:</b> {chat_type}
🎯 <b>Ключевое слово:</b> <code>{found_keyword}</code>

📝 <b>Сообщение:</b>
<code>{message_text[:300]}{"..." if len(message_text) > 300 else ""}</code>

<a href="{message_link}">👉 Открыть сообщение</a>"""

                # Формируем кнопки используя Button.url() и Button.callback()
                contact_url = f'https://t.me/{sender.username if hasattr(sender, "username") and sender.username else f"u{sender_id}"}'
                
                buttons = [
                    [Button.url('✅ Контакт', contact_url)],
                    [
                        Button.callback('🚫 Добавить в ЧС', f'blacklist_{sender_id}'),
                        Button.callback('❌ Неактуален', f'invalid_{sender_id}')
                    ]
                ]

                # Отправляем уведомление
                try:
                    target_entity = await client.get_entity(target_admin_id)
                    print(f"📤 Отправляю уведомление в {category_data['name']} (ID: {target_admin_id})...")
                    
                    await client.send_message(
                        target_entity,
                        notification,
                        parse_mode='html',
                        buttons=buttons
                    )
                    
                    notified_messages.add(unique_key)
                    status = "VIP 🌟" if is_vip else "обычный"
                    print(f"✅ Уведомление отправлено [{status}] в {category_data['name']}: {sender_name} из {chat_title}")
                    
                except Exception as send_error:
                    print(f"❌ Ошибка отправки сообщения в {category_data['name']}: {send_error}")
                    print(f"   ADMIN_ID: {target_admin_id}")
                    import traceback
                    traceback.print_exc()

            except Exception as e:
                print(f"❌ Ошибка обработки сообщения: {e}")
                import traceback
                traceback.print_exc()

        except Exception as e:
            print(f"❌ Ошибка обработчика: {e}")

    async def monitor_chats():
        """Функция для активного сканирования групп и каналов"""
        try:
            print("\n📊 Загрузка списка групп и каналов...")
            dialogs = await client.get_dialogs()

            active_chats = []
            for dialog in dialogs:
                if dialog.is_group or dialog.is_channel:
                    active_chats.append({
                        'id': dialog.id,
                        'title': dialog.title,
                        'type': 'Канал' if dialog.is_channel else 'Группа'
                    })

            print(f"✅ Найдено {len(active_chats)} групп/каналов:")
            for chat in active_chats:
                print(f"   • {chat['title']} ({chat['type']}) - ID: {chat['id']}")

            return active_chats
        except Exception as e:
            print(f"⚠️  Ошибка загрузки чатов: {e}")
            return []

    print('🔐 Подключение к Telegram...\n')

    try:
        await client.start(phone=phone_number, password=password)
        print('✅ Успешно подключено к Telegram!\n')

        # Проверяем целевые группы
        print(f'📬 Конфигурация групп уведомлений:')
        for category, config in keywords_config.items():
            try:
                target_group = await client.get_entity(config['admin_id'])
                group_title = target_group.title if hasattr(target_group, 'title') else str(config['admin_id'])
                print(f"   {config['emoji']} {config['name']}: {group_title} (ID: {config['admin_id']})")
            except Exception as e:
                print(f"   ⚠️  {config['name']}: Ошибка проверки группы - {e}")

        active_chats = await monitor_chats()

        print(f'\n🔍 Конфигурация ключевых слов:')
        for category, config in keywords_config.items():
            keywords_list = ', '.join(config['keywords'][:3])
            extra = f"... (+{len(config['keywords']) - 3} еще)" if len(config['keywords']) > 3 else ""
            print(f"   {config['emoji']} {config['name']}: {keywords_list}{extra}")

        if vip_keywords:
            print(f'\n⭐ VIP ключевые слова ({len(vip_keywords)}): {", ".join(vip_keywords)}')
        print(f'🚫 Чёрный список: {len(blacklist_users)} пользователей')
        print(f'❌ Неактуальные: {len(invalid_users)} пользователей')

        print(f'\n🚀 Бот запущен и слушает сообщения из всех групп и каналов...')
        print('⏹️  Для остановки нажми Ctrl+C\n')

        await client.run_until_disconnected()

    except Exception as e:
        print(f'❌ Ошибка подключения: {e}')
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
