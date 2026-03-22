# IntentDrift 论文示意图绘图提示词

以下提示词用于 Nano Banana 生成论文示意图。

---

## Figure 1: 核心示意图 — IntentDrift Motivating Example

### 提示词（英文，适合学术风格）

```
Create an academic research figure illustrating "Intent Drift in LLM Tool-Use Agent Evaluation".

The figure is split into two parallel vertical panels with a clear divider:

LEFT PANEL (labeled "Existing Benchmarks: Static Intent"):
- Shows a simple linear conversation flow between a User icon and an Agent icon
- 5 conversation turns flowing top to bottom
- User's intent stays the same throughout (shown as a single colored bar labeled "Book a flight to Tokyo")
- Agent successfully completes the task with a green checkmark at the bottom
- The conversation is clean and straightforward
- Use light gray/blue tones

RIGHT PANEL (labeled "Real-World: Dynamic Intent Drift"):
- Shows the same conversation starting point, but the User's intent evolves
- Turn 1-2: User asks "Book a flight to Tokyo" (same blue bar)
- Turn 3: A drift marker (lightning bolt or arrow icon) indicates "T1: Progressive Refinement" — user narrows to "direct flights only, under $800"
- Turn 4: Another drift marker "T2: Topic Shift" — user suddenly asks "What's the weather in Tokyo next week?"
- Turn 5: Another drift marker "T3: Constraint Addition" — user returns to booking but adds "must depart after 6pm"
- Turn 6-7: Agent struggles, shown with orange/red warning indicators
- The intent bar on the right changes color at each drift point (blue → teal → orange → purple)
- Final result: partial completion with an orange warning icon

BOTTOM SECTION spanning both panels:
- A horizontal bar chart comparing "Task Success Rate": Left panel shows ~85% (green), Right panel shows ~35% (red/orange)
- Label: "Current benchmarks overestimate agent capabilities by ignoring intent drift"

STYLE:
- Clean, modern academic figure style
- Flat design with rounded corners
- Color palette: primary blue (#4A90D9), secondary teal (#50C878), warning orange (#FF8C42), error red (#E74C3C), neutral gray (#F5F5F5)
- Sans-serif font (similar to Helvetica or Inter)
- White background
- No decorative elements, purely informational
- Resolution suitable for conference paper (at least 300 DPI equivalent)
- Aspect ratio approximately 16:9
```

---

## Figure 2: 意图漂移分类体系 (Taxonomy Overview)

### 提示词

```
Create an academic taxonomy diagram for "Six Types of Intent Drift in Tool-Use Agent Interactions".

Layout: A central hub labeled "Intent Drift Taxonomy" connected to 6 satellite nodes arranged in a circular/radial pattern.

Each satellite node represents one drift type with:
- An icon, a short label, and a one-line description
- A small illustrative mini-diagram showing the intent trajectory

The 6 types (clockwise from top):

1. "T1: Progressive Refinement" (icon: funnel/magnifying glass)
   - Mini-diagram: A wide arrow gradually narrowing
   - Description: "User narrows a vague intent over turns"
   - Color: Blue (#4A90D9)

2. "T2: Topic Shift" (icon: branching arrows)
   - Mini-diagram: A straight arrow that forks to a different direction then returns
   - Description: "User switches to an unrelated task mid-conversation"
   - Color: Teal (#50C878)

3. "T3: Constraint Addition" (icon: plus sign in a circle)
   - Mini-diagram: A straight arrow with new constraint blocks appearing along it
   - Description: "User adds new constraints after partial execution"
   - Color: Orange (#FF8C42)

4. "T4: Goal Conflict" (icon: two opposing arrows)
   - Mini-diagram: Two arrows pointing in opposite directions from a single point
   - Description: "User expresses contradictory requirements"
   - Color: Red (#E74C3C)

5. "T5: Implicit Need Emergence" (icon: lightbulb with dotted outline)
   - Mini-diagram: A solid arrow with a dotted parallel arrow gradually becoming solid
   - Description: "Unstated needs surface through context"
   - Color: Purple (#9B59B6)

6. "T6: Intent Backtracking" (icon: U-turn arrow)
   - Mini-diagram: An arrow going forward then curving back to an earlier point
   - Description: "User reverts to a previously abandoned option"
   - Color: Gold (#F1C40F)

BOTTOM: A horizontal axis showing "Orthogonal Dimensions" with 5 labeled scales:
- Drift Distance: Near ↔ Far
- Explicitness: Explicit ↔ Implicit
- Timing: Early ↔ Late
- Frequency: Single ↔ High
- Reversibility: Irreversible ↔ Reversible

STYLE:
- Clean academic diagram, suitable for NeurIPS paper
- Flat design, rounded corners, consistent spacing
- White background, subtle gray grid lines
- Sans-serif font
- No 3D effects, shadows minimal
- High resolution, aspect ratio ~4:3
```

