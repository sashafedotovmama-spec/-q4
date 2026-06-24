import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Токен бота (замените на свой)
BOT_TOKEN = "8908126962:AAEHJySFXe289oH3SXuYXdRgeaqEgvg7LWM"

# Время на принятие правил (в секундах) - 24 часа
TIME_TO_ACCEPT = 86400  # 24 часа = 24 * 60 * 60

# Текст правил
RULES_TEXT = """
📜 *ПРАВИЛА ЧАТА*

1. Будьте вежливы и уважайте других участников
2. Запрещён спам, реклама и провокации
3. Не используйте нецензурную лексику
4. Обсуждайте только темы, соответствующие тематике чата
5. Запрещена публикация личной информации без согласия

⚠️ Нарушение правил влечёт за собой предупреждение или блокировку.

Нажимая кнопку "Согласен", вы подтверждаете, что ознакомились с правилами и обязуетесь их соблюдать.
"""

# Словарь для отслеживания статуса пользователей
user_agreements = {}
# Словарь для хранения задач на кик
kick_tasks = {}

# Функция для форматирования времени
def format_time(seconds: int) -> str:
    """Преобразует секунды в читаемый формат"""
    if seconds >= 86400:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        if hours > 0:
            return f"{days} день {hours} часов"
        return f"{days} дней"
    elif seconds >= 3600:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if minutes > 0:
            return f"{hours} часов {minutes} минут"
        return f"{hours} часов"
    elif seconds >= 60:
        minutes = seconds // 60
        return f"{minutes} минут"
    else:
        return f"{seconds} секунд"

# Функция для кика пользователя
async def kick_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, reason: str = "Нарушение правил"):
    """Универсальная функция для кика пользователя"""
    try:
        # Пытаемся забанить пользователя
        await context.bot.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id
        )
        logging.info(f"✅ Пользователь {user_id} забанен в чате {chat_id}")
        
        # Разбаниваем, чтобы пользователь мог зайти позже (эффект "кика")
        await context.bot.unban_chat_member(
            chat_id=chat_id,
            user_id=user_id
        )
        logging.info(f"✅ Пользователь {user_id} разбанен (кик выполнен)")
        
        return True
    except Exception as e:
        logging.error(f"❌ Ошибка при кике пользователя {user_id}: {e}")
        return False

# Функция для автоматического кика через 24 часа
async def auto_kick_after_delay(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, message_id: int):
    """Автоматически кикает пользователя через 24 часа, если он не согласился"""
    try:
        # Ждем 24 часа
        await asyncio.sleep(TIME_TO_ACCEPT)
        
        # Проверяем, не согласился ли пользователь за это время
        if user_id in user_agreements and not user_agreements[user_id].get('agreed', False):
            # Пользователь не согласился - кикаем
            kick_success = await kick_user(
                context=context,
                chat_id=chat_id,
                user_id=user_id,
                reason=f"Не принял правила в течение 24 часов"
            )
            
            if kick_success:
                # Отправляем уведомление в чат
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🔨 Пользователь был удалён из чата за отказ от принятия правил в течение 24 часов.",
                    parse_mode='HTML'
                )
                
                # Удаляем пользователя из словаря
                if user_id in user_agreements:
                    del user_agreements[user_id]
                
                # Удаляем задачу на кик
                if user_id in kick_tasks:
                    del kick_tasks[user_id]
                    
        # Если пользователь согласился, задача сама завершится
        elif user_id in user_agreements and user_agreements[user_id].get('agreed', False):
            logging.info(f"✅ Пользователь {user_id} согласился с правилами, кик отменён")
            
    except asyncio.CancelledError:
        logging.info(f"⏰ Таймер для пользователя {user_id} отменён (пользователь согласился)")
    except Exception as e:
        logging.error(f"Ошибка в auto_kick_after_delay: {e}")

