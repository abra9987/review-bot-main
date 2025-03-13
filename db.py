import psycopg2
import os
import logging
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения из .env файла
load_dotenv()

# Параметры подключения к базе данных из переменных окружения
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DATABASE_URL = os.getenv("DATABASE_URL")  # Для совместимости с Railway

def get_connection():
    """Возвращает соединение с базой данных."""
    try:
        # Пробуем сначала через отдельные параметры
        if DB_HOST and DB_NAME and DB_USER and DB_PASSWORD:
            logger.info(f"Подключаюсь к базе данных {DB_NAME} на сервере {DB_HOST}")
            return psycopg2.connect(
                host=DB_HOST,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
        # Если какие-то параметры отсутствуют, пробуем через URL
        elif DATABASE_URL:
            logger.info("Подключаюсь к базе данных через DATABASE_URL")
            return psycopg2.connect(DATABASE_URL)
        else:
            raise ValueError("Не настроены параметры подключения к базе данных")
    except Exception as e:
        logger.error(f"Ошибка подключения к базе данных: {e}")
        raise

def create_tables():
    """Создает таблицы в базе данных, если они не существуют."""
    logger.info("Создание таблиц в базе данных...")
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Создаем таблицу пользователей
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            business_type TEXT NOT NULL
        )
        """)
        
        # Создаем таблицу вопросов
        cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY,
            business_type TEXT NOT NULL,
            question_text TEXT NOT NULL,
            question_order INT NOT NULL
        )
        """)
        
        # Создаем таблицу для хранения промптов для разных бизнес-типов
        cur.execute("""
        CREATE TABLE IF NOT EXISTS prompts (
            id SERIAL PRIMARY KEY,
            business_type TEXT UNIQUE NOT NULL,
            prompt_text TEXT NOT NULL
        )
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        logger.info("Таблицы успешно созданы")
    except Exception as e:
        logger.error(f"Ошибка при создании таблиц: {e}")
        raise

def check_user(telegram_id):
    """
    Проверяет, есть ли пользователь в базе данных.
    Возвращает business_type если пользователь найден, иначе None.
    """
    logger.info(f"Проверка пользователя с Telegram ID: {telegram_id}")
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT business_type FROM users WHERE telegram_id = %s", (telegram_id,))
        result = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if result:
            logger.info(f"Пользователь найден, business_type: {result[0]}")
            return result[0]
        else:
            logger.info("Пользователь не найден")
            return None
    except Exception as e:
        logger.error(f"Ошибка при проверке пользователя: {e}")
        return None

def get_questions(business_type):
    """
    Возвращает список вопросов для указанного типа бизнеса.
    Вопросы сортируются по question_order.
    Возвращаются только уникальные вопросы (максимум 4).
    """
    logger.info(f"Получение вопросов для типа бизнеса: {business_type}")
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Получаем уникальные вопросы, отсортированные по question_order
        cur.execute("""
        SELECT DISTINCT ON (question_text) question_text 
        FROM questions 
        WHERE business_type = %s
        ORDER BY question_text, question_order
        """, (business_type,))
        
        all_questions = [row[0] for row in cur.fetchall()]
        
        # Дополнительная проверка на уникальность и валидность
        valid_questions = []
        seen = set()
        
        for question in all_questions:
            # Проверяем, что вопрос не пустой и не повторяется
            if question and question not in seen and len(question.strip()) > 0:
                seen.add(question)
                valid_questions.append(question)
        
        # Логируем результат
        logger.info(f"Найдено {len(valid_questions)} уникальных вопросов, ограничиваем до 4")
        
        # Ограничиваем до 4 вопросов
        result = valid_questions[:4]
        
        # Если вопросов меньше 4, логируем это
        if len(result) < 4:
            logger.warning(f"Внимание: для типа бизнеса {business_type} найдено только {len(result)} вопросов из 4 необходимых")
        
        cur.close()
        conn.close()
        
        return result
    except Exception as e:
        logger.error(f"Ошибка при получении вопросов: {e}")
        # В случае ошибки возвращаем пустой список, чтобы бот мог корректно обработать ситуацию
        return []

def get_prompt(business_type):
    """
    Возвращает промпт для указанного типа бизнеса.
    Если промпт не найден, возвращает стандартный промпт.
    """
    logger.info(f"Получение промпта для типа бизнеса: {business_type}")
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT prompt_text FROM prompts WHERE business_type = %s", (business_type,))
        result = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if result:
            logger.info("Промпт найден в базе данных")
            return result[0]
        else:
            logger.info("Промпт не найден, используем стандартный")
            return "На основе следующих ответов составь отзыв:\n\n{}\n\nСоставь связный, теплый отзыв, будто писал клиент, который остался доволен сервисом."
    except Exception as e:
        logger.error(f"Ошибка при получении промпта: {e}")
        # В случае ошибки возвращаем стандартный промпт
        return "На основе следующих ответов составь отзыв:\n\n{}\n\nСоставь связный, теплый отзыв, будто писал клиент, который остался доволен сервисом."
