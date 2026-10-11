/* ============================================================
   影视世界观决策测评 — 前端逻辑
   ============================================================ */

/* ============================================================
   1. API 配置
   ============================================================ */
const API = {
  BASE: '', // 保持空字符串不变，因为前后端现在同端口
  WORLDS:    '/api/worlds',
  SELECTION: '/api/selection',
  QUIZ:      (stage) => `/api/quiz/${stage}`,
  RESULT:    '/api/result',
  RESET:     '/api/reset',
};

/* ============================================================
   2. 图片路径映射
   ============================================================ */
function getQuizBgImage(movieSlug, questionNumber) {
  if (!movieSlug) return '';
  return `images/${movieSlug}-${questionNumber}.jpg`;
}

/* ============================================================
   3. 工具函数
   ============================================================ */

/** 统一 fetch 封装 */
async function apiFetch(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok || !json.ok) {
    throw Object.assign(new Error(json.message || `HTTP ${res.status}`), { status: res.status, data: json });
  }
  return json;
}

/** 显示错误 */
function showError(msg, recoverable = true) {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="error-screen">
      <p class="error-msg">${escHtml(msg)}</p>
      ${recoverable ? '<button class="btn-primary" id="err-reset-btn">重新开始</button>' : ''}
    </div>`;
  document.getElementById('err-reset-btn')?.addEventListener('click', handleReset);
}

/** 显示加载 */
function showLoading(text = '加载中…') {
  document.getElementById('app').innerHTML =
    `<div class="loading"><span>${escHtml(text)}</span></div>`;
}

/** HTML 转义 */
function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** 应用主题 */
function applyTheme(style) {
  if (style?.theme) document.body.dataset.theme = style.theme;
  if (style?.movie_slug) document.body.dataset.movie = style.movie_slug;
}

/* ============================================================
   4. 重置
   ============================================================ */
async function handleReset() {
  showLoading('重置中…');
  try {
    await apiFetch(API.RESET, { method: 'POST' });
    await showWorldSelect();
  } catch (e) {
    showError('重置失败：' + e.message);
  }
}

/* ============================================================
   5. 选片页
   ============================================================ */
async function showWorldSelect() {
  showLoading('加载片单…');
  try {
    const data = await apiFetch(API.WORLDS);
    applyTheme(data.style);

    const groupsHtml = data.worlds.map(world => `
      <div class="world-section">
        <h2>${escHtml(world.name)}</h2>
        <p class="world-desc">${escHtml(world.description)}</p>
        <div class="movie-list">
          ${world.movies.map(m => `
            <button class="movie-card" data-slug="${escHtml(m.slug)}">
              <div class="movie-title">${escHtml(m.name)}</div>
            </button>
          `).join('')}
        </div>
      </div>
    `).join('');

    document.getElementById('app').innerHTML = `
      <div class="world-select">
        <h1>选择你的世界</h1>
        <p class="subtitle">选择一部影片，进入其世界观进行决策测评</p>
        <div class="world-list">${groupsHtml}</div>
      </div>`;

    document.querySelectorAll('.movie-card').forEach(btn => {
      btn.addEventListener('click', () => handleMovieSelect(btn.dataset.slug));
    });
  } catch (e) {
    showError('加载失败：' + e.message);
  }
}


async function handleMovieSelect(slug) {
  showLoading('进入世界…');
  try {
    // 先获取世界观数据，找到这个电影属于哪个 world
    const worldsData = await apiFetch(API.WORLDS);
    let worldSlug = null;
    
    // 遍历所有世界观，找到包含这个电影的那个
    for (const world of worldsData.worlds) {
      if (world.movies.some(m => m.slug === slug)) {
        worldSlug = world.slug;
        break;
      }
    }
    
    if (!worldSlug) {
      throw new Error('找不到对应的世界观');
    }
    
    // 发送正确的参数格式
    await apiFetch(API.SELECTION, {
      method: 'POST',
      body: JSON.stringify({ 
        world: worldSlug,  // 世界观 slug（如 "scifi"）
        movie: slug        // 电影 slug（如 "matrix"）
      }),
    });
    await showQuiz('stage1');
  } catch (e) {
    showError('选择失败：' + e.message);
  }
}


/* ============================================================
   6. 题目页通用框架
   ============================================================ */
async function showQuiz(stage) {
  showLoading('加载题目…');
  try {
    const data = await apiFetch(API.QUIZ(stage));
    applyTheme(data.style);
    
    if (stage === 'stage1') {
      renderStage1(data);
    } else if (stage === 'sandbox1') {
      renderSandbox1(data);
    } else if (stage === 'sandbox2') {
      renderSandbox2(data);
    } else if (stage === 'sandbox3') {
      renderSandbox3(data);
    }
  } catch (e) {
    showError('加载题目失败：' + e.message);
  }
}

/** 题目页框架模板 */
function quizPageTemplate(bgImageUrl, headerHtml, contentHtml) {
  return `
    <div class="quiz-page" style="background-image:url('${bgImageUrl}')">
      <div class="quiz-overlay"></div>
      <div class="quiz-header">${headerHtml}</div>
      <div class="quiz-content">${contentHtml}</div>
    </div>`;
}

/* ============================================================
   7. Stage1 — 三道单选题
   ============================================================ */
function renderStage1(quizData) {
  const questions = quizData.data;
  const movieSlug = quizData.style?.movie_slug;
  const answers = new Map();
  let currentQ = 0;

  function renderQuestion(index) {
    const q = questions[index];
    const bgImage = getQuizBgImage(movieSlug, index + 1);
    
    const optionsHtml = q.options.map(opt => `
      <button class="option-btn" data-oid="${escHtml(opt.id)}">
        <div class="option-text">${escHtml(opt.text)}</div>
        ${opt.detail ? `<div class="option-detail">${escHtml(opt.detail)}</div>` : ''}
      </button>
    `).join('');

    const headerHtml = `
      <h2>${escHtml(q.title)}</h2>
      <span class="quiz-progress">第 ${index + 1} / ${questions.length} 题</span>
    `;

    const contentHtml = `
      <div class="question-container">
        <p class="question-bg">${escHtml(q.background)}</p>
        <div class="options">${optionsHtml}</div>
        <div class="quiz-actions">
          ${index > 0 ? '<button class="btn-secondary" id="prev-btn">上一题</button>' : ''}
          <button class="btn-primary" id="next-btn" disabled>
            ${index < questions.length - 1 ? '下一题' : '提交'}
          </button>
        </div>
      </div>
    `;

    document.getElementById('app').innerHTML = quizPageTemplate(bgImage, headerHtml, contentHtml);

    // 回填已保存答案
    const savedId = answers.get(q.id);
    if (savedId) {
      const btn = document.querySelector(`.option-btn[data-oid="${CSS.escape(savedId)}"]`);
      btn?.classList.add('selected');
      document.getElementById('next-btn').disabled = false;
    }

    // 选项点击
    document.querySelectorAll('.option-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.option-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        answers.set(q.id, btn.dataset.oid);
        document.getElementById('next-btn').disabled = false;
      });
    });

    // 上一题
    document.getElementById('prev-btn')?.addEventListener('click', () => {
      currentQ--;
      renderQuestion(currentQ);
    });

    // 下一题/提交
    document.getElementById('next-btn').addEventListener('click', async () => {
      if (index < questions.length - 1) {
        currentQ++;
        renderQuestion(currentQ);
      } else {
        await submitStage1(answers);
      }
    });
  }

  async function submitStage1(answers) {
    document.getElementById('next-btn').disabled = true;
    const answersObj = Object.fromEntries(answers);
    try {
      const res = await apiFetch(API.QUIZ('stage1'), {
        method: 'POST',
        body: JSON.stringify({ answers: answersObj }),
      });
      if (res.next === '/api/result') {
        await showResult();
      } else {
        const nextStage = res.next.split('/').pop();
        await showQuiz(nextStage);
      }
    } catch (e) {
      showError('提交失败：' + e.message);
    }
  }

  renderQuestion(0);
}

/* ============================================================
   8. Sandbox1 — 资源分配（4个滑块总和100）
   ============================================================ */
function renderSandbox1(quizData) {
  const d = quizData.data;
  const movieSlug = quizData.style?.movie_slug;
  const bgImage = getQuizBgImage(movieSlug, 4);

  const itemLabels = (d.items || []).map(item =>
    typeof item === 'string' ? item : (item.text || item.name || item.label || String(item))
  );


  const values = quizData.saved_answer || [25, 25, 25, 25];
  
  const slidersHtml = itemLabels.map((label, i) => `
    <div class="allocation-item">
      <span class="allocation-label">${escHtml(label)}</span>
      <div class="slider-group">
        <input type="range" class="allocation-slider" id="slider-${i}" 
          min="0" max="100" value="${values[i]}" />
        <span class="allocation-value" id="value-${i}">${values[i]}</span>
      </div>
    </div>
  `).join('');

  const headerHtml = `
    <h2>${escHtml(d.theme)}</h2>
    <span class="quiz-progress">资源分配</span>
  `;

  const contentHtml = `
    <div class="sandbox-container">
      <p class="sandbox-scene">${escHtml(d.scene)}</p>
      <div class="allocation-box">
        ${slidersHtml}
        <div class="allocation-total">
          总计：<span id="total-value">100</span> / ${d.total}
        </div>
      </div>
      <button class="btn-primary" id="submit-btn">提交</button>
    </div>
  `;

  document.getElementById('app').innerHTML = quizPageTemplate(bgImage, headerHtml, contentHtml);

  const sliders = itemLabels.map((_, i) => document.getElementById(`slider-${i}`));
  const valueSpans = itemLabels.map((_, i) => document.getElementById(`value-${i}`));
  const totalSpan = document.getElementById('total-value');
  const submitBtn = document.getElementById('submit-btn');

  function updateTotal() {
    const total = sliders.reduce((sum, s) => sum + parseInt(s.value), 0);
    totalSpan.textContent = total;
    submitBtn.disabled = total !== d.total;
    if (total > d.total) {
      totalSpan.style.color = '#ff4757';
    } else if (total < d.total) {
      totalSpan.style.color = '#ffa502';
    } else {
      totalSpan.style.color = 'var(--accent)';
    }
  }

  sliders.forEach((slider, i) => {
    slider.addEventListener('input', () => {
      valueSpans[i].textContent = slider.value;
      updateTotal();
    });
  });

  updateTotal();

  submitBtn.addEventListener('click', async () => {
    submitBtn.disabled = true;
    const answers = sliders.map(s => parseInt(s.value));
    try {
      const res = await apiFetch(API.QUIZ('sandbox1'), {
        method: 'POST',
        body: JSON.stringify({ answers }),
      });
      if (res.next === '/api/result') {
        await showResult();
      } else {
        const nextStage = res.next.split('/').pop();
        await showQuiz(nextStage);
      }
    } catch (e) {
      showError('提交失败：' + e.message);
    }
  });
}

/* ============================================================
   9. Sandbox2 — 博弈单选
   ============================================================ */
function renderSandbox2(quizData) {
  const d = quizData.data;
  const movieSlug = quizData.style?.movie_slug;
  const bgImage = getQuizBgImage(movieSlug, 5);

  const optionsHtml = d.options.map(opt => `
    <button class="option-btn" data-oid="${escHtml(opt.id)}">
      <div class="option-text">${escHtml(opt.text)}</div>
      ${opt.detail ? `<div class="option-detail">${escHtml(opt.detail)}</div>` : ''}
    </button>
  `).join('');

  const headerHtml = `
    <h2>${escHtml(d.theme)}</h2>
    <span class="quiz-progress">博弈决策</span>
  `;

  const contentHtml = `
    <div class="sandbox-container">
      <p class="sandbox-scene">${escHtml(d.scene)}</p>
      <div class="options">${optionsHtml}</div>
      <button class="btn-primary" id="submit-btn" disabled>提交</button>
    </div>
  `;

  document.getElementById('app').innerHTML = quizPageTemplate(bgImage, headerHtml, contentHtml);

  let selectedId = quizData.saved_answer || null;
  const submitBtn = document.getElementById('submit-btn');

  if (selectedId) {
    const btn = document.querySelector(`.option-btn[data-oid="${CSS.escape(selectedId)}"]`);
    btn?.classList.add('selected');
    submitBtn.disabled = false;
  }

  document.querySelectorAll('.option-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.option-btn').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      selectedId = btn.dataset.oid;
      submitBtn.disabled = false;
    });
  });

  submitBtn.addEventListener('click', async () => {
    submitBtn.disabled = true;
    try {
      const res = await apiFetch(API.QUIZ('sandbox2'), {
        method: 'POST',
        body: JSON.stringify({ answers: selectedId }),
      });
      if (res.next === '/api/result') {
        await showResult();
      } else {
        const nextStage = res.next.split('/').pop();
        await showQuiz(nextStage);
      }
    } catch (e) {
      showError('提交失败：' + e.message);
    }
  });
}

/* ============================================================
   10. Sandbox3 — 多选（选N个）
   ============================================================ */
function renderSandbox3(quizData) {
  const d = quizData.data;
  const movieSlug = quizData.style?.movie_slug;
  const bgImage = getQuizBgImage(movieSlug, 6);

  const optionsHtml = d.options.map(opt => `
    <button class="option-btn multi" data-oid="${escHtml(opt.id)}">
      <div class="option-text">${escHtml(opt.text)}</div>
      ${opt.detail ? `<div class="option-detail">${escHtml(opt.detail)}</div>` : ''}
    </button>
  `).join('');

  const headerHtml = `
    <h2>${escHtml(d.theme)}</h2>
    <span class="quiz-progress">信息筛选（选 ${d.select_count} 个）</span>
  `;

  const contentHtml = `
    <div class="sandbox-container">
      <p class="sandbox-scene">${escHtml(d.background)}</p>
      ${d.instruction ? `<p class="sandbox-instruction">${escHtml(d.instruction)}</p>` : ''}
      <div class="options">${optionsHtml}</div>
      <button class="btn-primary" id="submit-btn" disabled>提交</button>
    </div>
  `;

  document.getElementById('app').innerHTML = quizPageTemplate(bgImage, headerHtml, contentHtml);

  const selected = new Set(quizData.saved_answer || []);
  const submitBtn = document.getElementById('submit-btn');

  if (selected.size > 0) {
    selected.forEach(oid => {
      const btn = document.querySelector(`.option-btn[data-oid="${CSS.escape(oid)}"]`);
      btn?.classList.add('selected');
    });
    submitBtn.disabled = selected.size !== d.select_count;
  }

  document.querySelectorAll('.option-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const oid = btn.dataset.oid;
      if (selected.has(oid)) {
        selected.delete(oid);
        btn.classList.remove('selected');
      } else {
        if (selected.size < d.select_count) {
          selected.add(oid);
          btn.classList.add('selected');
        }
      }
      submitBtn.disabled = selected.size !== d.select_count;
    });
  });

  submitBtn.addEventListener('click', async () => {
    submitBtn.disabled = true;
    try {
      const res = await apiFetch(API.QUIZ('sandbox3'), {
        method: 'POST',
        body: JSON.stringify({ answers: Array.from(selected) }),
      });
      await showResult();
    } catch (e) {
      showError('提交失败：' + e.message);
    }
  });
}

/* ============================================================
   11. 结果页
   ============================================================ */
/* ============================================================
   11. 结果页
   ============================================================ */
async function showResult() {
  showLoading('生成结果…');
  try {
    const data = await apiFetch(API.RESULT);
    applyTheme(data.style);

    const dimensionsHtml = data.dimensions.map((dimension, i) => {
      const score = data.score_list[i];
      return `
        <div class="dimension-item">
         <span class="dimension-name">${escHtml(dimension)}</span>
         <div class="dimension-bar">
           <div class="dimension-fill" style="width:${score}%"></div>
         </div>
         <span class="dimension-score">${score}</span>
        </div>
       `;
    }).join('');


    document.getElementById('app').innerHTML = `
      <div class="result-page">
        <div class="result-container">
          <h1 class="result-title">你的决策人格分析</h1>
          
          <div class="result-section">
            <h2>雷达图</h2>
            <img src="${escHtml(data.radar_url)}" alt="雷达图" class="radar-img" />
          </div>

          <div class="result-section">
            <h2>维度分数</h2>
            <div class="dimensions">${dimensionsHtml}</div>
          </div>

          <div class="result-section">
            <h2>角色匹配与性格分析</h2>
            <pre class="analysis-text">${escHtml(data.analysis || '分析数据加载中...')}</pre>
          </div>

          <button class="btn-primary" id="restart-btn">再测一次</button>
        </div>
      </div>
    `;

    document.getElementById('restart-btn').addEventListener('click', handleReset);
  } catch (e) {
    showError('加载结果失败：' + e.message);
  }
}


/* ============================================================
   12. 初始化
   ============================================================ */
(async function init() {
  try {
    await showWorldSelect();
  } catch (e) {
    showError('初始化失败：' + e.message, false);
  }
})();
