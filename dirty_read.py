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
    print("Таблица accounts создана. Начальный баланс: 1000\n")


def tx1():
    conn = get_conn()
    cur = conn.cursor()
    print("[TX1] Старт транзакции")
    cur.execute("UPDATE accounts SET balance = 9999 WHERE id = 1")
    print("[TX1] Баланс изменён на 9999 — НЕ зафиксировано")
    time.sleep(2)          # TX2 читает в этот момент
    conn.rollback()
    print("[TX1] ROLLBACK — изменения отменены")
    cur.close()
    conn.close()


def tx2():
    time.sleep(0.5)        # Ждём, пока TX1 сделает UPDATE
    conn = get_conn()
    # PostgreSQL READ UNCOMMITTED фактически = READ COMMITTED, dirty read невозможен
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_UNCOMMITTED)
    cur = conn.cursor()
    print("[TX2] Старт транзакции (уровень: READ UNCOMMITTED)")
    cur.execute("SELECT balance FROM accounts WHERE id = 1")
    balance = cur.fetchone()[0]
    print(f"[TX2] Прочитанный баланс: {balance}")
    if balance == 9999:
        print("[TX2] ⚠️  DIRTY READ: видны незафиксированные данные TX1!")
    else:
        print("[TX2] ✓  Dirty Read не произошёл — PostgreSQL защищает даже на READ UNCOMMITTED")
    conn.commit()
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
    print(f"\nИтоговый баланс после обеих транзакций: {cur.fetchone()[0]}")
    cur.close()
    conn.close()

    print("\n--- Как избежать ---")
    print("Использовать уровень изоляции READ COMMITTED и выше.")
    print("В PostgreSQL dirty read невозможен на любом уровне.")
