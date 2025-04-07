import logging
import urllib.parse
import os
import openai
import random
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackQueryHandler,
    ConversationHandler,
    CallbackContext,
)
from db import check_user, get_questions, get_prompt, create_tables

# Загружаем переменные окружения
load_dotenv()

# Получаем токен из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Определяем состояния диалога
START_MENU, QUESTION, CONFIRM_REVIEW, EDIT_REVIEW_STATE, HUMANIZE_PROCESSING, DEMOGRAPHIC_CHOICE = range(6)

# Настройка OpenAI API
openai.api_key = OPENAI_API_KEY

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Словарь профилей для персонализации
demographic_profiles = {
    "young_male": {
        "name": "молодого человека (18-30 лет)",
        "style": "современный, энергичный, использует молодежный сленг и короткие предложения",
        "characteristics": "ценит скорость, технологичность, прямолинейность, не любит ждать"
    },
    "young_female": {
        "name": "молодой женщины (18-30 лет)",
        "style": "эмоциональный, использует эмодзи, позитивный, детальный",
        "characteristics": "внимательна к деталям, ценит атмосферу и отношение персонала"
    },
    "middle_male": {
        "name": "мужчины средних лет",
        "style": "сдержанный, конкретный, деловой, оценивает соотношение цена/качество",
        "characteristics": "ценит профессионализм, четкость, пунктуальность, результат"
    },
    "woman_children": {
        "name": "женщины с детьми",
        "style": "заботливый, ориентированный на безопасность и комфорт, упоминает детей",
        "characteristics": "важны безопасность, внимание к детям, терпеливость персонала, удобство"
    },
    "elderly": {
        "name": "пожилого человека",
        "style": "вежливый, традиционный, размеренный, возможно с советскими речевыми оборотами",
        "characteristics": "ценит внимание, уважение, понятные объяснения, не торопливое обслуживание"
    },
    "random": {
        "name": "случайного клиента",
        "style": "естественный и повседневный",
        "characteristics": "обычный клиент со своими впечатлениями"
    }
}

