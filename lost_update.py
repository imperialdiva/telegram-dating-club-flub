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
    cur.execute("DROP TABLE IF EXISTS accounts")
    cur.execute("CREATE TABLE accounts (id INT PRIMARY KEY, balance INT)")
    cur.execute("INSERT INTO accounts VALUES (1, 1000)")
    cur.close()
    conn.close()
    print("Таблица accounts создана. Начальный баланс: 1000")
    print("Ожидаемый итог: TX1 +100, TX2 +200 → должно быть 1300\n")


def tx1():
    conn = get_conn()
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)
    cur = conn.cursor()
    print("[TX1] Старт — читаем баланс")
    cur.execute("SELECT balance FROM accounts WHERE id = 1")
    balance = cur.fetchone()[0]
    print(f"[TX1] Прочитан баланс: {balance}")

    time.sleep(2)          

    new_balance = balance + 100
    cur.execute("UPDATE accounts SET balance = %s WHERE id = 1", (new_balance,))
    conn.commit()
    print(f"[TX1] COMMIT — записан баланс: {new_balance} (было {balance} + 100)")
    cur.close()
    conn.close()


def tx2():
    time.sleep(0.5)        
    conn = get_conn()
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)
    cur = conn.cursor()
    print("[TX2] Старт — читаем баланс")
    cur.execute("SELECT balance FROM accounts WHERE id = 1")
    balance = cur.fetchone()[0]
    print(f"[TX2] Прочитан баланс: {balance}")

    new_balance = balance + 200
    cur.execute("UPDATE accounts SET balance = %s WHERE id = 1", (new_balance,))
    conn.commit()
    print(f"[TX2] COMMIT — записан баланс: {new_balance} (было {balance} + 200)")
    cur.close()
    conn.close()


if __name__ == '__main__':
    setup()

    t1 = threading.Thread(target=tx1)
    t2 = threading.Thread(target=tx2)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT balance FROM accounts WHERE id = 1")
    final = cur.fetchone()[0]
    cur.close()
    conn.close()

    print(f"\nИтоговый баланс: {final}")
    if final != 1300:
        print(f"⚠️  LOST UPDATE: ожидалось 1300, получили {final}. Одно обновление потеряно!")
    else:
        print("✓  Оба обновления сохранены")

    print("\n--- Как избежать ---")
    print("1. Атомарный UPDATE: SET balance = balance + 100 (без read-modify-write в приложении)")
    print("2. Оптимистичная блокировка: версионирование строки (поле version)")
    print("3. SELECT FOR UPDATE: явная блокировка строки до изменения")
    print("4. Уровень изоляции SERIALIZABLE")
