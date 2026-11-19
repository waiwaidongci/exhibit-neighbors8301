import math
from collections import Counter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from ..config.settings import CONFIG
from ..models.quiz import QuizSession,QuizAnswer
from ..models.run import Run
from ..utils.serialization import row,now
from .runs import get_run
from .audit import log
MAX_QUESTIONS=int(CONFIG.get('max_questions',8))
STARS=(1,2,3,4,5)
_NODE_BUDGET=100000
def star(value):
    # 样本评分四舍五入归入最近星级；缺评在相容判定中通配任意星级
    return min(5,max(1,int(math.floor(float(value)+0.5))))
def build_samples(run):
    # 标签=已完成研究中每位访客的首推：预测最高的策展建议，按(访客, 预测降序, 展品代码)稳定取一
    labels={}
    for r in sorted(run.result.get('recommendations',[]),key=lambda x:(x['visitor'],-x['prediction'],x['exhibit'])):
        labels.setdefault(r['visitor'],r['exhibit'])
    ratings={}
    for rec in run.snapshot['records']:
        v=rec['values'];ratings.setdefault(v['visitor'],{})[v['exhibit']]=star(v['rating'])
    samples=[{'visitor':uid,'label':labels[uid],'stars':ratings[uid]} for uid in sorted(labels) if uid in ratings]
    if len(samples)<2:raise HTTPException(422,'已完成研究中可用首推标签样本不足')
    return samples
def pick_questions(samples,exhibits=None):
    cover=Counter()
    for s in samples:
        for e in s['stars']:cover[e]+=1
    if exhibits is None:
        return [e for e,_ in sorted(cover.items(),key=lambda kv:(-kv[1],kv[0]))[:MAX_QUESTIONS]]
    chosen=list(dict.fromkeys(e for e in exhibits if isinstance(e,str) and e.strip()))
    if not 1<=len(chosen)<=MAX_QUESTIONS:raise HTTPException(422,f'候选题需1–{MAX_QUESTIONS}件展品')
    unknown=[e for e in chosen if e not in cover]
    if unknown:raise HTTPException(422,'候选题不在研究展品范围内：'+'、'.join(unknown))
    return chosen
class _Budget(Exception):pass
def evaluate(samples,questions,answers):
    # 相容样本：已答题上样本缺评（通配任意星级）或星级一致
    comp=tuple(i for i,s in enumerate(samples) if all(s['stars'].get(q) in (None,a) for q,a in answers.items()))
    base={'asked':len(answers),'compatible':len(comp)}
    if not comp:return {**base,'outcome':'empty'}
    first=samples[comp[0]]['label']
    if all(samples[i]['label']==first for i in comp):return {**base,'outcome':'recommend','label':first}
    remaining=[q for q in questions if q not in answers]
    if not remaining:
        return {**base,'outcome':'conflict','conflicts':[{'visitor':samples[i]['visitor'],'label':samples[i]['label'],'stars':{q:samples[i]['stars'].get(q) for q in answers}} for i in comp]}
    labels=[s['label'] for s in samples];stars=[s['stars'] for s in samples]
    idx={q:i for i,q in enumerate(questions)};full=(1<<len(questions))-1
    mask=0
    for q in answers:mask|=1<<idx[q]
    memo={};spent=[0]
    def terminal(c):
        if not c:return True
        f=labels[c[0]]
        return all(labels[i]==f for i in c)
    def solve(c,m):
        # 返回(最坏情况余题数, 下一题)；进入时c非空、标签不一致、m未问尽
        key=(m,c)
        if key in memo:return memo[key]
        spent[0]+=1
        if spent[0]>_NODE_BUDGET:raise _Budget
        best=None;best_q=None
        for qi,q in enumerate(questions):
            if m>>qi&1:continue
            worst=0
            for a in STARS:
                child=tuple(i for i in c if stars[i].get(q) in (None,a))
                if not child or terminal(child):cost=0
                elif m|(1<<qi)==full:cost=0
                else:cost=solve(child,m|(1<<qi))[0]
                if cost>worst:worst=cost
                if best is not None and worst>=best:break
            if best is None or 1+worst<best:best,best_q=1+worst,q
            if best==1:break
        memo[key]=(best,best_q)
        return memo[key]
    try:
        bound,next_q=solve(comp,mask);approx=False
    except _Budget:
        # 超出搜索预算时兜底：贪心收缩相容集，余题上限退化为剩余题数（仍是安全上限）
        next_q=min(remaining,key=lambda q:(max(sum(1 for i in comp if stars[i].get(q) in (None,a)) for a in STARS),idx[q]))
        bound=len(remaining);approx=True
    return {**base,'outcome':None,'next':next_q,'bound':bound,'approximate':approx,'labels':sorted({labels[i] for i in comp})}
def _result_of(ev):
    if ev['outcome']=='recommend':return {'outcome':'recommend','label':ev['label'],'compatible':ev['compatible']}
    if ev['outcome']=='empty':return {'outcome':'empty'}
    return {'outcome':'conflict','conflicts':ev['conflicts']}