# --- Функция стартового меню ---
def start(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    
    # Проверяем авторизацию пользователя
    business_type = check_user(user_id)
    
    if not business_type:
        if update.message:
            update.message.reply_text("Вы не авторизованы. Обратитесь к администратору.")
        else:
            update.callback_query.message.reply_text("Вы не авторизованы. Обратитесь к администратору.")
        return ConversationHandler.END
    
    # Сохраняем данные в контексте
    context.user_data["business_type"] = business_type
    context.user_data["questions"] = get_questions(business_type)
    
    if not context.user_data["questions"]:
        if update.message:
            update.message.reply_text(f"Ошибка: вопросы для типа бизнеса '{business_type}' не найдены.")
        else:
            update.callback_query.message.reply_text(f"Ошибка: вопросы для типа бизнеса '{business_type}' не найдены.")
        return ConversationHandler.END
    
    # Формируем клавиатуру стартового меню
    keyboard = [
        [InlineKeyboardButton("✅ Начать анкетирование", callback_data="start_survey")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "📌 Выберите действие:"
    
    if update.message:
        update.message.reply_text(message_text, reply_markup=reply_markup)
    else:
        update.callback_query.message.reply_text(message_text, reply_markup=reply_markup)
    
    return START_MENU

# --- Обработчик стартового меню ---
def start_menu_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    
    if query.data == "start_survey":
        context.user_data["current_question"] = 0
        context.user_data["answers"] = []
        questions = context.user_data.get("questions", [])
        if not questions:
            query.edit_message_text(text="Ошибка: вопросы не найдены.")
            return ConversationHandler.END
        
        question_text = f"📝 Вопрос 1/{len(questions)}:\n{questions[0]}"
        query.edit_message_text(text=question_text)
        return QUESTION
    
    elif query.data == "cancel":
        query.edit_message_text(text="Анкетирование отменено.")
        return ConversationHandler.END

# --- Обработчик ответов на вопросы ---
def answer_handler(update: Update, context: CallbackContext) -> int:
    current_q = context.user_data.get("current_question", 0)
    answer = update.message.text
    answers = context.user_data.get("answers", [])
    
    if len(answers) > current_q:
        answers[current_q] = answer
    else:
        answers.append(answer)
    
    context.user_data["answers"] = answers

    # Клавиатура с кнопками, включая "Обратно в меню"
    keyboard = [
        [
            InlineKeyboardButton("🔄 Изменить ответ", callback_data="edit_answer"),
            InlineKeyboardButton("⏭ Далее", callback_data="next_question"),
        ],
        [InlineKeyboardButton("🏠 Обратно в меню", callback_data="back_to_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(f"Ответ: \"{answer}\"\nВыберите действие:", reply_markup=reply_markup)
    return QUESTION

# --- Обработчик callback-запросов на этапе вопросов ---
def question_callback_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    
    current_q = context.user_data.get("current_question", 0)
    questions = context.user_data.get("questions", [])
    
    if query.data == "edit_answer":
        query.edit_message_text(
            text=f"📝 Вопрос {current_q+1}/{len(questions)}:\n{questions[current_q]}\nВведите новый ответ:"
        )
        return QUESTION
    
    elif query.data == "next_question":
        current_q += 1
        context.user_data["current_question"] = current_q
        
        if current_q < len(questions):
            question_text = f"📝 Вопрос {current_q+1}/{len(questions)}:\n{questions[current_q]}"
            query.edit_message_text(text=question_text)
            return QUESTION
        else:
            # Генерация отзыва
            answers = context.user_data.get("answers", [])
            business_type = context.user_data.get("business_type")
            prompt_template = get_prompt(business_type)
            answers_text = "\n".join(f"{i+1}. {ans}" for i, ans in enumerate(answers))
            prompt = prompt_template.format(answers_text)
            
            query.edit_message_text(text="Формирую отзыв, подождите...")
            
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Ты помогаешь составить отзыв для клиники."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                    max_tokens=200,
                )
                generated_review = response.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"Ошибка OpenAI API: {e}")
                query.edit_message_text(text="Ошибка при генерации отзыва.")
                return ConversationHandler.END

            context.user_data["generated_review"] = generated_review
            context.user_data["original_review"] = generated_review
            
            keyboard = [
                [
                    InlineKeyboardButton("✏️ Отредактировать отзыв", callback_data="edit_review"),
                    InlineKeyboardButton("👤 Персонализировать", callback_data="personalize_review"),
                    InlineKeyboardButton("✅ Отправить в WhatsApp", callback_data="send_whatsapp"),
                ],
                [InlineKeyboardButton("🔄 Начать заново", callback_data="restart")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.edit_message_text(
                text=f"🎉 Отзыв сформирован:\n\"{generated_review}\"", reply_markup=reply_markup
            )
            return CONFIRM_REVIEW
    
    elif query.data == "back_to_menu":
        # Сброс данных и возврат в меню
        context.user_data.clear()
        context.user_data["business_type"] = check_user(update.effective_user.id)
        context.user_data["questions"] = get_questions(context.user_data["business_type"])
        
        keyboard = [
            [InlineKeyboardButton("✅ Начать анкетирование", callback_data="start_survey")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text="📌 Выберите действие:", reply_markup=reply_markup)
        return START_MENU

# --- Обработчик подтверждения отзыва ---
def review_callback_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    
    if query.data == "edit_review":
        keyboard = [[InlineKeyboardButton("Назад", callback_data="cancel_edit")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(
            text="Введите отредактированный отзыв или нажмите 'Назад':",
            reply_markup=reply_markup,
        )
        return EDIT_REVIEW_STATE
    
    elif query.data == "send_whatsapp":
        review = context.user_data.get("generated_review", "")
        encoded_text = urllib.parse.quote(review)
        whatsapp_url = f"https://api.whatsapp.com/send?text={encoded_text}"
        
        keyboard = [
            [InlineKeyboardButton("Открыть WhatsApp", url=whatsapp_url)],
            [
                InlineKeyboardButton("Назад", callback_data="back_from_whatsapp"),
                InlineKeyboardButton("Отредактировать отзыв", callback_data="edit_review"),
                InlineKeyboardButton("🔄 Начать заново", callback_data="restart"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(
            text="Отправьте отзыв через WhatsApp:", reply_markup=reply_markup
        )
        return CONFIRM_REVIEW
    
    elif query.data == "back_from_whatsapp":
        generated_review = context.user_data.get("generated_review", "")
        keyboard = [
            [
                InlineKeyboardButton("✏️ Отредактировать отзыв", callback_data="edit_review"),
                InlineKeyboardButton("👤 Персонализировать", callback_data="personalize_review"),
                InlineKeyboardButton("✅ Отправить в WhatsApp", callback_data="send_whatsapp"),
            ],
            [InlineKeyboardButton("🔄 Начать заново", callback_data="restart")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(
            text=f"🎉 Отзыв сформирован:\n\"{generated_review}\"", reply_markup=reply_markup
        )
        return CONFIRM_REVIEW
    
    elif query.data == "restart":
        business_type = context.user_data.get("business_type")
        questions = context.user_data.get("questions", [])
        context.user_data.clear()
        context.user_data["business_type"] = business_type
        context.user_data["questions"] = questions
        
        keyboard = [
            [InlineKeyboardButton("✅ Начать анкетирование", callback_data="start_survey")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text="📌 Выберите действие:", reply_markup=reply_markup)
        return START_MENU

# --- Обработчик выбора демографии ---
def personalize_review_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    
    # Сохраняем текущий отзыв
    review = context.user_data.get("generated_review", "")
    context.user_data["original_review"] = review
    
    # Создаем клавиатуру с демографическими опциями
    keyboard = [
        [
            InlineKeyboardButton("👨 Молодой человек (18-30)", callback_data="demo_young_male"),
            InlineKeyboardButton("👩 Молодая женщина (18-30)", callback_data="demo_young_female"),
        ],
        [
            InlineKeyboardButton("👨‍💼 Мужчина средних лет", callback_data="demo_middle_male"),
            InlineKeyboardButton("👩‍👧 Женщина с детьми", callback_data="demo_woman_children"),
        ],
        [
            InlineKeyboardButton("👴 Пожилой человек", callback_data="demo_elderly"),
            InlineKeyboardButton("🎲 Случайный", callback_data="demo_random"),
        ],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_review")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        text=f"👤 Выберите тип клиента для персонализации отзыва:\n\n"
             f"Текущий отзыв:\n\"{review}\"",
        reply_markup=reply_markup
    )
    return DEMOGRAPHIC_CHOICE

# --- Обработчик возврата к экрану отзыва ---
def back_to_review_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    
    review = context.user_data.get("generated_review", "")
    
    keyboard = [
        [
            InlineKeyboardButton("✏️ Отредактировать отзыв", callback_data="edit_review"),
            InlineKeyboardButton("👤 Персонализировать", callback_data="personalize_review"),
            InlineKeyboardButton("✅ Отправить в WhatsApp", callback_data="send_whatsapp"),
        ],
        [InlineKeyboardButton("🔄 Начать заново", callback_data="restart")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        text=f"🎉 Отзыв сформирован:\n\"{review}\"",
        reply_markup=reply_markup
    )
    return CONFIRM_REVIEW

# --- Обработчик восстановления исходного отзыва ---
def restore_original_review_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    
    # Получаем исходный отзыв
    original_review = context.user_data.get("original_review", "")
    
    # Восстанавливаем исходный отзыв
    context.user_data["generated_review"] = original_review
    
    # Создаем клавиатуру с кнопкой персонализации
    keyboard = [
        [
            InlineKeyboardButton("✏️ Отредактировать отзыв", callback_data="edit_review"),
            InlineKeyboardButton("👤 Персонализировать", callback_data="personalize_review"),
            InlineKeyboardButton("✅ Отправить в WhatsApp", callback_data="send_whatsapp"),
        ],
        [InlineKeyboardButton("🔄 Начать заново", callback_data="restart")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        text=f"🔄 Восстановлен исходный отзыв:\n\n\"{original_review}\"",
        reply_markup=reply_markup
    )
    return CONFIRM_REVIEW

# --- Обработчик выбора демографии ---
def demographic_choice_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    
    demographic_type = query.data.replace("demo_", "")
    review = context.user_data.get("original_review", "")
    
    query.edit_message_text(text="Персонализирую отзыв, подождите...")
    
    if demographic_type == "random":
        # Выбираем случайный профиль, кроме "random"
        demographic_type = random.choice([k for k in demographic_profiles.keys() if k != "random"])
    
    profile = demographic_profiles.get(demographic_type)
    
    # Промпт для персонализации отзыва
    personalize_prompt = f"""
    Перепиши этот отзыв так, чтобы он звучал как отзыв от {profile["name"]}.
    
    Стиль написания: {profile["style"]}
    Клиент ценит: {profile["characteristics"]}
    
    Правила:
    1. Отзыв должен быть ОЧЕНЬ коротким (2-4 предложения максимум)
    2. Используй речевые обороты, характерные для данной демографической группы
    3. Избегай слишком формального языка
    4. Сохрани основные положительные моменты из исходного отзыва
    5. Добавь 1-2 специфических детали, характерных для этой группы клиентов
    
    Вот исходный отзыв:
    "{review}"
    
    Создай короткую, персонализированную версию отзыва.
    """
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": f"Ты эксперт по созданию реалистичных отзывов от лица разных типов клиентов."},
                {"role": "user", "content": personalize_prompt},
            ],
            temperature=0.85,
            max_tokens=200,
        )
        personalized_review = response.choices[0].message.content.strip()
        context.user_data["generated_review"] = personalized_review
        
        # Клавиатура с кнопкой восстановления исходного отзыва
        keyboard = [
            [
                InlineKeyboardButton("✏️ Отредактировать отзыв", callback_data="edit_review"),
                InlineKeyboardButton("✅ Отправить в WhatsApp", callback_data="send_whatsapp"),
            ],
            [
                InlineKeyboardButton("🔙 Восстановить исходный", callback_data="restore_original"),
                InlineKeyboardButton("🔄 Начать заново", callback_data="restart"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        profile_name = demographic_profiles.get(demographic_type)["name"]
        query.edit_message_text(
            text=f"🎭 Отзыв персонализирован (стиль {profile_name}):\n\n\"{personalized_review}\"",
            reply_markup=reply_markup
        )
        return CONFIRM_REVIEW
    except Exception as e:
        logger.error(f"Ошибка OpenAI API при персонализации: {e}")
        
        # В случае ошибки возвращаем к выбору демографии
        keyboard = [
            [
                InlineKeyboardButton("👨 Молодой человек (18-30)", callback_data="demo_young_male"),
                InlineKeyboardButton("👩 Молодая женщина (18-30)", callback_data="demo_young_female"),
            ],
            [
                InlineKeyboardButton("👨‍💼 Мужчина средних лет", callback_data="demo_middle_male"),
                InlineKeyboardButton("👩‍👧 Женщина с детьми", callback_data="demo_woman_children"),
            ],
            [
                InlineKeyboardButton("👴 Пожилой человек", callback_data="demo_elderly"),
                InlineKeyboardButton("🎲 Случайный", callback_data="demo_random"),
            ],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_to_review")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            text=f"❌ Ошибка при персонализации отзыва. Попробуйте еще раз.\n\n"
                 f"Текущий отзыв:\n\"{review}\"",
            reply_markup=reply_markup
        )
        return DEMOGRAPHIC_CHOICE

# --- Обработчик очеловечивания отзыва ---
def humanize_review_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    
    review = context.user_data.get("generated_review", "")
    
    query.edit_message_text(text="Очеловечиваю отзыв, подождите...")
    
    # Обновленный промпт для "очеловечивания" отзыва
    humanize_prompt = """
    Ты эксперт по созданию коротких, естественных отзывов клиентов. 
    Твоя задача — переписать предоставленный отзыв так, чтобы он был:
    1. Очень лаконичным (максимум 2-4 коротких предложения)
    2. Звучал как настоящий отзыв довольного пациента

    Используй:
    - разговорную речь и простые конструкции предложений
    - 1-2 эмоциональных выражения (благодарность, радость)
    - конкретную, но краткую похвалу
    - уместные разговорные фразы

    Избегай:
    - длинных, сложных предложений
    - перечислений множества деталей
    - излишне восторженных прилагательных
    - повторений
    - слишком формального языка

    ОЧЕНЬ ВАЖНО: отзыв должен быть коротким (2-4 предложения), так как реальные пациенты не пишут длинные отзывы.

    Вот отзыв, который нужно сделать коротким и человечным:
    "{review}"

    Создай новую, более короткую и естественную версию этого отзыва.
    """
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты помогаешь сделать отзыв клиента более коротким, естественным и человечным."},
                {"role": "user", "content": humanize_prompt.format(review=review)},
            ],
            temperature=0.8,
            max_tokens=200,
        )
        humanized_review = response.choices[0].message.content.strip()
        context.user_data["generated_review"] = humanized_review
        
        # Клавиатура без кнопки "Очеловечить"
        keyboard = [
            [
                InlineKeyboardButton("✏️ Отредактировать отзыв", callback_data="edit_review"),
                InlineKeyboardButton("✅ Отправить в WhatsApp", callback_data="send_whatsapp"),
            ],
            [InlineKeyboardButton("🔄 Начать заново", callback_data="restart")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(
            text=f"🎉 Отзыв очеловечен:\n\"{humanized_review}\"", reply_markup=reply_markup
        )
        return CONFIRM_REVIEW
    except Exception as e:
        logger.error(f"Ошибка OpenAI API при очеловечивании: {e}")
        
        # В случае ошибки возвращаем исходную клавиатуру
        keyboard = [
            [
                InlineKeyboardButton("✏️ Отредактировать отзыв", callback_data="edit_review"),
                InlineKeyboardButton("👤 Персонализировать", callback_data="personalize_review"),
                InlineKeyboardButton("✅ Отправить в WhatsApp", callback_data="send_whatsapp"),
            ],
            [InlineKeyboardButton("🔄 Начать заново", callback_data="restart")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(
            text=f"❌ Ошибка при очеловечивании отзыва. Попробуйте еще раз.\n\nВаш отзыв:\n\"{review}\"",
            reply_markup=reply_markup
        )
        return CONFIRM_REVIEW

# --- Обработчик редактирования отзыва ---
def edit_review_handler(update: Update, context: CallbackContext) -> int:
    edited_review = update.message.text
    context.user_data["generated_review"] = edited_review
    
    keyboard = [
        [
            InlineKeyboardButton("✏️ Отредактировать отзыв", callback_data="edit_review"),
            InlineKeyboardButton("👤 Персонализировать", callback_data="personalize_review"),
            InlineKeyboardButton("✅ Отправить в WhatsApp", callback_data="send_whatsapp"),
        ],
        [InlineKeyboardButton("🔄 Начать заново", callback_data="restart")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        f"Ваш отредактированный отзыв:\n\"{edited_review}\"\nВыберите действие:", reply_markup=reply_markup
    )
    return CONFIRM_REVIEW

def cancel_edit_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    
    generated_review = context.user_data.get("generated_review", "")
    keyboard = [
        [
            InlineKeyboardButton("✏️ Отредактировать отзыв", callback_data="edit_review"),
            InlineKeyboardButton("👤 Персонализировать", callback_data="personalize_review"),
            InlineKeyboardButton("✅ Отправить в WhatsApp", callback_data="send_whatsapp"),
        ],
        [InlineKeyboardButton("🔄 Начать заново", callback_data="restart")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(
        text=f"Отзыв сохранён:\n\"{generated_review}\"", reply_markup=reply_markup
    )
    return CONFIRM_REVIEW

# --- Отмена диалога ---
def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Диалог отменен.")
    return ConversationHandler.END

# --- Главная функция ---
def main():
    create_tables()
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            START_MENU: [CallbackQueryHandler(start_menu_handler, pattern="^(start_survey|cancel)$")],
            QUESTION: [
                MessageHandler(Filters.text & ~Filters.command, answer_handler),
                CallbackQueryHandler(question_callback_handler, pattern="^(edit_answer|next_question|back_to_menu)$"),
            ],
            CONFIRM_REVIEW: [
                CallbackQueryHandler(
                    review_callback_handler, 
                    pattern="^(edit_review|send_whatsapp|back_from_whatsapp|restart)$"
                ),
                CallbackQueryHandler(
                    personalize_review_handler, 
                    pattern="^personalize_review$"
                ),
                CallbackQueryHandler(
                    humanize_review_handler, 
                    pattern="^humanize_review$"
                ),
                CallbackQueryHandler(
                    restore_original_review_handler, 
                    pattern="^restore_original$"
                ),
            ],
            EDIT_REVIEW_STATE: [
                CallbackQueryHandler(cancel_edit_handler, pattern="^cancel_edit$"),
                MessageHandler(Filters.text & ~Filters.command, edit_review_handler),
            ],
            DEMOGRAPHIC_CHOICE: [
                CallbackQueryHandler(demographic_choice_handler, pattern="^demo_"),
                CallbackQueryHandler(back_to_review_handler, pattern="^back_to_review$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    dp.add_handler(conv_handler)
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()