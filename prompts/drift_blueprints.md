# IntentDrift 蓝图生成 Prompt 模板

本文件包含6类漂移类型的蓝图生成prompt，用于 Step 2 (Blueprint Generation)。

---

## 通用系统 Prompt

```
You are an expert in designing realistic multi-turn tool-use evaluation scenarios. Your task is to create "intent drift blueprints" — structured descriptions of how a user's intent evolves during a tool-assisted conversation.

CRITICAL REQUIREMENTS:
1. NATURALNESS: Every drift must be something a real user would plausibly do. Not adversarial, not contrived — just realistic.
2. TOOL-GROUNDED: The user's requests must be achievable through the provided tool set.
3. STRUCTURED OUTPUT: Follow the exact output schema provided.
4. DIVERSITY: Avoid repetitive patterns across blueprints for the same seed task.
```

---

## T1: 渐进细化 (Progressive Refinement)

```
### Task: Generate an Intent Drift Blueprint — Type T1: Progressive Refinement

**Definition**: The user starts with a vague or broad intent and progressively narrows/specifies it over multiple turns, revealing more detailed preferences as the conversation unfolds.

**Seed Task**: {seed_task}
**Domain**: {domain}
**Available Tools**: {tool_list}

**Instructions**:
Design a multi-turn scenario where:
1. The user begins with a broad, underspecified request
2. Over 3-5 turns, the user progressively adds specificity (NOT all at once)
3. Each refinement is triggered naturally — e.g., by seeing the agent's results and reacting
4. The agent should ideally update its search/action incrementally, not restart from scratch

**Output Schema**:
```json
{
  "blueprint_id": "T1-{domain}-{number}",
  "drift_type": "progressive_refinement",
  "domain": "{domain}",
  "initial_intent": "The user's starting request (vague)",
  "refinement_chain": [
    {
      "turn": 2,
      "trigger": "What the user sees/hears that motivates refinement",
      "user_utterance": "What the user says",
      "refined_intent": "Updated intent after this turn",
      "tools_affected": ["which tools need re-invocation"]
    },
    // ... 2-4 more refinements
  ],
  "final_intent": "The fully specified intent after all refinements",
  "ideal_agent_behavior": "Description of how an ideal agent handles incremental refinement",
  "anti_pattern": "Common failure mode (e.g., restarting search from scratch each time)",
  "expected_tool_calls": ["ordered list of ideal tool invocations"],
  "difficulty": "easy|medium|hard",
  "naturalness_score": 1-5
}
```

**Example** (for reference, generate a DIFFERENT scenario):
- Initial: "Find me a restaurant nearby"
- Refinement 1 (turn 2): Seeing diverse options → "I'm in the mood for Italian"
- Refinement 2 (turn 3): Seeing Italian options → "Something under $30 per person"
- Refinement 3 (turn 5): After seeing a few → "Does any of them have outdoor seating?"
- Final: "Italian restaurant, under $30/person, with outdoor seating, nearby"
```

---

## T2: 主题转移 (Topic Shift)

```
### Task: Generate an Intent Drift Blueprint — Type T2: Topic Shift

**Definition**: The user temporarily or permanently shifts to a completely different task topic during the conversation, potentially returning to the original topic later.

**Seed Task**: {seed_task}
**Domain**: {domain}
**Available Tools**: {tool_list}

**Instructions**:
Design a multi-turn scenario where:
1. The user starts with the seed task
2. At some point (turn 3-6), the user shifts to an UNRELATED topic
3. The shift can be: (a) temporary — user returns to original task, or (b) permanent — user abandons original task
4. The shift should feel natural — e.g., something reminded the user of another task, or the user suddenly remembers something urgent
5. The agent must manage the context switch cleanly

**Output Schema**:
```json
{
  "blueprint_id": "T2-{domain}-{number}",
  "drift_type": "topic_shift",
  "domain": "{domain}",
  "initial_intent": "Original task",
  "shift_event": {
    "turn": 4,
    "trigger": "Why the user shifts (natural reason)",
    "user_utterance": "What the user says to shift topic",
    "new_topic": "The unrelated topic",
    "shift_permanence": "temporary|permanent"
  },
  "return_event": {  // null if permanent shift
    "turn": 7,
    "user_utterance": "How the user signals return to original topic",
    "expected_context_recall": "What info should the agent remember from before the shift"
  },
  "ideal_agent_behavior": "How the ideal agent handles: acknowledge shift, serve new topic, restore context on return",
  "anti_pattern": "Common failure (e.g., forgetting original context, confusing the two tasks)",
  "expected_tool_calls": ["ordered list"],
  "difficulty": "easy|medium|hard",
  "naturalness_score": 1-5
}
```

**Natural shift triggers** (use as inspiration):
- "Oh wait, before I forget — can you also check..."
- "Actually, this reminds me, I need to..."
- "Hold on, let me ask you something else first"
- "Sorry, my boss just messaged me — can you quickly look up..."
```

