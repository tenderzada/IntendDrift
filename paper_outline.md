# IntentDrift: Evaluating Tool-Use Agents Under Dynamic User Intent Evolution

## Paper Outline (NeurIPS 2026)

---

## Title Options

1. **IntentDrift: Evaluating LLM Tool-Use Agents Under Dynamic User Intent Evolution**
2. **Beyond Static Intents: A Benchmark for Tool-Use Agents in the Face of Evolving User Goals**
3. **Do Tool Agents Keep Up? Benchmarking LLM Agents Under Realistic Intent Drift**

推荐选项 1：简洁、有记忆点、直接传达核心贡献。

---

## Abstract (~250 words)

**段落结构**: 问题 → 差距 → 我们的工作 → 方法 → 关键发现

- **问题**: LLM tool-use agents are evaluated on benchmarks where user intents remain static and explicit throughout the conversation.
- **差距**: In reality, user intents dynamically evolve — users refine vague goals, shift topics mid-task, add constraints after partial execution, express contradictory needs, or harbor implicit requirements that surface gradually. This mismatch leads to an overestimation of agent capabilities.
- **我们的工作**: We introduce IntentDrift, a systematic framework for evaluating tool-use agents under dynamic intent evolution. Our contributions include: (1) a taxonomy of six intent drift patterns grounded in HCI literature, (2) IntentDrift-Bench, a benchmark of X scenarios across Y domains with fine-grained drift annotations, and (3) a suite of metrics measuring intent tracking accuracy, drift detection latency, adaptation success, and context preservation.
- **发现**: Evaluating Z models reveals that [主要发现1: 性能下降幅度], [主要发现2: 最难漂移类型], and [主要发现3: 架构差异]. Our results demonstrate that current evaluations significantly overestimate agent capabilities and highlight intent drift as a critical yet overlooked challenge.

---

## 1. Introduction (1.5 pages)

### 1.1 开篇：用一个具体例子引入问题 (0.5 page)

- **Motivating Example** (Figure 1): 展示一个真实场景下的多轮工具调用对话，其中用户意图发生自然漂移
  - 左半部分：现有基准中的"理想化"版本（用户意图清晰不变）
  - 右半部分：真实版本（用户在过程中细化、追加约束、临时跑题）
  - 底部：同一代理在两种场景下的表现差异

### 1.2 问题陈述 (0.3 page)

- 现有基准的核心假设：用户意图 = 静态 + 明确
- 该假设与真实交互的脱节：引用 WildToolBench（57模型无一超15%）、Lost in Simulation 等
- 意图漂移是真实用户交互中最普遍但最被忽视的特征

### 1.3 我们的贡献 (0.3 page)

明确列出 3-4 个贡献点：
1. **Taxonomy**: 形式化定义六类意图漂移模式，建立意图漂移的理论框架
2. **Benchmark**: IntentDrift-Bench — X个场景，Y个领域，Z个工具，包含细粒度漂移标注
3. **Metrics**: 一套面向意图追踪能力的评估指标体系（ITA, DDL, ASR, CPS, PCR, GDS）
4. **Findings**: 对 N 个模型的系统性评估，揭示 [核心发现]

### 1.4 论文结构 (0.1 page)

简述各章节安排。

---

## 2. Related Work (1 page)

### 2.1 Tool-Use Agent Evaluation

- 现有基准总览：ToolBench, API-Bank, tau-bench, WildToolBench, ACEBench, ToolComp
- 它们的共同局限：静态意图假设
- 表格对比：各基准在意图动态性维度的覆盖情况

### 2.2 Agent Drift and Behavioral Degradation

- **AgentDrift** (arXiv 2603.12564): 推荐系统中的安全漂移，定义语义/协调/行为退化
- **Agent Drift** (arXiv 2601.04170): 量化代理行为退化的通用框架
- **关键区分**: 这些工作关注**代理侧退化**，我们关注**用户侧意图演化**——方向互补

### 2.3 User Simulation for Agent Evaluation

- LLM-based user simulation: ChatChecker, tau^2-bench, UserLM
- 其局限性: Lost in Simulation（LLM模拟用户不可靠，偏差达9%）
- 我们的区别：不仅模拟用户，更系统性地定义和控制意图漂移

### 2.4 Intent Understanding in Dialogue Systems

- **TUNA 框架** (Shelby et al., 2025): 6模式→14策略→57请求类型，最系统的用户交互分类
- **ISO 24617-2**: 对话行为标注标准（9维度+56功能），我们的标注体系与之对齐
- **DST Challenge**: Goal Changes 指标，我们的 ITA/DDL 是其在工具代理场景的自然扩展
- Topic shift detection: 多粒度提示学习方法
- 与工具代理场景的差异：工具代理需要执行不可逆操作，意图漂移的代价更高

---

## 3. Intent Drift Taxonomy (1.5 pages)

### 3.1 Formalization

- 形式化定义"用户意图状态" $I_t$ 和"意图漂移事件" $\Delta(I_t, I_{t+k})$
- 定义漂移距离函数 $d(I_t, I_{t+k})$
- 与 TUNA 框架的对齐：将我们的漂移类型映射到 TUNA 的交互模式/策略层级
- 与 DST 中 Goal Changes 概念的关联与扩展

