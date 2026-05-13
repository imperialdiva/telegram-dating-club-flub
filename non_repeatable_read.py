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
    cur.execute("DROP TABLE IF EXISTS employees")
    cur.execute("CREATE TABLE employees (id INT PRIMARY KEY, name TEXT, salary INT)")
    cur.execute("INSERT INTO employees VALUES (1, 'Alice', 50000)")
    cur.close()
    conn.close()
    print("Таблица employees создана. Начальная зарплата Alice: 50000\n")


def tx1():
    time.sleep(1)          
    conn = get_conn()
    cur = conn.cursor()
    print("[TX1] Старт — обновляем зарплату до 70000")
    cur.execute("UPDATE employees SET salary = 70000 WHERE id = 1")
    conn.commit()
    print("[TX1] COMMIT — зарплата зафиксирована: 70000")
    cur.close()
    conn.close()


def tx2():
    conn = get_conn()
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)
    cur = conn.cursor()
    print("[TX2] Старт транзакции (уровень: READ COMMITTED)")

    cur.execute("SELECT salary FROM employees WHERE id = 1")
    salary1 = cur.fetchone()[0]
    print(f"[TX2] Первое чтение зарплаты: {salary1}")

    time.sleep(2)          

    cur.execute("SELECT salary FROM employees WHERE id = 1")
    salary2 = cur.fetchone()[0]
    print(f"[TX2] Второе чтение зарплаты: {salary2}")

    if salary1 != salary2:
        print(f"[TX2] ⚠️  NON-REPEATABLE READ: {salary1} → {salary2}, данные изменились внутри транзакции!")
    else:
        print("[TX2] ✓  Значения совпадают")

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
    print("Использовать уровень изоляции REPEATABLE READ или SERIALIZABLE.")
    print("На REPEATABLE READ TX2 будет видеть одно и то же значение на протяжении всей транзакции.")
