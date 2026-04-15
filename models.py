# models.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, func, UUID
from sqlalchemy.orm import declarative_base, relationship
import uuid

Base = declarative_base()

class Customer(Base):
    __tablename__ = 'customers'
    customer_id = Column(UUID(as_uuid=True),primary_key=True, default=uuid.uuid4)
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String, unique=True)

class Product(Base):
    __tablename__ = 'products'
    product_id = Column(Integer, primary_key=True)
    product_name = Column(String)
    price = Column(Float)

class Order(Base):
    __tablename__ = 'orders'
    order_id = Column(Integer, primary_key=True)
    customer_id = Column(ForeignKey('customers.customer_id'))
    order_date = Column(DateTime, server_default=func.now())
    total_amount = Column(Float, default=0.0)
    items = relationship("OrderItem")

class OrderItem(Base):
    __tablename__ = 'order_items'
    order_item_id = Column(Integer, primary_key=True)
    order_id = Column(ForeignKey('orders.order_id'))
    product_id = Column(ForeignKey('products.product_id'))
    quantity = Column(Integer)
    subtotal = Column(Float)