# Обработчик новых участников
async def new_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, есть ли новые участники
    for member in update.message.new_chat_members:
        # Пропускаем, если новый участник - сам бот
        if member.id == context.bot.id:
            continue
            
        # Сохраняем в словарь, что пользователь ещё не согласился
        user_agreements[member.id] = {
            'agreed': False,
            'joined_time': update.message.date.timestamp()
        }
            
        keyboard = [
            [
                InlineKeyboardButton("✅ Согласен", callback_data=f'agree_{member.id}'),
                InlineKeyboardButton("❌ Отказаться", callback_data=f'decline_{member.id}')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем правила новому участнику
        sent_message = await update.message.reply_text(
            f"👋 Добро пожаловать, {member.first_name}!\n\n{RULES_TEXT}\n\n"
            f"⏰ У вас есть 24 часа, чтобы принять правила!\n"
            f"Если вы не примете правила в течение суток, вы будете автоматически удалены из чата.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        # Запускаем таймер на кик через 24 часа
        task = asyncio.create_task(
            auto_kick_after_delay(
                context=context,
                chat_id=update.effective_chat.id,
                user_id=member.id,
                message_id=sent_message.message_id
            )
        )
        kick_tasks[member.id] = task

# Обработчик нажатия на кнопку
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Получаем ID пользователя и действие из callback_data
    action, user_id = query.data.split('_')
    user_id = int(user_id)
    chat_id = update.effective_chat.id
    
    # Проверяем, что кнопку нажимает тот же пользователь
    if query.from_user.id != user_id:
        await query.answer("❌ Эта кнопка не для вас!", show_alert=True)
        return
    
    # Обработка согласия
    if action == 'agree':
        # Отмечаем, что пользователь согласился
        if user_id in user_agreements:
            user_agreements[user_id]['agreed'] = True
        else:
            user_agreements[user_id] = {'agreed': True, 'joined_time': query.message.date.timestamp()}
        
        # Отменяем задачу на кик, если она есть
        if user_id in kick_tasks:
            kick_tasks[user_id].cancel()
            del kick_tasks[user_id]
            logging.info(f"✅ Задача на кик отменена для пользователя {user_id}")
            
        await query.edit_message_text(
            f"✅ *Спасибо, {query.from_user.first_name}! Вы приняли правила.*\n\n"
            f"Теперь вы можете общаться в чате.\n"
            f"Добро пожаловать! 🎉",
            parse_mode='Markdown'
        )
        
        # Отправляем приветствие в чат
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"👋 Приветствуем нового участника: {query.from_user.mention_html()}!\n"
                 f"Он принял правила и готов к общению!",
            parse_mode='HTML'
        )
    
    # Обработка отказа - КИКАЕМ ПОЛЬЗОВАТЕЛЯ!
    elif action == 'decline':
        # Отмечаем, что пользователь отказался
        if user_id in user_agreements:
            user_agreements[user_id]['agreed'] = False
        else:
            user_agreements[user_id] = {'agreed': False, 'joined_time': query.message.date.timestamp()}
        
        # Отменяем задачу на кик, если она есть
        if user_id in kick_tasks:
            kick_tasks[user_id].cancel()
            del kick_tasks[user_id]
        
        # Сначала показываем сообщение об отказе
        await query.edit_message_text(
            f"❌ *{query.from_user.first_name}, вы отказались от принятия правил.*\n\n"
            f"К сожалению, без принятия правил вы не можете участвовать в чате.\n"
            f"Вы будете удалены из чата.",
            parse_mode='Markdown'
        )
        
        # Пытаемся кикнуть пользователя
        kick_success = await kick_user(
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            reason="Отказ от правил"
        )
        
        if kick_success:
            # Отправляем уведомление в чат
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔨 Пользователь {query.from_user.mention_html()} был удалён из чата за отказ от правил.",
                parse_mode='HTML'
            )
            
            # Удаляем пользователя из словаря
            if user_id in user_agreements:
                del user_agreements[user_id]

# Обработчик сообщений (проверка, принял ли пользователь правила)
async def check_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет, принял ли пользователь правила перед отправкой сообщения"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Проверяем только сообщения в группах
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    
    # Пропускаем сообщения от ботов
    if update.effective_user.is_bot:
        return
    
    # Проверяем, есть ли пользователь в словаре
    if user_id in user_agreements:
        # Если пользователь НЕ согласился с правилами
        if not user_agreements[user_id].get('agreed', False):
            # Удаляем сообщение
            try:
                await update.message.delete()
                logging.info(f"🗑️ Сообщение от {user_id} удалено (не принял правила)")
            except Exception as e:
                logging.error(f"Ошибка при удалении сообщения: {e}")
            
            # Отправляем предупреждение в чат
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ {update.effective_user.mention_html()}, вы не можете писать в чат, пока не примете правила!\n"
                     f"У вас есть 24 часа, чтобы нажать кнопку \"✅ Согласен\".\n"
                     f"В противном случае вы будете автоматически удалены.",
                parse_mode='HTML'
            )
            
            return
    
    # Если пользователя нет в словаре - возможно, он присоединился до бота
    else:
        user_agreements[user_id] = {
            'agreed': False,
            'joined_time': update.message.date.timestamp()
        }
        
        # Удаляем сообщение
        try:
            await update.message.delete()
        except:
            pass
        
        # Отправляем правила
        keyboard = [
            [
                InlineKeyboardButton("✅ Согласен", callback_data=f'agree_{user_id}'),
                InlineKeyboardButton("❌ Отказаться", callback_data=f'decline_{user_id}')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        sent_message = await context.bot.send_message(
            chat_id=chat_id,
            text=f"👋 {update.effective_user.mention_html()}, вы не приняли правила чата!\n\n{RULES_TEXT}\n\n"
                 f"⏰ У вас есть 24 часа, чтобы принять правила!\n"
                 f"Если вы не примете правила в течение суток, вы будете автоматически удалены из чата.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        # Запускаем таймер на кик через 24 часа
        task = asyncio.create_task(
            auto_kick_after_delay(
                context=context,
                chat_id=chat_id,
                user_id=user_id,
                message_id=sent_message.message_id
            )
        )
        kick_tasks[user_id] = task

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Получаем username бота
    bot_username = context.bot.username
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить в группу", url=f"https://t.me/{bot_username}?startgroup=start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🤖 *Привет! Я бот для управления правилами группы.*\n\n"
        "📌 *Мои функции:*\n"
        "• Приветствую новых участников\n"
        "• Показываю правила чата\n"
        "• Запрашиваю согласие с правилами\n"
        "• ⏰ Кикаю через 24 часа, если не принял правила\n"
        "• 🔨 Удаляю тех, кто отказался\n"
        "• 🛡️ Блокирую сообщения от тех, кто не принял правила\n\n"
        "🔧 *Как использовать:*\n"
        "1. Добавьте меня в группу\n"
        "2. Сделайте меня администратором с правами:\n"
        "   ✅ Отправка сообщений\n"
        "   ✅ Удаление сообщений\n"
        "   ✅ Блокировка пользователей\n"
        "3. Готово! Я буду автоматически работать\n\n"
        "👑 *Команды для админов:*\n"
        "/rules - показать правила\n"
        "/stats - статистика согласий\n"
        "/check - проверить статус всех пользователей\n"
        "/kick_waiting - кикнуть всех, кто не принял правила",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# Команда для проверки статуса пользователей
async def check_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет статус всех пользователей в чате"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Проверяем права админа
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ['creator', 'administrator']:
            await update.message.reply_text("❌ Эта команда только для администраторов!")
            return
    except:
        await update.message.reply_text("❌ Ошибка проверки прав!")
        return
    
    if not user_agreements:
        await update.message.reply_text("📊 Все пользователи согласились с правилами!")
        return
    
    text = "📊 *Статус пользователей:*\n\n"
    for uid, data in user_agreements.items():
        try:
            user = await context.bot.get_chat(uid)
            name = user.full_name or user.username or str(uid)
            status = "✅ Согласился" if data.get('agreed', False) else "❌ Не согласился (будет кикнут через 24 часа)"
            text += f"• {name} — {status}\n"
        except:
            text += f"• ID {uid} — {data.get('agreed', False)}\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

# Команда для принудительного кика всех, кто не принял правила
async def kick_waiting_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кикает всех пользователей, которые не приняли правила"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Проверяем права админа
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ['creator', 'administrator']:
            await update.message.reply_text("❌ Эта команда только для администраторов!")
            return
    except:
        await update.message.reply_text("❌ Ошибка проверки прав!")
        return
    
    # Находим всех, кто не согласился
    waiting_users = [uid for uid, data in user_agreements.items() if not data.get('agreed', False)]
    
    if not waiting_users:
        await update.message.reply_text("✅ Нет пользователей, ожидающих принятия правил.")
        return
    
    await update.message.reply_text(f"⏳ Начинаю кик {len(waiting_users)} пользователей...")
    
    kicked = 0
    for uid in waiting_users:
        success = await kick_user(
            context=context,
            chat_id=chat_id,
            user_id=uid,
            reason="Принудительный кик админом (не принял правила)"
        )
        if success:
            kicked += 1
            if uid in user_agreements:
                del user_agreements[uid]
            if uid in kick_tasks:
                kick_tasks[uid].cancel()
                del kick_tasks[uid]
    
    await update.message.reply_text(
        f"✅ Кикнуто {kicked} из {len(waiting_users)} пользователей, не принявших правила."
    )

# Команда для показа правил
async def show_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, что команду вызвал админ
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ['creator', 'administrator']:
            await update.message.reply_text("❌ Эта команда только для администраторов!")
            return
    except:
        await update.message.reply_text("❌ Ошибка проверки прав!")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Согласен", callback_data=f'agree_{user_id}'),
            InlineKeyboardButton("❌ Отказаться", callback_data=f'decline_{user_id}')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📜 *Правила чата*\n\n{RULES_TEXT}",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# Команда для просмотра статистики
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, что команду вызвал админ
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ['creator', 'administrator']:
            await update.message.reply_text("❌ Эта команда только для администраторов!")
            return
    except:
        await update.message.reply_text("❌ Ошибка проверки прав!")
        return
    
    # Считаем статистику
    total = len(user_agreements)
    agreed = sum(1 for v in user_agreements.values() if v.get('agreed', False))
    declined = total - agreed
    
    stats_text = (
        f"📊 *Статистика принятия правил*\n\n"
        f"👥 Всего участников на рассмотрении: {total}\n"
        f"✅ Согласились: {agreed}\n"
        f"❌ Не согласились (будут кикнуты через 24 часа): {declined}\n\n"
        f"⏰ Время на принятие правил: 24 часа"
    )
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')

# Основная функция
def main():
    # Создаём приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("rules", show_rules))
    application.add_handler(CommandHandler("stats", show_stats))
    application.add_handler(CommandHandler("check", check_users))
    application.add_handler(CommandHandler("kick_waiting", kick_waiting_users))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member_handler))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_message_handler))

    print("🤖 Бот запущен и готов к работе в группах...")
    print("📌 Не забудьте:")
    print("  1. Добавить бота в группу")
    print("  2. Сделать бота администратором")
    print("  3. Включить права на:")
    print("     ✅ Отправка сообщений")
    print("     ✅ Удаление сообщений")
    print("     ✅ Блокировка пользователей (ЭТО ВАЖНО ДЛЯ КИКА!)")
    print("\n⏰ Бот будет кикать через 24 часа, если пользователь не принял правила!")
    print("👑 Команды админа:")
    print("  /check - проверить статус пользователей")
    print("  /kick_waiting - кикнуть всех, кто не принял правила")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