---

## T3: 约束追加 (Constraint Addition)

```
### Task: Generate an Intent Drift Blueprint — Type T3: Constraint Addition

**Definition**: The user adds NEW constraints AFTER the agent has already partially executed the task, potentially invalidating previous results or requiring backtracking.

**Seed Task**: {seed_task}
**Domain**: {domain}
**Available Tools**: {tool_list}

**Instructions**:
Design a multi-turn scenario where:
1. The user gives an initial request with some constraints
2. The agent begins execution (tool calls made, partial results returned)
3. The user then adds a NEW constraint that was NOT mentioned initially
4. The new constraint may or may not invalidate the agent's prior work
5. The key challenge: the agent must assess whether prior results still hold and decide whether to redo work

**Output Schema**:
```json
{
  "blueprint_id": "T3-{domain}-{number}",
  "drift_type": "constraint_addition",
  "domain": "{domain}",
  "initial_intent": "Original request with initial constraints",
  "initial_constraints": ["constraint_1", "constraint_2"],
  "agent_partial_execution": {
    "turns": [2, 3],
    "actions_taken": ["What the agent did before the new constraint"],
    "results_obtained": "What results were shown to user"
  },
  "constraint_addition": {
    "turn": 4,
    "user_utterance": "How the user adds the constraint",
    "new_constraint": "The added constraint",
    "invalidates_prior_work": true/false,
    "reason_for_late_addition": "Why user didn't mention it earlier (must be natural)"
  },
  "ideal_agent_behavior": "Check if prior results satisfy new constraint; if not, redo with all constraints; do NOT restart if prior results are still valid",
  "anti_pattern": "Ignoring new constraint / restarting everything unnecessarily / hallucinating compliance",
  "expected_tool_calls": ["ordered list including any re-invocations"],
  "difficulty": "easy|medium|hard",
  "naturalness_score": 1-5
}
```

**Natural reasons for late constraints** (use as inspiration):
- User forgot to mention it initially
- User learned new info during the conversation (e.g., from agent's results)
- External event changed user's requirements (e.g., budget update, schedule change)
- User assumed the constraint was obvious/default
```

---

## T4: 目标矛盾 (Goal Conflict)

```
### Task: Generate an Intent Drift Blueprint — Type T4: Goal Conflict

**Definition**: The user expresses requirements that are mutually contradictory, either within a single turn or across turns. The agent must detect the conflict and proactively seek clarification.

**Seed Task**: {seed_task}
**Domain**: {domain}
**Available Tools**: {tool_list}

**Instructions**:
Design a multi-turn scenario where:
1. The user initially states one requirement
2. Later, the user states another requirement that CONTRADICTS the first
3. The contradiction can be: (a) explicit — directly opposite, or (b) implicit — logically incompatible but not obviously so
4. An ideal agent should DETECT the conflict and ASK for clarification, rather than silently picking one or hallucinating a solution

**Output Schema**:
```json
{
  "blueprint_id": "T4-{domain}-{number}",
  "drift_type": "goal_conflict",
  "domain": "{domain}",
  "initial_intent": "First requirement",
  "conflicting_requirement": {
    "turn": 4,
    "user_utterance": "What the user says that creates conflict",
    "conflict_type": "explicit|implicit",
    "conflicting_with": "Which earlier requirement it contradicts",
    "conflict_explanation": "Why these two requirements are incompatible"
  },
  "resolution_options": [
    "Option A: prioritize requirement 1",
    "Option B: prioritize requirement 2",
    "Option C: propose a compromise"
  ],
  "ideal_agent_behavior": "Detect conflict → clearly articulate it to user → present options → let user decide",
  "anti_pattern": "Silently ignoring one requirement / hallucinating impossible solution / not detecting conflict",
  "expected_tool_calls": ["ordered list"],
  "difficulty": "easy|medium|hard",
  "naturalness_score": 1-5
}
```
```

---

## T5: 隐性需求浮现 (Implicit Need Emergence)

```
### Task: Generate an Intent Drift Blueprint — Type T5: Implicit Need Emergence

**Definition**: The user has needs they haven't explicitly stated, but which can be reasonably inferred from context. An ideal agent would proactively identify and address these needs.

**Seed Task**: {seed_task}
**Domain**: {domain}
**Available Tools**: {tool_list}

**Instructions**:
Design a multi-turn scenario where:
1. The user makes an explicit request
2. The context IMPLIES additional needs the user hasn't stated
3. A good agent would proactively offer to address these implicit needs
4. The implicit needs should be REASONABLE to infer (not mind-reading), based on common patterns or logical connections

**Output Schema**:
```json
{
  "blueprint_id": "T5-{domain}-{number}",
  "drift_type": "implicit_need_emergence",
  "domain": "{domain}",
  "explicit_request": "What the user actually asks for",
  "implicit_needs": [
    {
      "need": "What the user likely also needs but didn't say",
      "evidence": "What contextual clues suggest this need",
      "confidence": "high|medium",
      "relevant_tools": ["which tools could address this need"]
    }
  ],
  "proactive_turn": {
    "ideal_turn": 3,
    "agent_proactive_utterance": "How the agent should offer to help with implicit need",
    "user_confirmation": "How user would respond (likely grateful acceptance)"
  },
  "ideal_agent_behavior": "Complete explicit request first, then proactively offer to address implicit needs based on contextual inference",
  "anti_pattern": "Only doing exactly what was asked with no contextual awareness / over-assuming and doing unrequested things without asking",
  "expected_tool_calls": ["ordered list"],
  "difficulty": "easy|medium|hard",
  "naturalness_score": 1-5
}
```

**Common implicit need patterns**:
- Booking flight → may need hotel, ground transport, weather info
- Scheduling meeting → may need to check conflicts, send invites, book room
- Analyzing data → may need visualization, export, summary
- Buying product → may need comparison, reviews, warranty info
```

