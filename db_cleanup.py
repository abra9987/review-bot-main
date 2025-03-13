import psycopg2
import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Параметры подключения к базе данных из переменных окружения
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

def get_connection():
    """Возвращает соединение с базой данных."""
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def remove_duplicate_questions():
    """
    Удаляет дублирующиеся вопросы из базы данных, оставляя только по одному
    вопросу каждого типа для каждого business_type.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Получаем все business_type
    cur.execute("SELECT DISTINCT business_type FROM questions")
    business_types = [row[0] for row in cur.fetchall()]
    
    for bt in business_types:
        print(f"Обработка типа бизнеса: {bt}")
        
        # Получаем уникальные тексты вопросов для этого business_type
        cur.execute("SELECT DISTINCT question_text FROM questions WHERE business_type = %s", (bt,))
        unique_questions = [row[0] for row in cur.fetchall()]
        
        print(f"Найдено {len(unique_questions)} уникальных вопросов")
        
        # Для каждого уникального текста вопроса оставляем только одну запись в базе
        for i, question_text in enumerate(unique_questions):
            # Получаем все ID вопросов с этим текстом
            cur.execute(
                "SELECT id FROM questions WHERE business_type = %s AND question_text = %s ORDER BY id",
                (bt, question_text)
            )
            question_ids = [row[0] for row in cur.fetchall()]
            
            if len(question_ids) > 1:
                # Оставляем только первый ID, удаляем остальные
                keep_id = question_ids[0]
                delete_ids = question_ids[1:]
                
                print(f"Вопрос: '{question_text[:30]}...' - оставляем ID {keep_id}, удаляем {len(delete_ids)} дубликатов")
                
                # Обновляем order для оставшегося вопроса
                cur.execute(
                    "UPDATE questions SET question_order = %s WHERE id = %s",
                    (i, keep_id)
                )
                
                # Удаляем дубликаты
                cur.execute(
                    "DELETE FROM questions WHERE id IN %s",
                    (tuple(delete_ids),)
                )
            else:
                # Обновляем order для единственного вопроса
                cur.execute(
                    "UPDATE questions SET question_order = %s WHERE id = %s",
                    (i, question_ids[0])
                )
    
    conn.commit()
    cur.close()
    conn.close()
    print("Очистка базы данных завершена")

if __name__ == "__main__":
    remove_duplicate_questions()
