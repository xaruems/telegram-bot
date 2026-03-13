import asyncio
import os
from telethon import TelegramClient, events
from telethon.tl.types import User, Channel, Chat, PeerChannel, PeerChat
from dotenv import load_dotenv

load_dotenv()

api_id = int(os.getenv('API_ID'))
api_hash = os.getenv('API_HASH')
phone_number = os.getenv('PHONE_NUMBER')
password = os.getenv('PASSWORD', None)
admin_id = int(os.getenv('ADMIN_ID'))
keywords = [k.strip().lower() for k in os.getenv('KEYWORDS').split(',')]

notified_messages = set()
monitored_chats = {}  # Кеш для отслеживания чатов


async def main():
    client = TelegramClient('session', api_id, api_hash)

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

    @client.on(events.NewMessage(incoming=True))
    async def handler(event):
        """Обработчик новых сообщений из всех источников"""
        try:
            message_text = (event.message.text or '').lower()
            if not message_text:
                return

            chat_id = event.chat_id
            message_id = event.message.id
            unique_key = f"{chat_id}_{message_id}"

            # Пропускаем уже обработанные сообщения
            if unique_key in notified_messages:
                return

            # Ищем ключевое слово
            found_keyword = None
            for keyword in keywords:
                if keyword in message_text:
                    found_keyword = keyword
                    break

            if not found_keyword:
                return

            try:
                # Получаем информацию об отправителе
                sender = await event.get_sender()
                if sender:
                    sender_name = sender.first_name or 'Пользователь'
                    if hasattr(sender, 'last_name') and sender.last_name:
                        sender_name += ' ' + sender.last_name
                    username = f"@{sender.username}" if hasattr(sender,
                                                                'username') and sender.username else "нет username"
                    sender_id = sender.id
                else:
                    sender_name = 'Неизвестный пользователь'
                    username = 'нет информации'
                    sender_id = event.from_id if hasattr(event, 'from_id') else 'неизвестно'

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
                    # Для групп и каналов
                    if isinstance(chat, Channel):
                        # Для каналов используем username если есть
                        if hasattr(chat, 'username') and chat.username:
                            message_link = f"https://t.me/{chat.username}/{message_id}"
                        else:
                            message_link = f"https://t.me/c/{abs(chat_id)}/{message_id}"
                    else:
                        message_link = f"https://t.me/c/{abs(chat_id)}/{message_id}"

                # Формируем уведомление
                notification = f"""
🔔 <b>НАЙДЕН НОВЫЙ КЛИЕНТ!</b>

👤 <b>Клиент:</b> {sender_name}
🆔 <b>ID клиента:</b> <code>{sender_id}</code>
🆔 <b>Контакт:</b> {username}
💬 <b>Канал/Чат:</b> {chat_title}
🏷️ <b>Тип:</b> {chat_type}
🎯 <b>Ключевое слово:</b> <code>{found_keyword}</code>

📝 <b>Сообщение:</b>
<code>{message_text[:300]}{"..." if len(message_text) > 300 else ""}</code>

<a href="{message_link}">👉 Открыть сообщение</a>
                """

                # Отправляем уведомление
                try:
                    target_entity = await client.get_entity(admin_id)
                    await client.send_message(target_entity, notification, parse_mode='html')
                    notified_messages.add(unique_key)
                    print(f"✅ Уведомление отправлено: {sender_name} в {chat_title}")
                except Exception as send_error:
                    print(f"❌ Ошибка отправки сообщения: {send_error}")
                    print(f"   ADMIN_ID: {admin_id}")

            except Exception as e:
                print(f"❌ Ошибка обработки сообщения: {e}")

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

        # Проверяем целевую группу для уведомлений
        try:
            target_group = await client.get_entity(admin_id)
            print(f'📬 Уведомления будут отправляться в: {target_group.title}')
            print(f'   ID: {admin_id}')

            if isinstance(target_group, Channel):
                print(f'   Тип: {"Супергруппа" if target_group.megagroup else "Канал"}')
            else:
                print(f'   Тип: Группа')

        except Exception as e:
            print(f'⚠️  Ошибка проверки группы: {e}')

        # Загружаем список доступных чатов
        active_chats = await monitor_chats()

        print(f'\n🚀 Бот запущен и слушает сообщения из всех групп и каналов...')
        print(f'🔍 Поиск ключевых слов: {", ".join(keywords)}')
        print('⏹️  Для остановки нажми Ctrl+C\n')

        await client.run_until_disconnected()

    except Exception as e:
        print(f'❌ Ошибка подключения: {e}')


if __name__ == '__main__':
    asyncio.run(main())