---

## T6: 意图回溯 (Intent Backtracking)

```
### Task: Generate an Intent Drift Blueprint — Type T6: Intent Backtracking

**Definition**: The user reverts a previous decision and wants to return to an earlier choice point in the conversation, potentially after the agent has already acted on the abandoned decision.

**Seed Task**: {seed_task}
**Domain**: {domain}
**Available Tools**: {tool_list}

**Instructions**:
Design a multi-turn scenario where:
1. The user makes a choice/decision at some point
2. The agent acts on that decision (possibly making API calls, modifying state)
3. Later, the user wants to UNDO that decision and go back to a previous option
4. The agent must recall the previous options and handle any state that needs reversal

**Output Schema**:
```json
{
  "blueprint_id": "T6-{domain}-{number}",
  "drift_type": "intent_backtracking",
  "domain": "{domain}",
  "initial_intent": "Original request",
  "decision_point": {
    "turn": 3,
    "options_presented": ["option A", "option B", "option C"],
    "user_choice": "option B",
    "actions_taken_on_choice": ["What the agent did after user chose B"]
  },
  "backtrack_event": {
    "turn": 6,
    "user_utterance": "How the user signals they want to go back",
    "target": "Which earlier option/state they want to return to",
    "reason": "Why user changed their mind (natural reason)",
    "state_to_reverse": ["What actions need to be undone"]
  },
  "ideal_agent_behavior": "Remember previous options → confirm which one to revert to → undo relevant actions → proceed with new choice",
  "anti_pattern": "Forgetting previous options / unable to undo actions / confusing current and previous state",
  "expected_tool_calls": ["ordered list including undo/redo calls"],
  "difficulty": "easy|medium|hard",
  "naturalness_score": 1-5
}
```

**Natural backtracking triggers**:
- "Actually, I changed my mind — can we go back to the other one?"
- "Wait, that's too expensive. What was the second option again?"
- "Hmm, on second thought, the first approach was better"
- "My partner just said they prefer X, can we switch?"
```

---

## 批量生成 Prompt

用于一次生成多个蓝图的 wrapper prompt：

```
You will generate {N} intent drift blueprints for the following configuration:

Domain: {domain}
Drift Type: {drift_type} (see type definition above)
Seed Tasks: {seed_task_list}
Available Tools: {tool_list}

Requirements:
1. Generate exactly one blueprint per seed task
2. Ensure DIVERSITY across blueprints — vary the drift trigger, timing, difficulty, and specific patterns
3. Difficulty distribution: ~30% easy, ~50% medium, ~20% hard
4. All blueprints must pass the naturalness check (score >= 4)
5. Use the exact output schema defined for {drift_type}

Output all blueprints as a JSON array.
```

---

## 蓝图验证 Prompt（用于 Layer 2: LLM 审查委员会）

```
You are a quality reviewer for intent drift evaluation scenarios. Review the following blueprint and evaluate it on these criteria:

Blueprint: {blueprint_json}

Evaluation Criteria:
1. **Naturalness** (1-5): Would a real user plausibly exhibit this behavior? Is the drift trigger believable?
2. **Drift Type Accuracy**: Is the labeled drift type (T1-T6) correct for this scenario?
3. **Tool Groundedness**: Can the scenario be executed with the provided tools?
4. **Difficulty Calibration**: Is the difficulty label (easy/medium/hard) accurate?
5. **Completeness**: Are all required fields filled and consistent?

For each criterion, provide:
- Score (1-5)
- Brief justification
- Suggested fixes (if score < 4)

Output:
```json
{
  "overall_pass": true/false,
  "scores": {
    "naturalness": {"score": 4, "justification": "..."},
    "type_accuracy": {"score": 5, "justification": "..."},
    "tool_groundedness": {"score": 3, "justification": "...", "fix": "..."},
    "difficulty_calibration": {"score": 4, "justification": "..."},
    "completeness": {"score": 5, "justification": "..."}
  },
  "recommendation": "accept|revise|reject",
  "revision_notes": "..."
}
```
```
