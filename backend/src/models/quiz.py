from sqlalchemy import Column,Integer,String,JSON,ForeignKey,UniqueConstraint
from ..config.database import Base
from ..config.settings import CONFIG
class QuizSession(Base):
    __tablename__=CONFIG['quiz_table']
    id=Column(Integer,primary_key=True)
    run_id=Column(Integer,ForeignKey(CONFIG['run_table']+'.id'),nullable=False)
    guest=Column(String(160),nullable=False)
    state=Column(String(20),default='answering')
    questions=Column(JSON,nullable=False)
    samples=Column(JSON,nullable=False)
    answers=Column(JSON,nullable=False,default=dict)
    bound=Column(Integer,nullable=False)
    result=Column(JSON,nullable=True)
    created_at=Column(String(40),nullable=False)
class QuizAnswer(Base):
    __tablename__=CONFIG['quiz_answer_table']
    __table_args__=(UniqueConstraint('session_id','exhibit',name='uq_quiz_answer'),)
    id=Column(Integer,primary_key=True)
    session_id=Column(Integer,ForeignKey(CONFIG['quiz_table']+'.id'),nullable=False)
    exhibit=Column(String(120),nullable=False)
    rating=Column(Integer,nullable=False)
    created_at=Column(String(40),nullable=False)
