import os
import psycopg2
from dotenv import load_dotenv

# Эта функция будет использоваться для проверки подключения
def test_connection():
    load_dotenv()
    
    # Печатаем значения переменных окружения (кроме пароля)
    print("Переменные окружения:")
    print(f"DB_HOST: {os.getenv('DB_HOST')}")
    print(f"DB_NAME: {os.getenv('DB_NAME')}")
    print(f"DB_USER: {os.getenv('DB_USER')}")
    
    # Проверяем существование переменной DATABASE_URL
    database_url = os.getenv("DATABASE_URL")
    print(f"DATABASE_URL существует: {database_url is not None}")
    
    # Пробуем подключиться к базе данных разными способами
    try:
        print("\nПробуем подключиться к базе напрямую через переменные...")
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )
        print("Успешное подключение!")
        conn.close()
    except Exception as e:
        print(f"Ошибка при подключении напрямую: {e}")
    
    # Пробуем через DATABASE_URL если он существует
    if database_url:
        try:
            print("\nПробуем подключиться через DATABASE_URL...")
            conn = psycopg2.connect(database_url)
            print("Успешное подключение через DATABASE_URL!")
            conn.close()
        except Exception as e:
            print(f"Ошибка при подключении через DATABASE_URL: {e}")
    
    print("\nПроверка подключения завершена.")

# Сначала проверяем подключение
print("=== Начинаем процесс очистки базы данных ===")
print("Проверка подключения к базе данных...")
test_connection()

# Затем запускаем скрипт очистки
print("\nЗапускаем скрипт очистки базы данных...")
try:
    from db_cleanup import remove_duplicate_questions
    remove_duplicate_questions()
    print("\n=== Очистка базы данных успешно завершена ===")
    print("Теперь можно обновить db.py с исправленной функцией get_questions")
except Exception as e:
    print(f"\n=== Произошла ошибка при очистке базы данных ===\n{e}")
