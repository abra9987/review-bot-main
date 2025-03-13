import psycopg2
import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Печатаем информацию для отладки
print("Подключение к базе данных...")
print(f"DB_HOST: {os.getenv('DB_HOST')}")
print(f"DB_NAME: {os.getenv('DB_NAME')}")
print(f"DB_USER: {os.getenv('DB_USER')}")
# Пароль не печатаем в целях безопасности

def get_connection():
    """Возвращает соединение с базой данных."""
    # Используем прямое указание переменных, а не через переменные
    try:
        connection = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )
        print("Успешное подключение к базе данных!")
        return connection
    except Exception as e:
        print(f"Ошибка подключения к базе данных: {e}")
        # Пробуем подключиться через DATABASE_URL, если он есть
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            print("Пробуем подключение через DATABASE_URL...")
            try:
                return psycopg2.connect(database_url)
            except Exception as e2:
                print(f"Ошибка подключения через DATABASE_URL: {e2}")
                raise
        raise

def remove_duplicate_questions():
    """
    Удаляет дублирующиеся вопросы из базы данных, оставляя только по одному
    вопросу каждого типа для каждого business_type.
    """
    try:
        print("Начинаем очистку базы данных от дубликатов вопросов...")
        conn = get_connection()
        cur = conn.cursor()
        
        # Получаем все business_type
        cur.execute("SELECT DISTINCT business_type FROM questions")
        business_types = [row[0] for row in cur.fetchall()]
        
        print(f"Найдено типов бизнеса: {len(business_types)}")
        
        for bt in business_types:
            print(f"Обработка типа бизнеса: {bt}")
            
            # Получаем уникальные тексты вопросов для этого business_type
            cur.execute("SELECT DISTINCT question_text FROM questions WHERE business_type = %s", (bt,))
            unique_questions = [row[0] for row in cur.fetchall()]
            
            print(f"Найдено {len(unique_questions)} уникальных вопросов для типа {bt}")
            
            # Для каждого уникального текста вопроса оставляем только одну запись в базе
            for i, question_text in enumerate(unique_questions):
                # Получаем все ID вопросов с этим текстом
                cur.execute(
                    "SELECT id FROM questions WHERE business_type = %s AND question_text = %s ORDER BY id",
                    (bt, question_text)
                )
                question_ids = [row[0] for row in cur.fetchall()]
                
                print(f"Вопрос для типа {bt}: '{question_text[:30]}...' имеет {len(question_ids)} записей")
                
                if len(question_ids) > 1:
                    # Оставляем только первый ID, удаляем остальные
                    keep_id = question_ids[0]
                    delete_ids = question_ids[1:]
                    
                    print(f"Оставляем ID {keep_id}, удаляем {len(delete_ids)} дубликатов")
                    
                    # Обновляем order для оставшегося вопроса
                    cur.execute(
                        "UPDATE questions SET question_order = %s WHERE id = %s",
                        (i, keep_id)
                    )
                    
                    # Удаляем дубликаты
                    if delete_ids:  # Проверяем, что список не пустой
                        delete_list = tuple(delete_ids)
                        if len(delete_list) == 1:
                            # Для одиночного значения добавляем запятую, чтобы сделать его кортежем
                            cur.execute(
                                "DELETE FROM questions WHERE id = %s",
                                (delete_list[0],)
                            )
                        else:
                            cur.execute(
                                "DELETE FROM questions WHERE id IN %s",
                                (delete_list,)
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
        print("Очистка базы данных успешно завершена")
    except Exception as e:
        print(f"Произошла ошибка при очистке базы данных: {e}")
        raise

if __name__ == "__main__":
    remove_duplicate_questions()
