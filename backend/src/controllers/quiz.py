from ..services import quiz
class QuizController:
    list=staticmethod(quiz.list_sessions)
    preview=staticmethod(quiz.preview)
    create=staticmethod(quiz.create_session)
    get=staticmethod(quiz.session_detail)
    answer=staticmethod(quiz.answer)
    interrupt=staticmethod(quiz.interrupt)
    resume=staticmethod(quiz.resume)
