from db_cleanup import remove_duplicate_questions

if __name__ == "__main__":
    remove_duplicate_questions()
    print("Очистка завершена. Теперь можно обновить db.py")