### 3.2 Six Drift Patterns

- 逐一定义六类漂移模式（T1-T6），每类给出：
  - 形式化定义
  - 真实场景示例（附完整对话）
  - 对代理的挑战分析
  - 与已有 HCI 文献的关联
  - 与 TUNA 分类中对应请求类型的映射

### 3.3 Drift Dimensions

- 漂移距离、显性、时机、频率、可回溯性
- 这些维度如何与六类模式正交组合

### 3.4 Compound Drift

- 真实场景中的复合漂移模式
- 复合漂移的理论复杂度分析

---

## 4. IntentDrift-Bench (1.5 pages)

### 4.1 Design Principles

- 真实性 (Realism): 漂移模式来源于真实用户行为
- 可控性 (Controllability): 每个场景的漂移类型和时机可精确标注
- 覆盖度 (Coverage): 六类漂移 x 多个领域 x 多种难度
- 可复现性 (Reproducibility): 确定性的评估流程

### 4.2 Construction Pipeline (Blueprint-to-Trajectory, inspired by APIGen-MT)

- **Stage 1: Blueprint Generation** — 漂移蓝图设计（初始意图 → 触发点 → 漂移后意图）
- **Stage 2: Trajectory Generation** — 蓝图实例化为多轮对话（生成/验证用不同LLM防同源偏差）
- **Stage 3: Three-Layer Verification** — 自动化检查 → LLM审查委员会 → 双人工标注 (Cohen's κ ≥ 0.75)
- 评估锚点：借鉴 tau-bench 的数据库状态比较，每个场景定义期望终态

### 4.3 Dataset Statistics

- 规模、领域分布、漂移类型分布、对话长度分布
- 与现有基准的定量对比表

### 4.4 Human Baseline

- 人类"代理"在 IntentDrift-Bench 上的表现
- 人类如何自然地处理意图漂移

---

## 5. Evaluation Metrics (1 page)

### 5.1 Metric Definitions

- ITA, DDL, ASR, CPS, PCR, GDS 的形式化定义
- 综合评分 IDS 的计算方法

### 5.2 Automated Evaluation

- LLM-as-Judge 的评估协议
- 评分 rubric 设计
- 人类-LLM 评估一致性验证

---

## 6. Experiments (2.5 pages)

### 6.1 Experimental Setup

- 模型列表、代理框架、运行参数
- 评估流程

### 6.2 Main Results (Table 1 + Figure 2)

- **Table 1**: 模型 x 漂移类型 的 IDS 矩阵
- **Figure 2**: 雷达图——不同模型在六类漂移上的表现轮廓
- 关键发现：
  - 整体性能下降幅度
  - 最难/最易的漂移类型排序
  - 模型规模与漂移鲁棒性的关系

### 6.3 Static vs. Drift Comparison (Figure 3)

- 同一任务有/无漂移的成功率对比
- 量化"理想化评估"的高估程度

### 6.4 Ablation: Drift Dimensions (Figure 4)

- 固定漂移类型，变化距离/显性/时机/频率
- 哪个维度影响最大？

### 6.5 Compound Drift Analysis

- 单一 vs 复合漂移的性能对比
- 是否存在超线性退化？

### 6.6 Agent Framework Analysis

- 同一 LLM，不同框架的漂移鲁棒性
- 反思架构(Reflexion)是否真的有帮助？

### 6.7 Case Studies (Figure 5)

- 2-3 个具体对话案例的深入分析
- 成功处理漂移 vs 失败处理漂移的对比

---

## 7. Discussion (0.5 page)

### 7.1 Why Intent Drift Is Hard

- 理论分析：漂移要求代理维护动态信念状态(belief state)
- 与规划(planning)和重规划(re-planning)的关系

### 7.2 Implications for Agent Design

- 哪些设计选择提升了漂移鲁棒性？
- 对未来代理架构的建议

### 7.3 Limitations

- 数据集规模和领域覆盖的局限
- LLM-as-Judge 的局限
- 英语为主的语言覆盖

---

## 8. Conclusion (0.3 page)

- 重述核心贡献
- 关键发现总结
- 展望：意图漂移感知的代理架构

---

## Appendix

- A: 完整的漂移类型示例库
- B: 标注指南全文
- C: LLM Judge 的评分 rubric
- D: 补充实验结果
- E: 数据集许可与伦理声明

---

## 图表清单

| 编号 | 类型 | 内容 | 位置 |
|------|------|------|------|
| Figure 1 | 示意图 | Motivating example: 静态 vs 动态意图对比 | Introduction |
| Figure 2 | 雷达图 | 不同模型在六类漂移上的表现 | Main Results |
| Figure 3 | 柱状图 | 有/无漂移的成功率对比 | Static vs Drift |
| Figure 4 | 热力图 | 漂移维度(距离x显性x时机) vs 性能 | Ablation |
| Figure 5 | 对话流程图 | 成功/失败案例分析 | Case Studies |
| Table 1 | 主表 | 模型 x 漂移类型 x 指标 | Main Results |
| Table 2 | 对比表 | IntentDrift-Bench vs 现有基准 | Dataset |
| Table 3 | 消融表 | 复合漂移分析 | Compound Drift |