---

## Figure 3: IntentDrift-Bench 构建流程 (Pipeline)

### 提示词

```
Create an academic pipeline diagram showing the construction process of "IntentDrift-Bench Dataset".

Layout: A horizontal left-to-right flow with 5 main stages connected by arrows.

Stage 1 - "Seed Task Collection" (icon: database):
- Three input sources shown as smaller boxes feeding into this stage:
  - "Existing Benchmarks (ToolBench, tau-bench)"
  - "Real User Logs (WildToolBench)"
  - "Expert-Designed Scenarios"
- Output label: "150 seed tasks across 8 domains"

Stage 2 - "Drift Script Generation" (icon: script/scroll):
- Shows LLM icon + Human reviewer icon working together
- A small branching diagram: one seed task splitting into 3-4 drift variants
- Labels for drift types (T1-T6) color-coded
- Output label: "600 drift scripts"

Stage 3 - "Dialogue Instantiation" (icon: chat bubbles):
- Shows drift scripts being converted to multi-turn conversations
- A mini conversation snippet
- Output label: "800 dialogue instances"

Stage 4 - "Annotation & Validation" (icon: checklist):
- Two annotator icons with arrows to same document (cross-validation)
- Labels: "Intent state per turn", "Drift points", "Ideal responses"
- A small badge showing "Cohen's κ > 0.7"
- Output label: "Fully annotated benchmark"

Stage 5 - "Quality Assurance" (icon: shield/checkmark):
- Three QA checks shown as sub-items:
  - "Naturalness filter"
  - "Human baseline test"
  - "Difficulty calibration"
- Output label: "IntentDrift-Bench v1.0"

BOTTOM: A statistics summary bar showing key numbers:
- "8 Domains | 6 Drift Types | 800 Scenarios | 8-15 Turns/Dialogue | 200+ Tools"

STYLE:
- Horizontal flow, clean academic style
- Each stage is a rounded rectangle with soft color fill
- Arrows between stages are thick and clean
- Color progression from left to right: light blue → medium blue → teal → green → dark green
- White background
- Sans-serif font
- Suitable for NeurIPS paper figure
- Aspect ratio ~3:1 (wide)
```

---

## Figure 4: 实验结果 — 模型在不同漂移类型上的雷达图

### 提示词（此图可用代码生成，提示词仅作参考）

```
Create a radar/spider chart comparing LLM performance across 6 intent drift types.

The chart has 6 axes, one for each drift type:
- T1: Refinement
- T2: Topic Shift
- T3: Constraint Addition
- T4: Goal Conflict
- T5: Implicit Need
- T6: Backtracking

Show 4-5 overlapping polygons representing different models:
- GPT-4o (blue line, filled with 20% opacity blue)
- Claude Sonnet 4 (teal line, filled with 20% opacity teal)
- Llama-3.1-70B (orange line, filled with 20% opacity orange)
- Qwen2.5-72B (purple line, filled with 20% opacity purple)
- GPT-4o-mini (gray dashed line, no fill)

Each polygon should show different strengths:
- GPT-4o: relatively balanced but still low on T3 and T6
- Claude: strong on T4 (conflict detection) and T5 (implicit needs)
- Open-source models: notably weaker on T5 and T6

Scale: 0-100 on each axis, with gridlines at 20, 40, 60, 80

STYLE:
- Clean academic chart
- Legend in top-right corner
- Light gray gridlines
- White background
- High resolution
- Aspect ratio 1:1 (square)
```

---

## 使用建议

1. **Figure 1** 是最重要的图，放在论文第一页，用于直觉上传达核心思想
2. **Figure 2** 放在 Section 3 (Taxonomy)，作为分类体系的可视化总览
3. **Figure 3** 放在 Section 4 (Dataset)，展示数据集构建的系统性
4. **Figure 4** 放在 Section 6 (Experiments)，作为核心实验结果的可视化

建议优先生成 Figure 1 和 Figure 2，这两张图对论文的第一印象影响最大。
