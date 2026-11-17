'use strict';
// Static, dependency-free frontend. All paper selection, option marking and
// scoring happen on the FastAPI server; browser code never receives the answer
// key of an active session.
const root = document.getElementById('root');
const s = {
  view: 'create', meta: null, plan: null, blueprint: null, blueprintError: '',
  studentName: '', studentCode: '', session: null, index: 0,
  adminKey: sessionStorage.getItem('sp_admin_key') || '', adminReady: false,
  bank: [], sessions: [], bankFilter: '', busy: false, notice: '', error: '',
  pendingSave: Promise.resolve(), loadingAdmin: false,
};
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label = t => String(t).replace(/_/g,' ').replace(/\b\w/g,m=>m.toUpperCase());
const fmtDate = x => x ? new Date(x).toLocaleString() : '—';
const shortId = id => String(id || '').slice(0,9) + '…';
const pct = (a,b) => b ? Math.round(a/b*100) : 0;
const getLast = () => localStorage.getItem('sp_last_session') || '';
const setLast = id => localStorage.setItem('sp_last_session',id);
const setMsg = (message,kind='notice') => {s.error=kind==='error'?message:'';s.notice=kind==='notice'?message:'';render();};

async function api(path, method='GET', body=null, admin=false) {
  const headers = {'Content-Type':'application/json'};
  if (admin) headers['X-Admin-Key'] = s.adminKey;
  let resp;
  try {resp = await fetch('/api'+path,{method,headers,body: body===null ? undefined : JSON.stringify(body)});}
  catch {throw Error('Cannot connect to the backend. Check that SecurePaper is running.');}
  const data = await resp.json().catch(()=>({}));
  if (!resp.ok) {
    if (resp.status===401 && admin) {s.adminReady=false;sessionStorage.removeItem('sp_admin_key');}
    const detail = data.detail;
    const msg = typeof detail==='string'?detail:Array.isArray(detail)?detail.map(e=>e.msg).join('; '):'Request failed ('+resp.status+')';
    throw Error(msg);
  }
  return data;
}

