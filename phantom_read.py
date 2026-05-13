import psycopg2
import threading
import time

from db_config import DB_CONFIG


def get_conn(isolation_level=None):
    conn = psycopg2.connect(**DB_CONFIG)
    if isolation_level is not None:
        conn.set_isolation_level(isolation_level)
    return conn


def setup():
    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS orders")
    cur.execute("CREATE TABLE orders (id SERIAL PRIMARY KEY, user_id INT, amount INT)")
    cur.execute("INSERT INTO orders (user_id, amount) VALUES (1, 100), (1, 200), (1, 50)")
    cur.close()
    conn.close()
    print("Таблица orders создана. Заказов у user_id=1: 3\n")


def tx1():
    time.sleep(1)          
    conn = get_conn()
    cur = conn.cursor()
    print("[TX1] Старт — добавляем новый заказ для user_id=1")
    cur.execute("INSERT INTO orders (user_id, amount) VALUES (1, 500)")
    conn.commit()
    print("[TX1] COMMIT — новый заказ добавлен")
    cur.close()
    conn.close()


def tx2():
    conn = get_conn()
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)
    cur = conn.cursor()
    print("[TX2] Старт транзакции (уровень: READ COMMITTED)")

    cur.execute("SELECT COUNT(*) FROM orders WHERE user_id = 1")
    count1 = cur.fetchone()[0]
    print(f"[TX2] Первый COUNT заказов: {count1}")

    time.sleep(2)          

    cur.execute("SELECT COUNT(*) FROM orders WHERE user_id = 1")
    count2 = cur.fetchone()[0]
    print(f"[TX2] Второй COUNT заказов: {count2}")

    if count1 != count2:
        print(f"[TX2] PHANTOM READ: {count1} → {count2}, появились 'фантомные' строки!")
    else:
        print("[TX2] ✓  Количество строк не изменилось")

    conn.commit()
    cur.close()
    conn.close()


if __name__ == '__main__':
    setup()

    t1 = threading.Thread(target=tx1)
    t2 = threading.Thread(target=tx2)
    t2.start()
    t1.start()
    t1.join()
    t2.join()

    print("\n--- Как избежать ---")
    print("Использовать уровень изоляции SERIALIZABLE.")
    print("На REPEATABLE READ PostgreSQL тоже защищает от фантомных чтений.")
