from fastapi import APIRouter,Depends
from ..config.database import db_session
from ..schemas.quiz import QuizCreate,QuizPreview,AnswerInput
from ..services.auth import current_user,writer
from ..controllers.quiz import QuizController as C
router=APIRouter()
@router.get('/quiz')
def sessions(db=Depends(db_session),u=Depends(current_user)):return C.list(db)
@router.post('/quiz/preview')
def preview(data:QuizPreview,db=Depends(db_session),u=Depends(current_user)):return C.preview(db,data)
@router.post('/quiz')
def create(data:QuizCreate,db=Depends(db_session),u=Depends(writer)):return C.create(db,u,data)
@router.get('/quiz/{id}')
def detail(id:int,db=Depends(db_session),u=Depends(current_user)):return C.get(db,id)
@router.post('/quiz/{id}/answers')
def answer(id:int,data:AnswerInput,db=Depends(db_session),u=Depends(writer)):return C.answer(db,u,id,data)
@router.post('/quiz/{id}/interrupt')
def interrupt(id:int,db=Depends(db_session),u=Depends(writer)):return C.interrupt(db,u,id)
@router.post('/quiz/{id}/resume')
def resume(id:int,db=Depends(db_session),u=Depends(writer)):return C.resume(db,u,id)