function shell(body) {
  return `<header class="topbar"><div class="topbar-inner">
    <div class="brand" data-home="1"><div class="logo">S</div><div><div class="brand-title">SecurePaper<span style="color:#8ea3ff">.</span></div><div class="brand-sub">MCQ Assembly Studio</div></div></div>
    <div class="header-pill"><span class="dot"></span> Database-first demo <span style="opacity:.5">·</span> No LLM needed</div>
  </div></header><div class="nav-wrap"><nav class="nav" aria-label="Navigation">
    ${[['create','Create exam'],['admin','Question bank'],['sessions','Sessions'],['about','How it works']].map(([id,text])=>`<button type="button" data-action="nav" data-target="${id}" class="${s.view===id?'active':''}">${text}</button>`).join('')}
  </nav></div><main class="container">${s.error?`<div class="error" role="alert">${esc(s.error)}</div>`:''}${s.notice?`<div class="success" role="status">${esc(s.notice)}</div>`:''}${body}</main>
  <footer class="footer"><span>SecurePaper v2 · Tagged question bank · 4-option MCQ delivery</span><span>Prototype only · Not a proctored or high-stakes exam system</span></footer>`;
}
function card(title, content, extra='', footer='') {
  return `<section class="card"><div class="card-header"><h3>${title}</h3>${extra}</div><div class="card-body">${content}</div>${footer?`<div class="card-footer">${footer}</div>`:''}</section>`;
}
function render(){
  if (!s.meta) {root.innerHTML=shell('<div class="loading">Connecting to the question database…</div>');return;}
  let view;
  if(s.view==='exam' && s.session) view=renderExam();
  else if(s.view==='result' && s.session) view=renderResult();
  else if(s.view==='admin') view=renderAdmin();
  else if(s.view==='sessions') view=renderSessions();
  else if(s.view==='about') view=renderAbout();
  else view=renderCreate();
  root.innerHTML=shell(view);
  if(s.view==='create') refreshBlueprint();
}
const stat = (number,description,icon) => `<div class="stat"><div><div class="stat-number">${esc(number)}</div><div class="stat-caption">${esc(description)}</div></div><div class="stat-icon">${icon}</div></div>`;
function renderCreate(){
  const subjects=s.meta.subjects;
  const goals=s.meta.goals;
  const types=s.meta.question_types;
  return `<div class="hero"><div><div class="eyebrow">✦ INTELLIGENT TEST ASSEMBLY</div><h1>Different paper. Same learning goals.</h1><p>SecurePaper chooses verified questions from your tagged database, adapts difficulty to the exam purpose, and creates a fresh MCQ set for every student.</p></div><div class="hero-icon" aria-hidden="true">▤</div></div>
  <div class="stat-grid">${stat(s.meta.question_count,'Questions in verified bank','▤')}${stat(subjects.length,'Available subjects','◈')}${stat(3,'Wrong options picked per MCQ','◇')}${stat(s.meta.session_count,'Student sessions created','◎')}</div>
  ${getLast()?`<div class="hint-banner"><span>Have an unfinished or previously completed session in this browser?</span><button class="btn secondary small" data-action="resume">Resume last session</button></div>`:''}
  <div class="section-heading"><div><h2>Create a personalized test</h2><div class="subtitle">Choose the requirements. The selection engine handles the rest.</div></div><span class="tag">STEP 01 / CONFIGURE</span></div>
  <div class="grid-2"><div>${card('Student & exam requirements',`
    <div class="form-row"><div class="field"><label for="student-name">Student name</label><input class="input" id="student-name" autocomplete="name" placeholder="e.g. Alex Kumar" value="${esc(s.studentName)}" maxlength="80"></div><div class="field"><label for="student-code">Student ID / roll number (optional)</label><input class="input" id="student-code" placeholder="e.g. IT-101" value="${esc(s.studentCode)}" maxlength="40"><div class="help">Helps avoid repeating questions across attempts.</div></div></div>
    <div class="option-block"><span class="block-label">Purpose of the exam</span><div class="goal-grid">${goals.map(g=>`<button class="goal ${s.plan.goal===g.id?'selected':''}" data-action="goal" data-value="${esc(g.id)}"><span class="goal-dot"></span><span><div class="goal-name">${esc(g.label)}</div><div class="goal-descr">${esc(g.description)}</div></span></button>`).join('')}</div></div>
    <div class="option-block"><span class="block-label">Subjects to include</span><div class="chips">${subjects.map(x=>`<button class="chip ${s.plan.subjects.includes(x.name)?'selected':''}" data-action="subject" data-value="${esc(x.name)}"><span class="chip-check">${s.plan.subjects.includes(x.name)?'✓':''}</span>${esc(x.name)} <span style="opacity:.55">${x.count}</span></button>`).join('')}</div></div>
    <div class="option-block"><span class="block-label">Question types <span class="small-muted">(none selected = all types)</span></span><div class="chips">${types.map(x=>`<button class="chip ${s.plan.question_types.includes(x.name)?'selected':''}" data-action="type" data-value="${esc(x.name)}"><span class="chip-check">${s.plan.question_types.includes(x.name)?'✓':''}</span>${esc(label(x.name))}</button>`).join('')}</div></div>
    <div class="form-row"><div class="field"><label for="count">Number of questions</label><input type="number" class="input" id="count" min="1" max="40" value="${s.plan.question_count}"></div><div class="field"><label for="duration">Duration (minutes)</label><input type="number" class="input" id="duration" min="1" max="180" value="${s.plan.duration_minutes}"></div></div>
    <div class="info-note"><strong>How selection works:</strong> No MCQs are invented. The system filters approved tags, calculates a suitable difficulty mix, prioritizes broad topic coverage, and avoids repeated questions where possible.</div>`, '', `<button class="btn primary full" data-action="start" ${s.busy?'disabled':''}>${s.busy?'Building your exam…':'Generate unique MCQ paper →'}</button>`)}
  </div><aside class="stack">${card('AI selection blueprint','<div id="blueprint-content" class="loading">Calculating the question mix…</div>','<span class="tag subject">LIVE PREVIEW</span>')}${card('What happens next',`<div class="steps"><div class="step"><div class="step-n">01</div><div><strong>Match the tags</strong><p>Subject, type, topic and difficulty guide retrieval.</p></div></div><div class="step"><div class="step-n">02</div><div><strong>Build an individual paper</strong><p>Fresh question set and different wrong options for each attempt.</p></div></div><div class="step"><div class="step-n">03</div><div><strong>Take the quiz</strong><p>One correct and three incorrect answers in shuffled order.</p></div></div><div class="step"><div class="step-n">04</div><div><strong>Get your result</strong><p>Server-side checking reveals correct answers after submission.</p></div></div></div>`)}
  </aside></div>`;
}
function planMarkup(p){
  const cols = p.difficulty || {};
  const diffMarkup = ['easy','medium','hard'].map(d=>`<div class="bar-group"><div class="bar-label"><span>${label(d)}</span><b>${cols[d]||0} questions</b></div><div class="bar-track"><div class="bar-fill ${d}" style="width:${pct(cols[d]||0,p.question_count)}%"></div></div></div>`).join('');
  return `<div class="plan-summary"><div class="plan-stat"><b>${p.question_count}</b><span>QUESTIONS</span></div><div class="plan-stat"><b>${Object.keys(p.subjects).length}</b><span>SUBJECTS</span></div><div class="plan-stat"><b>${p.eligible_questions}</b><span>IN BANK</span></div></div><div class="small-muted" style="font-weight:800;margin-bottom:14px">PROPOSED DIFFICULTY MIX</div>${diffMarkup}<hr class="divider"><div class="small-muted" style="font-weight:800;margin-bottom:10px">SUBJECT ALLOCATION</div>${Object.entries(p.subjects).map(([k,v])=>`<div class="bar-label" style="margin-bottom:9px"><span>${esc(k)}</span><b>${v}</b></div>`).join('')}<div class="small-muted" style="margin-top:17px">This is an adaptive target. Actual selection depends on available tagged questions.</div>`;
}
let planRequestId=0;
async function refreshBlueprint(){
  if(s.view!=='create' || !s.plan) return;
  const id=++planRequestId;
  const el=document.getElementById('blueprint-content');
  if(!el) return;
  try{
    if(!s.plan.subjects.length) throw Error('Please select at least one subject.');
    const req={...s.plan,student_name:s.studentName.trim()||'Preview Student',student_code:s.studentCode};
    const res=await api('/blueprint','POST',req);
    if(id!==planRequestId||s.view!=='create')return;
    s.blueprint=res;
    const target=document.getElementById('blueprint-content');if(target)target.innerHTML=planMarkup(res);
  }catch(e){
    if(id!==planRequestId||s.view!=='create')return;
    s.blueprint=null;
    const target=document.getElementById('blueprint-content');if(target)target.innerHTML=`<div class="error">${esc(e.message)}</div>`;
  }
}
function renderExam(){
  const session=s.session, questions=session.questions, q=questions[s.index];
  const answered=questions.filter(x=>x.selected_option).length;
  const left=Math.max(0,Math.ceil((new Date(session.ends_at)-Date.now())/1000));
  const clock=`${String(Math.floor(left/60)).padStart(2,'0')}:${String(left%60).padStart(2,'0')}`;
  return `<div class="exam-top"><div><div class="eyebrow">ACTIVE EXAM SESSION</div><h2>${esc(session.blueprint.goal_label)}</h2><div class="subtitle">${esc(session.student_name)} · ${questions.length} questions · ${esc(session.blueprint.strategy)}</div></div><div class="exam-clock ${left<=60?'urgent':''}" id="countdown">◷ ${clock}</div></div>
  <div class="exam-shell"><div>${card(`Question ${s.index+1} of ${questions.length}`,`
    <div class="tag-row"><span class="tag subject">${esc(q.subject)}</span><span class="tag">${esc(q.topic)}</span><span class="tag ${esc(q.difficulty)}">${esc(label(q.difficulty))}</span><span class="tag">${esc(label(q.question_type))}</span></div>
    <div class="question-text">${esc(q.text)}</div><div class="choices">${q.options.map((o,i)=>`<button data-action="answer" data-option="${esc(o.id)}" class="choice ${q.selected_option===o.id?'active':''}"><span class="choice-letter">${'ABCD'[i]}</span><span>${esc(o.text)}</span></button>`).join('')}</div>
    <div class="btn-row"><button class="btn secondary" data-action="previous" ${s.index===0?'disabled':''}>← Previous</button><button class="btn primary" data-action="next" ${s.index===questions.length-1?'disabled':''}>Next question →</button></div>
  `,`<span class="question-count">${answered} / ${questions.length} answered</span>`,`<div class="small-muted">Answers save automatically. You can change your choice until submission or time expiry.</div>`)}
  </div><aside>${card('Question navigator',`<div class="small-muted">Select a question to jump directly to it.</div><div class="progress-line"><div style="width:${pct(answered,questions.length)}%"></div></div><div class="question-nav">${questions.map((qq,i)=>`<button data-action="goto" data-index="${i}" class="${i===s.index?'current':qq.selected_option?'answered':''}">${i+1}</button>`).join('')}</div><div class="legend"><span><i class="done"></i> Answered</span><span><i class="now"></i> Current</span></div><hr class="divider"><button class="btn primary full" data-action="submit">Submit exam →</button><p class="small-muted">${questions.length-answered} unanswered. Final submission cannot be undone.</p>`)}</aside></div>`;
}
function renderResult(){
  const session=s.session;
  const count=session.questions.length,score=session.score||0;
  const bySubject={};
  (session.review||[]).forEach(x=>{if(!bySubject[x.subject])bySubject[x.subject]={right:0,total:0};bySubject[x.subject].total++;if(x.is_correct)bySubject[x.subject].right++;});
  return `<div class="result-banner"><div class="eyebrow" style="justify-content:center">PAPER SUBMITTED</div><div class="result-circle"><div><b>${pct(score,count)}%</b><span>${score} / ${count} correct</span></div></div><h2>${pct(score,count)>=70?'Excellent work!':pct(score,count)>=40?'Good effort!':'Keep practising!'}</h2><p style="color:#c7d9f6;font-size:13px">${esc(session.student_name)} · Completed ${fmtDate(session.submitted_at)}</p></div>
  <div class="grid-2"><div>${card('Answer review',`<div class="small-muted" style="margin-bottom:15px">Verified correct options are shown only after submission.</div>${(session.review||[]).map((a,i)=>`<div class="review-item"><div class="tag-row" style="margin-bottom:8px"><span class="tag">Q${i+1}</span><span class="tag subject">${esc(a.subject)}</span><span class="tag ${a.is_correct?'easy':'hard'}">${a.is_correct?'✓ Correct':a.selected_text?'✕ Incorrect':'— Unanswered'}</span></div><strong>${esc(a.text)}</strong><p>Your answer: <b>${esc(a.selected_text||'Not answered')}</b></p><p>Correct answer: <b style="color:#16875d">${esc(a.correct_text)}</b></p></div>`).join('')}`)}</div>
  <aside class="stack">${card('Performance by subject',Object.entries(bySubject).map(([name,r])=>`<div class="bar-group"><div class="bar-label"><span>${esc(name)}</span><b>${r.right}/${r.total}</b></div><div class="bar-track"><div class="bar-fill medium" style="width:${pct(r.right,r.total)}%"></div></div></div>`).join(''))}${card('Next steps',`<p class="small-muted" style="margin:0 0 16px">Each attempt creates a newly shuffled set from the database. Use the same student ID to prioritize unseen questions.</p><button class="btn primary full" data-action="new">Create another exam</button>`)}</aside></div>`;
}
function renderAdmin(){
  if(!s.adminReady) return `<div class="admin-lock">${card('Unlock the question bank',`<div class="small-muted" style="margin-bottom:18px">Admin access is required to view correct answers or modify stored questions. Enter the shared demo key from the setup instructions.</div><form id="admin-login"><div class="field"><label for="admin-key">Admin key</label><input class="input" id="admin-key" type="password" autocomplete="off" placeholder="Enter admin key" required></div><button class="btn primary full" style="margin-top:17px" type="submit">Unlock admin tools →</button></form><div class="info-note" style="margin-top:15px">For hosting, set <code>SECUREPAPER_ADMIN_KEY</code> to a private value. The bundled demo key is not production authentication.</div>`)}</div>`;
  return `<div class="section-heading"><div><h2>Question bank</h2><div class="subtitle">Manage tagged MCQs and separate verified correct/incorrect option pools.</div></div><button class="btn ghost small" data-action="logout">Lock admin</button></div>
  <div class="stat-grid">${stat(s.meta.question_count,'Active MCQs','▤')}${stat(s.meta.subjects.length,'Subjects','◈')}${stat(s.bank.reduce((n,q)=>n+q.options.filter(o=>!o.is_correct).length,0),'Stored wrong answers','◇')}${stat(s.meta.session_count,'Exam sessions','◎')}</div>
  <div class="two-pane"><div class="stack">${card('Add a tagged MCQ',`<form id="add-question">
    <div class="form-row"><div class="field"><label>Subject / category</label><input name="subject" class="input" required placeholder="Electrical" list="subject-values"><datalist id="subject-values">${s.meta.subjects.map(x=>`<option value="${esc(x.name)}">`).join('')}</datalist></div><div class="field"><label>Topic / chapter</label><input name="topic" class="input" required placeholder="e.g. Circuit laws"></div></div>
    <div class="form-row"><div class="field"><label>Difficulty</label><select class="input" name="difficulty"><option value="easy">Easy</option><option value="medium" selected>Medium</option><option value="hard">Hard</option></select></div><div class="field"><label>Question type</label><select class="input" name="question_type">${['conceptual','numerical','application','reasoning'].map(t=>`<option value="${t}">${label(t)}</option>`).join('')}</select></div></div>
    <div class="field" style="margin-bottom:15px"><label>Question</label><textarea name="text" class="input" placeholder="Enter the MCQ stem…" required minlength="6"></textarea></div>
    <div class="field" style="margin-bottom:15px"><label>Correct option (exactly one)</label><input name="correct_option" class="input" required placeholder="Verified correct answer"></div>
    <div class="field" style="margin-bottom:15px"><label>Incorrect options (3 or more, one per line)</label><textarea name="wrong_options" class="input" rows="6" required placeholder="Wrong option A&#10;Wrong option B&#10;Wrong option C&#10;Wrong option D&#10;Wrong option E"></textarea><div class="help">The engine selects any three distractors randomly for each exam.</div></div>
    <button class="btn primary full" type="submit">+ Save question to database</button></form>`)}
    ${card('Bulk import (optional)',`<p class="small-muted" style="margin:0 0 15px">Upload a JSON array using the same fields as the add-question form. All rows are validated and imported together. A sample is included in the ZIP.</p><input id="import-file" type="file" class="input" accept=".json,application/json">`)}
  </div><div>${card(`Stored questions (${s.bank.length})`,`<input class="input" id="bank-filter" value="${esc(s.bankFilter)}" placeholder="Search questions, subjects or topics…"><div id="bank-list" style="margin-top:13px">${bankList()}</div>`,`<span class="tag">ADMIN VIEW</span>`)}</div></div>`;
}
function bankList(){
  const q=s.bank.filter(x=>[x.subject,x.topic,x.difficulty,x.text].some(v=>v.toLowerCase().includes(s.bankFilter.toLowerCase())));
  if(!q.length)return '<div class="empty">No questions match this filter.</div>';
  return `<div style="max-height:660px;overflow:auto">${q.map(x=>`<div class="review-item ${x.active?'':'archived'}"><div class="tag-row" style="margin-bottom:9px"><span class="tag subject">${esc(x.subject)}</span><span class="tag ${esc(x.difficulty)}">${label(x.difficulty)}</span><span class="tag">${label(x.question_type)}</span><span class="tag">${esc(x.topic)}</span></div><strong>${esc(x.text)}</strong><details><summary class="small-muted">See correct and ${x.options.length-1} wrong options</summary><div class="small-muted" style="margin:10px 0">${x.options.map(o=>`<div style="padding:4px 0" class="${o.is_correct?'correct':'incorrect'}">${o.is_correct?'✓ Correct:':'○ Wrong:'} ${esc(o.text)}</div>`).join('')}</div></details><div class="btn-row" style="margin-top:10px"><span class="small-muted">${x.active?'Active in selection':'Archived / excluded'}</span><button class="btn small ${x.active?'danger':'secondary'}" data-action="toggle" data-id="${esc(x.id)}" data-active="${x.active?'false':'true'}">${x.active?'Archive':'Restore'}</button></div></div>`).join('')}</div>`;
}
function renderSessions(){
  if(!s.adminReady) return `<div class="admin-lock">${card('Session history',`<div class="small-muted">Session history includes student identifiers and is available only to administrators.</div><button class="btn primary full" style="margin-top:16px" data-action="nav" data-target="admin">Unlock admin dashboard →</button>`)}</div>`;
  return `<div class="section-heading"><div><h2>Student sessions</h2><div class="subtitle">Demo history, completion and score summary (newest first).</div></div><button class="btn secondary small" data-action="refresh-sessions">↻ Refresh</button></div>${card('Recent sessions',s.sessions.length?`<div class="table-wrap"><table class="table"><thead><tr><th>Student</th><th>Exam goal</th><th>Questions</th><th>Score</th><th>Status</th><th>Started</th></tr></thead><tbody>${s.sessions.map(x=>`<tr><td><b>${esc(x.student_name)}</b><div class="small-muted">${esc(x.student_code||shortId(x.id))}</div></td><td>${esc(label(x.exam_goal))}</td><td>${x.question_count}</td><td>${x.score===null?'—':`${x.score}/${x.question_count}`}</td><td><span class="tag ${x.status==='submitted'?'easy':'medium'}">${esc(x.status)}</span></td><td>${esc(fmtDate(x.created_at))}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">No exams have been started yet.</div>')}</div>`;
}
function renderAbout(){
  return `<div class="section-heading"><div><h2>How SecurePaper works</h2><div class="subtitle">A complete MCQ demonstration — without question generation or external model costs.</div></div></div><div class="two-pane">${card('Database → exam → result',`<div class="steps"><div class="step"><div class="step-n">01</div><div><strong>Verified tagged database</strong><p>SQLite stores question text, subject, topic, difficulty, question type, one marked correct answer and five or more marked wrong answers in separate rows.</p></div></div><div class="step"><div class="step-n">02</div><div><strong>Automatic blueprint</strong><p>A constraint-aware selection algorithm chooses subject counts and difficulty proportions based on practice, class test, competitive or revision intent.</p></div></div><div class="step"><div class="step-n">03</div><div><strong>Unique student paper</strong><p>Questions are drawn from the available bank with random variation, exposure penalties and preference for unseen items. Three random wrong answers join the stored correct one, then all four are shuffled.</p></div></div><div class="step"><div class="step-n">04</div><div><strong>Secure server-side grading</strong><p>Student API responses never include the correct-option marker before submission. Submitted or expired sessions are graded against the stored database answers.</p></div></div></div>`)}
  ${card('Demo boundaries',`<div class="info-note"><strong>Selection, not generation.</strong> This is a deterministic/rule-based intelligent selector with randomness; it does not call an LLM and does not create new question content.</div><p class="small-muted">This version intentionally omits advanced report features such as AI question generation, encrypted paper custody, trustee threshold release, proctoring and high-stakes anti-cheating controls.</p><p class="small-muted">Admin key and bearer-style session URLs are adequate for demonstrating workflows, not for protecting real examinations. Add user accounts, authorization policies, HTTPS, monitoring and a production database before real-world use.</p><hr class="divider"><div class="tag-row"><span class="tag">Python FastAPI</span><span class="tag">SQLite</span><span class="tag">Vanilla JS</span><span class="tag">Docker-ready</span><span class="tag">No CDN</span></div>`)}
  </div>`;
}

async function loadAdmin(){
  if(!s.adminKey) return;
  try{
    const [bank,sessions]=await Promise.all([api('/admin/questions?limit=1000','GET',null,true),api('/admin/sessions','GET',null,true)]);
    s.bank=bank;s.sessions=sessions;s.adminReady=true;
  }catch(e){s.adminReady=false;throw e;}
}
async function loadMeta(){s.meta=await api('/meta');if(!s.plan){s.plan={goal:'class_test',subjects:s.meta.subjects.map(x=>x.name),question_types:[],question_count:10,duration_minutes:20};}}
async function refreshSession(){
  if(!s.session)return;
  const session=await api('/sessions/'+encodeURIComponent(s.session.id));
  s.session=session;
  if(session.status==='submitted') s.view='result';
  render();
}
async function startExam(){
  if(!s.studentName.trim()||s.studentName.trim().length<2) {setMsg('Enter a student name with at least two characters.','error');return;}
  if(!s.plan.subjects.length){setMsg('Choose at least one subject.','error');return;}
  s.busy=true;s.error='';s.notice='';render();
  try{
    const data=await api('/sessions','POST',{...s.plan,student_name:s.studentName.trim(),student_code:s.studentCode.trim()});
    s.session=data;s.index=0;s.view='exam';setLast(data.id);s.error='';
  }catch(e){s.error=e.message;}
  finally{s.busy=false;render();window.scrollTo({top:0,behavior:'smooth'});}
}
async function saveSelectedOption(id){
  const q=s.session.questions[s.index];
  if(!q.options.some(o=>o.id===id))return;
  q.selected_option=id;
  const sid=s.session.id;
  const qid=q.id;
  s.pendingSave=s.pendingSave.catch(()=>{}).then(()=>api('/sessions/'+encodeURIComponent(sid)+'/answer','POST',{question_id:qid,option_id:id}));
  s.pendingSave.catch(async e=>{s.error=e.message;try{await refreshSession();}catch{}render();});
  render();
}
async function submitExam(){
  const open=s.session.questions.filter(q=>!q.selected_option).length;
  if(!window.confirm(open?`${open} questions are unanswered. Submit the exam anyway?`:'Submit your answers? You cannot edit after submission.'))return;
  s.busy=true;
  try{await s.pendingSave; s.session=await api('/sessions/'+encodeURIComponent(s.session.id)+'/submit','POST',{});s.view='result';s.error='';await loadMeta();}
  catch(e){s.error=e.message;}
  finally{s.busy=false;render();window.scrollTo({top:0,behavior:'smooth'});}
}
async function goView(target){
  if(s.view==='exam' && target!=='exam' && !window.confirm('Leave this page? Your saved answers remain in the current session.')) return;
  s.view=target;s.error='';s.notice='';
  if((target==='admin'||target==='sessions') && s.adminReady){try{await loadAdmin();}catch(e){s.error=e.message;}}
  render();window.scrollTo({top:0,behavior:'smooth'});
}
root.addEventListener('click',async e=>{
  if(e.target.closest('[data-home]')){await goView('create');return;}
  const b=e.target.closest('[data-action]');if(!b||b.disabled)return;
  const a=b.dataset.action;
  try{
    if(a==='nav')return goView(b.dataset.target);
    if(a==='goal'){s.plan.goal=b.dataset.value;return render();}
    if(a==='subject'){const v=b.dataset.value;s.plan.subjects=s.plan.subjects.includes(v)?s.plan.subjects.filter(x=>x!==v):[...s.plan.subjects,v];return render();}
    if(a==='type'){const v=b.dataset.value;s.plan.question_types=s.plan.question_types.includes(v)?s.plan.question_types.filter(x=>x!==v):[...s.plan.question_types,v];return render();}
    if(a==='start')return await startExam();
    if(a==='resume'){
      const id=getLast();if(!id)return; s.session=await api('/sessions/'+encodeURIComponent(id));s.view=s.session.status==='submitted'?'result':'exam';s.index=0;s.error='';return render();
    }
    if(a==='new'){s.view='create';s.session=null;s.index=0;s.error='';return render();}
    if(a==='answer')return await saveSelectedOption(b.dataset.option);
    if(a==='previous'){s.index=Math.max(0,s.index-1);return render();}
    if(a==='next'){s.index=Math.min(s.session.questions.length-1,s.index+1);return render();}
    if(a==='goto'){s.index=Number(b.dataset.index);return render();}
    if(a==='submit')return await submitExam();
    if(a==='logout'){s.adminKey='';s.adminReady=false;s.bank=[];s.sessions=[];sessionStorage.removeItem('sp_admin_key');return render();}
    if(a==='refresh-sessions'){await loadAdmin();return render();}
    if(a==='toggle'){
      const active=b.dataset.active==='true';
      await api('/admin/questions/'+encodeURIComponent(b.dataset.id)+'?active='+active,'PATCH',null,true);
      await Promise.all([loadMeta(),loadAdmin()]);s.notice=active?'Question restored.':'Question archived.';return render();
    }
  }catch(err){setMsg(err.message,'error');}
});
root.addEventListener('input',e=>{
  const t=e.target;
  if(t.id==='student-name')s.studentName=t.value;
  if(t.id==='student-code')s.studentCode=t.value;
  if(t.id==='bank-filter'){
    s.bankFilter=t.value;
    const target=document.getElementById('bank-list');if(target)target.innerHTML=bankList();
  }
});
root.addEventListener('change',async e=>{
  const t=e.target;
  if(t.id==='count'){s.plan.question_count=Number(t.value);refreshBlueprint();}
  if(t.id==='duration'){s.plan.duration_minutes=Number(t.value);refreshBlueprint();}
  if(t.id==='import-file'){
    if(!t.files?.length)return;
    try{
      const qs=JSON.parse(await t.files[0].text());
      if(!Array.isArray(qs))throw Error('The import file must be a JSON array.');
      const result=await api('/admin/questions/import','POST',qs,true);
      await Promise.all([loadMeta(),loadAdmin()]);setMsg(`Imported ${result.imported} questions successfully.`);
    }catch(err){setMsg(err.message,'error');}
  }
});
root.addEventListener('submit',async e=>{
  const f=e.target;
  if(f.id==='admin-login'){
    e.preventDefault();
    s.adminKey=f.querySelector('#admin-key').value;
    try{await loadAdmin();sessionStorage.setItem('sp_admin_key',s.adminKey);s.error='';render();}
    catch(err){setMsg(err.message,'error');}
  }
  if(f.id==='add-question'){
    e.preventDefault();
    const form=new FormData(f);
    const q={
      subject:String(form.get('subject')||'').trim(),topic:String(form.get('topic')||'').trim(),
      difficulty:form.get('difficulty'),question_type:form.get('question_type'),text:String(form.get('text')||'').trim(),
      correct_option:String(form.get('correct_option')||'').trim(),
      wrong_options:String(form.get('wrong_options')||'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean),
    };
    try{
      await api('/admin/questions','POST',q,true);
      await Promise.all([loadMeta(),loadAdmin()]);setMsg('Question added to the tagged database.');
    }catch(err){setMsg(err.message,'error');}
  }
});
let checkingExpiry=false;
setInterval(async()=>{
  if(s.view!=='exam'||!s.session||s.session.status!=='active')return;
  const remain=Math.max(0,Math.ceil((new Date(s.session.ends_at)-Date.now())/1000));
  const element=document.getElementById('countdown');
  if(element){element.textContent='◷ '+String(Math.floor(remain/60)).padStart(2,'0')+':'+String(remain%60).padStart(2,'0');element.classList.toggle('urgent',remain<=60);}
  if(remain===0&&!checkingExpiry){
    checkingExpiry=true;
    try{await s.pendingSave.catch(()=>{});await refreshSession();}
    catch(err){s.error=err.message;render();}
    finally{checkingExpiry=false;}
  }
},1000);
(async function init(){
  try{await loadMeta();if(s.adminKey){try{await loadAdmin();}catch{}}
    render();}
  catch(err){root.innerHTML=shell(`<div class="error">Startup failed: ${esc(err.message)}</div><p>Run the FastAPI server as described in README.md.</p>`);}
})();
