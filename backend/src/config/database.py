from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .settings import DATABASE_URL
class Base(DeclarativeBase): pass
connect_args={'timeout':15,'check_same_thread':False} if DATABASE_URL.startswith('sqlite') else {}
engine=create_engine(DATABASE_URL,pool_pre_ping=True,connect_args=connect_args)
Session=sessionmaker(bind=engine,expire_on_commit=False)
def db_session():
    with Session() as db: yield db
