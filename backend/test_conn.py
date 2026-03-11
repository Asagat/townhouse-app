import psycopg2

try:
    print("Пробую подключиться к локальному Postgres...")
    conn = psycopg2.connect(
        dbname="townhouse_db",
        user="postgres",
        password="postgres",
        host="127.0.0.1",
        port="5432",
        connect_timeout=3,
    )
    print("✅ Соединение установлено успешно!")
    conn.close()
except Exception as e:
    print(f"❌ Ошибка: {e}")
