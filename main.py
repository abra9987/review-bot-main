import logging
import urllib.parse
import os
import openai
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
START_MENU, QUESTION, CONFIRM_REVIEW, EDIT_REVIEW_STATE = range(4)

# Настройка OpenAI API
openai.api_key = OPENAI_API_KEY

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Стартовое меню ---
def start(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    
    # Проверяем, авторизован ли пользователь
    business_type = check_user(user_id)
    
    if not business_type:
        if update.message:
            update.message.reply_text("Вы не авторизованы. Обратитесь к администратору.")
        else:
            update.callback_query.message.reply_text("Вы не авторизованы. Обратитесь к администратору.")
        return ConversationHandler.END
    
    # Сохраняем бизнес-тип в контексте
    context.user_data["business_type"] = business_type
    
    # Загружаем вопросы для этого бизнес-типа
    questions = get_questions(business_type)
    
    if not questions:
        if update.message:
            update.message.reply_text(f"Ошибка: вопросы для типа бизнеса '{business_type}' не найдены. Обратитесь к администратору.")
        else:
            update.callback_query.message.reply_text(f"Ошибка: вопросы для типа бизнеса '{business_type}' не найдены. Обратитесь к администратору.")
        return ConversationHandler.END
    
    # Сохраняем вопросы в контексте
    context.user_data["questions"] = questions
    
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

def start_menu_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    
    if query.data == "start_survey":
        context.user_data["current_question"] = 0
        context.user_data["answers"] = []
        
        questions = context.user_data.get("questions", [])
        if not questions:
            query.edit_message_text(text="Ошибка: вопросы не найдены. Обратитесь к администратору.")
            return ConversationHandler.END
        
        question_text = f"📝 Вопрос 1/{len(questions)}:\n{questions[0]}"
        query.edit_message_text(text=question_text)
        return QUESTION
    
    elif query.data == "cancel":
        query.edit_message_text(text="Анкетирование отменено.")
        return ConversationHandler.END

# --- Этап вопросов ---
def answer_handler(update: Update, context: CallbackContext) -> int:
    current_q = context.user_data.get("current_question", 0)
    answer = update.message.text
    answers = context.user_data.get("answers", [])
    
    if len(answers) > current_q:
        answers[current_q] = answer
    else:
        answers.append(answer)
    
    context.user_data["answers"] = answers

    # Подтверждаем ответ с кнопками "Изменить ответ" и "Далее"
    keyboard = [
        [
            InlineKeyboardButton("🔄 Изменить ответ", callback_data="edit_answer"),
            InlineKeyboardButton("⏭ Далее", callback_data="next_question"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(f"Ответ: \"{answer}\"\nВыберите действие:", reply_markup=reply_markup)
    return QUESTION

def question_callback_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    
    current_q = context.user_data.get("current_question", 0)
    questions = context.user_data.get("questions", [])
    
    if query.data == "edit_answer":
        query.edit_message_text(
            text=f"📝 Вопрос {current_q+1}/{len(questions)}:\n{questions[current_q]}\nПожалуйста, введите новый ответ:"
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
            # Формируем промпт для генерации отзыва
            answers = context.user_data.get("answers", [])
            business_type = context.user_data.get("business_type")
            
            # Получаем шаблон промпта для этого бизнес-типа
            prompt_template = get_prompt(business_type)
            
            # Формируем список ответов для вставки в промпт
            answers_text = ""
            for i, ans in enumerate(answers):
                answers_text += f"{i+1}. {ans}\n"
            
            # Подставляем ответы в шаблон промпта
            prompt = prompt_template.format(answers_text)
            
            query.edit_message_text(text="Формирую отзыв, пожалуйста, подождите...")
            
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "Ты помогаешь составить отзыв для клиники."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                    max_tokens=200,
                )
                generated_review = response.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"Ошибка при вызове OpenAI API: {e}")
                query.edit_message_text(text="Произошла ошибка при генерации отзыва. Попробуйте позже.")
                return ConversationHandler.END

            context.user_data["generated_review"] = generated_review
            
            # Выводим сгенерированный отзыв с набором из трёх кнопок
            keyboard = [
                [
                    InlineKeyboardButton("✏️ Отредактировать отзыв", callback_data="edit_review"),
                    InlineKeyboardButton("✅ Отправить в WhatsApp", callback_data="send_whatsapp"),
                    InlineKeyboardButton("🔄 Начать заново", callback_data="restart"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            review_text = f"🎉 Отзыв сформирован:\n\"{generated_review}\""
            query.edit_message_text(text=review_text, reply_markup=reply_markup)
            return CONFIRM_REVIEW
    else:
        query.edit_message_text(text="Неизвестная команда, завершаем диалог.")
        return ConversationHandler.END

# --- Этап подтверждения отзыва ---
def review_callback_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    
    if query.data == "edit_review":
        # Предлагаем ввести отредактированный отзыв с кнопкой "Назад"
        keyboard = [[InlineKeyboardButton("Назад", callback_data="cancel_edit")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(
            text="Пожалуйста, введите отредактированный вариант отзыва или нажмите 'Назад', чтобы отменить редактирование:",
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
            text="Отправьте отзыв через WhatsApp или выберите другое действие:",
            reply_markup=reply_markup,
        )
        return CONFIRM_REVIEW
    
    elif query.data == "back_from_whatsapp":
        generated_review = context.user_data.get("generated_review", "")
        keyboard = [
            [
                InlineKeyboardButton("✏️ Отредактировать отзыв", callback_data="edit_review"),
                InlineKeyboardButton("✅ Отправить в WhatsApp", callback_data="send_whatsapp"),
                InlineKeyboardButton("🔄 Начать заново", callback_data="restart"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(
            text=f"🎉 Отзыв сформирован:\n\"{generated_review}\"", reply_markup=reply_markup
        )
        return CONFIRM_REVIEW
    
    elif query.data == "restart":
        # Начинаем заново, сохраняя business_type и questions
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
    
    else:
        query.edit_message_text(text="Неизвестная команда, завершаем диалог.")
        return ConversationHandler.END

def edit_review_handler(update: Update, context: CallbackContext) -> int:
    edited_review = update.message.text
    context.user_data["generated_review"] = edited_review
    
    keyboard = [
        [
            InlineKeyboardButton("✏️ Отредактировать отзыв", callback_data="edit_review"),
            InlineKeyboardButton("✅ Отправить в WhatsApp", callback_data="send_whatsapp"),
            InlineKeyboardButton("🔄 Начать заново", callback_data="restart"),
        ]
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
            InlineKeyboardButton("✅ Отправить в WhatsApp", callback_data="send_whatsapp"),
            InlineKeyboardButton("🔄 Начать заново", callback_data="restart"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        text=f"Отзыв сохранён:\n\"{generated_review}\"", reply_markup=reply_markup
    )
    return CONFIRM_REVIEW

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Диалог отменен.")
    return ConversationHandler.END

def main():
    # Создаем таблицы в базе данных, если они не существуют
    create_tables()
    
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            START_MENU: [CallbackQueryHandler(start_menu_handler, pattern="^(start_survey|cancel)$")],
            QUESTION: [
                MessageHandler(Filters.text & ~Filters.command, answer_handler),
                CallbackQueryHandler(question_callback_handler, pattern="^(edit_answer|next_question)$"),
            ],
            CONFIRM_REVIEW: [
                CallbackQueryHandler(
                    review_callback_handler, pattern="^(edit_review|send_whatsapp|back_from_whatsapp|restart)$"
                ),
            ],
            EDIT_REVIEW_STATE: [
                CallbackQueryHandler(cancel_edit_handler, pattern="^cancel_edit$"),
                MessageHandler(Filters.text & ~Filters.command, edit_review_handler),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    dp.add_handler(conv_handler)
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()