def _summary(ev):
    if ev['outcome']=='recommend':return '相容样本首推一致，推荐 '+ev['label']
    if ev['outcome']=='empty':return '没有相容样本'
    return '问尽仍有分歧，冲突样本 '+str(len(ev['conflicts']))+' 个'
def get_session(db,id):
    s=db.get(QuizSession,id)
    if not s:raise HTTPException(404,'未找到快问场次')
    return s
def _payload(db,s,deduplicated=False):
    ev=evaluate(s.samples,s.questions,s.answers)
    run=db.get(Run,s.run_id)
    return {**{k:v for k,v in row(s).items() if k!='samples'},'run_name':run.name if run else '','samples_count':len(s.samples),'progress':ev,'deduplicated':deduplicated}
def list_sessions(db):
    return [{k:v for k,v in row(s).items() if k!='samples'} for s in db.scalars(select(QuizSession).order_by(QuizSession.id.desc()))]
def session_detail(db,id):return _payload(db,get_session(db,id))
def preview(db,data):
    r=get_run(db,data.run_id)
    if r.state!='completed':raise HTTPException(409,'仅已完成的研究可开卷')
    samples=build_samples(r)
    cover=Counter()
    for s in samples:
        for e in s['stars']:cover[e]+=1
    questions=pick_questions(samples,data.exhibits)
    ev=evaluate(samples,questions,{})
    labels=Counter(s['label'] for s in samples)
    return {'run_id':r.id,'run_name':r.name,'samples':len(samples),'coverage':[{'exhibit':e,'count':c} for e,c in sorted(cover.items(),key=lambda kv:(-kv[1],kv[0]))],'questions':questions,'bound':ev.get('bound',0),'approximate':ev.get('approximate',False),'outcome':ev['outcome'],'label':ev.get('label'),'labels':[{'label':k,'count':v} for k,v in sorted(labels.items())]}
def create_session(db,user,data):
    r=get_run(db,data.run_id)
    if r.state!='completed':raise HTTPException(409,'仅已完成的研究可开卷')
    samples=build_samples(r)
    questions=pick_questions(samples,data.exhibits)
    ev=evaluate(samples,questions,{})
    guest=data.guest.strip() or '新访客'
    s=QuizSession(run_id=r.id,guest=guest,state='answering',questions=questions,samples=samples,answers={},bound=ev.get('bound',0),created_at=now())
    if ev['outcome']:
        s.state='completed';s.result=_result_of(ev)
    db.add(s);db.flush()
    log(db,user,'quiz.opened',s.id,f'锁定研究 #{r.id} · 候选题 {len(questions)} 件 · 余题上限 {s.bound}')
    db.commit()
    return _payload(db,s)
def answer(db,user,id,data):
    s=get_session(db,id)
    existing=db.scalar(select(QuizAnswer).where(QuizAnswer.session_id==s.id,QuizAnswer.exhibit==data.exhibit))
    if existing:
        if existing.rating==data.rating:return _payload(db,s,deduplicated=True)
        raise HTTPException(409,'该题已收到不同答案，并发作答只采纳其一')
    if s.state=='paused':raise HTTPException(409,'本场已中断，请先恢复续答')
    if s.state=='completed':raise HTTPException(409,'本场已完结，请查看结果')
    ev=evaluate(s.samples,s.questions,s.answers)
    if ev['outcome'] or data.exhibit!=ev['next']:raise HTTPException(409,'请按当前发问题目作答：'+str(ev.get('next') or '已完结'))
    s.answers={**s.answers,data.exhibit:data.rating}
    db.add(QuizAnswer(session_id=s.id,exhibit=data.exhibit,rating=data.rating,created_at=now()))
    try:
        db.flush()
    except IntegrityError:
        # 并发答同一题：唯一约束只放行一个答案，另一个按幂等或冲突处理
        db.rollback()
        s=get_session(db,id)
        dup=db.scalar(select(QuizAnswer).where(QuizAnswer.session_id==s.id,QuizAnswer.exhibit==data.exhibit))
        if dup and dup.rating==data.rating:return _payload(db,s,deduplicated=True)
        raise HTTPException(409,'该题已收到不同答案，并发作答只采纳其一')
    ev=evaluate(s.samples,s.questions,s.answers)
    if ev['outcome']:
        s.state='completed';s.result=_result_of(ev)
        log(db,user,'quiz.completed',s.id,_summary(ev))
    db.commit()
    return _payload(db,s)
def interrupt(db,user,id):
    s=get_session(db,id)
    if s.state=='completed':raise HTTPException(409,'本场已完结')
    if s.state=='answering':
        s.state='paused';log(db,user,'quiz.interrupted',s.id);db.commit()
    return _payload(db,s)
def resume(db,user,id):
    s=get_session(db,id)
    if s.state=='completed':raise HTTPException(409,'本场已完结')
    if s.state=='paused':
        # 下一题由锁定的研究版本、候选题与已答记录确定性重算，即恢复原分支
        s.state='answering';log(db,user,'quiz.resumed',s.id,'恢复原分支');db.commit()
    return _payload(db,s)
