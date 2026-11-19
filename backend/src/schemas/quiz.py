from pydantic import BaseModel,Field
class QuizCreate(BaseModel):
    run_id:int
    guest:str=Field(default='新访客',min_length=1,max_length=160)
    exhibits:list[str]|None=None
class QuizPreview(BaseModel):
    run_id:int
    exhibits:list[str]|None=None
class AnswerInput(BaseModel):
    exhibit:str=Field(min_length=1,max_length=120)
    rating:int=Field(ge=1,le=5)
