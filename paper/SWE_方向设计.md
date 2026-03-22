# IntentDrift × SWE Agent：聚焦方向设计

## 一、竞争格局分析

当前 SWE agent 基准的演化路线：

| 基准 | 焦点 | 局限 |
|------|------|------|
| [SWE-bench](https://github.com/SWE-bench/SWE-bench) (ICLR 2024) | 单 issue → 单 patch | 静态、单轮、无用户交互 |
| [SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/) | 500 个人工验证的高质量子集 | 同上 |
| [SWE-agent](https://github.com/SWE-agent/SWE-agent) (NeurIPS 2024) | Agent-Computer Interface 设计 | 仍是单 issue 范式 |
| [SWE-smith](https://github.com/SWE-bench/SWE-smith) (NeurIPS 2025 D&B Spotlight) | 大规模训练数据合成 | 关注训练而非评估 |
| [SWE-EVO](https://arxiv.org/abs/2512.18470) (2025) | 跨版本长期演化，48 个任务 | 无用户交互，需求来自 release notes |
| [SWE-CI](https://arxiv.org/abs/2603.03823) (2026) | CI 循环持续维护，100 个任务 | 需求由 Architect agent 自动生成，非人类用户 |
| [SWE-bench Live](https://github.com/microsoft/SWE-bench-Live) (NeurIPS 2025 D&B) | 防数据污染的持续更新 | 仍是单 issue 范式 |

### 关键空白

**所有这些基准都假设需求/issue 是一次性给定的。** 没有一个建模真实开发场景中最常见的情况：

> 用户（产品经理/同事/自己）在 agent 执行过程中**改变、细化、追加或回溯需求**。

这正是我们的切入点。

---

## 二、IntentDrift-SWE 的定位

### 一句话定位

> **IntentDrift-SWE**: 评估 SWE agent 在**用户需求动态演化**下的表现——当用户在代码修改过程中细化需求、追加约束、改变方向或回溯决定时，agent 能否正确适应？

### 与已有工作的差异

| 维度 | SWE-bench 系列 | SWE-EVO / SWE-CI | **IntentDrift-SWE** |
|------|---------------|-------------------|---------------------|
| 需求来源 | GitHub issue（静态） | release notes / 自动生成 | **人类用户动态交互** |
| 需求变化 | 无 | 跨版本演化（非实时） | **对话中实时漂移** |
| 交互模式 | 单轮（给 issue → 出 patch） | 多轮但自动化 | **人-agent 多轮对话** |
| 评估什么 | 最终 patch 正确性 | 多版本演化能力 | **漂移检测 + 适应 + 上下文保留** |

### 为什么这个空白重要？

真实的 SWE agent 使用场景（如 Claude Code、Cursor、Devin）中，用户几乎从不一次性给出完整需求：

- "帮我修这个 bug" → 调查后发现 → "其实问题在另一个文件" → **T1 渐进细化**
- 正在重构一个函数 → "等一下，先帮我看另一个 PR 的 review" → **T2 主题转移**
- "加一个缓存层" → agent 开始实现 → "哦对了，必须线程安全" → **T3 约束追加**
- "让它更快，但不要改公开 API" → 根本上矛盾 → **T4 目标矛盾**
- 用户要求添加 feature → 暗示需要测试和文档 → **T5 隐性需求**
- "用方案 A 实现" → 做到一半 → "算了，回到之前那个方案 B" → **T6 意图回溯**

---

## 三、具体设计方案

### 3.1 环境设计

```
IntentDrift-SWE/
├── repos/                        # 精选的 Python 开源仓库（5-8 个）
│   ├── flask/                    # Web 框架
│   ├── requests/                 # HTTP 库
│   ├── pandas/                   # 数据处理
│   ├── fastapi/                  # API 框架
│   └── ...
├── environments/                 # Docker 化执行环境
│   ├── flask_env/
│   │   ├── Dockerfile
│   │   ├── repo_snapshot/        # 仓库特定 commit 的快照
│   │   └── test_suite/           # 测试用例
├── tasks/                        # 漂移任务定义
│   ├── T1_refinement/
│   ├── T3_constraint/
│   ├── T6_backtracking/
│   └── compound/
├── user_simulator/               # 环境耦合的用户模拟器
│   └── drift_controller.py
└── evaluation/
    └── state_comparator.py       # 测试通过 + 代码状态比较
```

### 3.2 工具集（真实可执行）

直接复用 SWE-agent 风格的工具，不需要自己造：

| 工具 | 说明 |
|------|------|
| `read_file(path, start, end)` | 读文件 |
| `edit_file(path, old, new)` | 编辑文件 |
| `search_code(pattern, path)` | 搜索代码 |
| `run_tests(test_path)` | 运行测试 |
| `bash(command)` | 执行 shell 命令 |
| `git_diff()` | 查看当前修改 |
| `git_log()` | 查看提交历史 |
| `find_files(pattern)` | 查找文件 |
| `lint(path)` | 代码检查 |

### 3.3 任务设计（核心创新）

每个任务 = 初始需求 + 漂移蓝图 + 期望测试终态

**示例任务（T3: 约束追加）**：

```yaml
task_id: "T3-flask-001"
repo: "flask"
repo_commit: "abc123"
drift_type: "T3_constraint_addition"

initial_request: |
  Add rate limiting middleware to Flask that limits
  each IP to 100 requests per minute. Return 429
  when exceeded.

# Agent 开始实现...可能已经写了部分代码

drift_event:
  trigger_condition: "agent has created/modified at least 1 file"
  turn: ~4-6  # 在 agent 开始实现后触发
  user_message: |
    Oh wait, I forgot to mention — this needs to work
    with our Redis backend for distributed rate limiting
    across multiple workers. In-memory won't work in prod.

  constraint_added: "must use Redis backend"
  invalidates_prior_work: true  # agent 可能已实现了 in-memory 版本

expected_end_state:
  tests_must_pass:
    - "tests/test_rate_limit.py::test_basic_rate_limit"
    - "tests/test_rate_limit.py::test_429_response"
    - "tests/test_rate_limit.py::test_redis_backend"
    - "tests/test_rate_limit.py::test_distributed_workers"
  tests_must_not_regress:
    - "tests/"  # 现有测试不能被破坏
  code_constraints:
    - "import redis"  # 代码中必须使用 redis
    - "!in_memory_store"  # 不能用纯内存实现
```

**示例任务（T6: 意图回溯）**：

```yaml
task_id: "T6-requests-001"
repo: "requests"
repo_commit: "def456"
drift_type: "T6_intent_backtracking"

initial_request: |
  Implement retry logic for failed HTTP requests.
  Use exponential backoff with jitter.

# Agent 开始用 exponential backoff 实现

drift_event:
  trigger_condition: "agent has implemented retry logic"
  turn: ~5-7
  user_message: |
    Actually, I just checked and the team decided we should
    use the urllib3 Retry adapter instead of rolling our own.
    Can you undo what you did and use urllib3's built-in retry?

  revert_to: "use urllib3.util.retry.Retry instead of custom impl"
  requires_rollback: true  # agent 需要撤销已实现的代码

expected_end_state:
  tests_must_pass:
    - "tests/test_retry.py::test_retry_on_500"
    - "tests/test_retry.py::test_max_retries"
    - "tests/test_retry.py::test_urllib3_adapter"
  code_constraints:
    - "from urllib3.util.retry import Retry"
    - "!exponential_backoff"  # 不应有自定义 backoff 代码残留
```

### 3.4 评估体系（确定性为主）

#### 核心指标：pass^k（与 τ-bench 对齐）

```
pass^k = P(至少 1 次成功 in k 次独立运行)
```

对每个任务运行 k=4 次，报告 pass^1 和 pass^4。

#### 终态评估（确定性）

```python
def evaluate(task, agent_workspace):
    results = {}

    # 1. 必须通过的测试
    for test in task.tests_must_pass:
        results['test_pass'] = run_pytest(test, workspace)

    # 2. 不能回归的测试
    for test in task.tests_must_not_regress:
        results['no_regression'] = run_pytest(test, workspace)

    # 3. 代码约束检查
    for constraint in task.code_constraints:
        results['code_check'] = check_code_constraint(constraint, workspace)

    # 综合: 全部通过 = pass, 否则 = fail
    return all(results.values())
```

#### 漂移过程指标（确定性/半确定性）

| 指标 | 实现 | 确定性 |
|------|------|--------|
| **DDL** (漂移检测延迟) | 漂移消息后，agent 第一次修改与新需求相关文件的轮数 | 确定 |
| **CPS** (上下文保留) | 漂移后 agent 是否重复执行了漂移前已完成的不变操作 | 确定 |
| **Rollback Rate** (回滚率，T3/T6 专用) | agent 是否正确撤销了被漂移 invalidate 的代码修改 | 确定（git diff 比较） |
| **PCR** (主动澄清率，T4/T5 专用) | agent 在 tool call 前是否发出了澄清性文本 | 半确定 |

### 3.5 用户模拟器设计

借鉴 τ-Knowledge 的 flow-based 方法（rule-governed + LLM 混合）：

```python
class DriftUserSimulator:
    def __init__(self, task_blueprint):
        self.blueprint = task_blueprint
        self.drift_triggered = False

    def respond(self, agent_message, environment_state):
        # Phase 1: 初始需求阶段
        if not self.drift_triggered:
            if self._should_trigger_drift(environment_state):
                self.drift_triggered = True
                return self.blueprint.drift_event.user_message
            else:
                # Rule-based: 简单确认/催促
                return self._acknowledge(agent_message)

        # Phase 2: 漂移后阶段
        # Rule-based: 根据 agent 是否在处理新需求来响应
        return self._post_drift_response(agent_message, environment_state)

    def _should_trigger_drift(self, env_state):
        """检查触发条件（如 agent 已修改文件）"""
        return self.blueprint.drift_event.trigger_condition.check(env_state)
```

关键设计：
- **触发条件基于环境状态**（如"agent 已修改了至少 1 个文件"），而非固定轮次
- 漂移消息从蓝图中读取（确定性），不由 LLM 实时生成
- 漂移后的用户响应用简单规则（确认/催促/回答问题），仅在复杂情况下调用 LLM

### 3.6 任务规模规划

| 层级 | 数量 | 说明 |
|------|------|------|
| 仓库 | 5-8 | 选择流行、测试覆盖好的 Python 项目 |
| 种子任务 | 80-120 | 每仓库 10-20 个，人工设计 |
| 漂移类型覆盖 | 6 类 | T1-T6 各 ~15-20 个任务 |
| 复合漂移 | 20-30 | 2 种漂移组合 |
| 总任务 | 100-150 | 每个都有确定性测试终态 |
| 评估运行 | k=4 | 每任务 4 次独立运行（pass^k） |

---

## 四、与原方案的对比

| 维度 | 原方案 | SWE 新方案 |
|------|--------|-----------|
| 领域 | 8 个通用领域 | 1 个深领域（SWE） |
| 环境 | 模拟工具描述 | 真实代码仓库 + Docker |
| 评估 | LLM-as-Judge 为主 | 测试通过/失败（确定性） |
| 工具 | 200+ 描述性工具定义 | ~10 个真实可执行工具 |
| 用户 | 静态轨迹 | 环境耦合模拟器 |
| 可靠性 | 无 | pass^k |
| 任务数 | 576 | 100-150（但每个更深） |
| 投稿 track | D&B 或 Main | D&B（更匹配） |

---

## 五、潜在风险

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| SWE-EVO / SWE-CI 已部分覆盖"需求变化" | 高 | 它们的需求来自版本历史/自动生成，我们的来自**用户实时交互**，本质不同 |
| 构建可执行环境工作量大 | 中 | 复用 SWE-bench 的 Docker 基础设施 |
| 用户模拟器质量 | 中 | 漂移消息是确定性的（从蓝图读取），模拟器只做简单确认 |
| 任务设计需要深厚 SWE 知识 | 中 | 选择简单、独立的功能点，避免需要深入理解项目架构的任务 |
| 与 SWE-bench 生态兼容性 | 低 | 工具接口对齐 SWE-agent，方便现有 agent 适配 |

---

## 六、下一步行动建议

1. **选择 3-5 个仓库**：Flask, Requests, Click, Httpx, FastAPI（流行、测试好、Python）
2. **搭建 Docker 环境**：每个仓库一个可执行环境
3. **手工设计 20 个 pilot 任务**（每种漂移类型 3-4 个），验证可行性
4. **实现用户模拟器原型**
5. **在 2-3 个 agent 上跑 pilot**（Claude, GPT-4o, Qwen），验证漂移确实导致性能下降
6. 根据 pilot 结果决定是否 scale up
