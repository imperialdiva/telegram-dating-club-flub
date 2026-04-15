import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Customer, Product, Order, OrderItem
import os

user = os.getenv('DB_USER')
password = os.getenv('DB_PASSWORD')
host = os.getenv('DB_HOST', 'localhost')
db_name = os.getenv('DB_NAME')

DATABASE_URL = f"postgresql://{user}:{password}@{host}:5432/{db_name}"

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def main():
    time.sleep(5) 
    Base.metadata.create_all(engine)
    session = Session()

    try:
        cust = Customer(first_name="sago", last_name="madjik", email="madjik@mail.com")
        prod = Product(product_name="Laptop", price=1000.0)
        session.add_all([cust, prod])
        session.commit()

        print("Перый сценарий")
        new_order = Order(customer_id=cust.customer_id)
        session.add(new_order)
        session.flush() 

        item1 = OrderItem(order_id=new_order.order_id, product_id=prod.product_id, quantity=2, subtotal=prod.price * 2)
        session.add(item1)
        
        new_order.total_amount = item1.subtotal
        #raise Exception("error")
        session.commit() 
        print("1 готов")

        print("Второй сценарий")
        customer_to_update = session.query(Customer).filter_by(first_name="sago").first()
        customer_to_update.email = "new_madjik@mail.com"
        session.commit()
        print("12 готов")

        print("Третий сценарий")
        new_product = Product(product_name="Smartphone", price=500.0)
        session.add(new_product)
        session.commit()
        print("3 готов")

    except Exception as e:
        print(f"Error occurred: {e}")
        session.rollback() 
    finally:
        session.close()

if __name__ == "__main__":
    main()