# 医疗 Agent 评测数据集清单

日期: 2026-04-01

## 目的

这份文档用于后续为本项目选择医疗评测基准。重点不是列出“医学数据集大全”，而是筛出对当前后端 agent 有实际价值的评测集，并标明：

- 是否开源或公开可用
- 评测方式
- 主要覆盖的能力
- 对当前后端 agent 的适配价值

当前后端的核心形态是：

- `FastAPI + /api/chat`
- `RAG 检索 + 会话记忆`
- 最终输出是面向患者的医疗解释型回答
- 当前没有真实工具调用链，也没有 EHR 操作环境

因此，最相关的是：

- 最终回答质量
- 多轮上下文利用
- 提问与信息补全能力
- 医疗安全性
- 复杂推理质量

## 结论先行

建议分两层做评测：

1. 总评层：
   - `HealthBench`
   - 作用: 评估最终回答质量、医疗安全、语气适配、上下文理解
2. 补充层：
   - `HealthQ`
   - `MedSafetyBench`
   - `MedAgentBench` 或 `MedAgentsBench`
   - `MedR-Bench`

如果只跑一个集，优先 `HealthBench`。  
如果要更像“评整个 agent”，推荐 `HealthBench + HealthQ + MedSafetyBench` 组合。  
如果以后接入工具或 EHR 环境，再加入 `MedAgentBench`。

## 数据集对比

| 名称 | 是否开源 | 评测详情 | 主要测试能力 | 对当前后端 agent 的价值 | 备注 |
|---|---|---|---|---|---|
| HealthBench | 部分开源 | 5,000 个真实感医疗多轮对话；模型回答最后一条用户消息；按医生编写 rubric 打分；官方参考实现使用 GPT-4.1 作为 grader | 最终回答质量、医疗安全、上下文理解、角色适配、分诊与不确定性处理 | 很高 | 最适合做总评；能自动化跑，不需要网页手工录入 |
| HealthBench Hard / Consensus | 部分开源 | HealthBench 的更难子集或一致性子集；仍使用 rubric + model grader | 更强区分度、对难例表现更敏感 | 高 | 适合先做小规模试跑或回归测试 |
| MedAgentBench | 是 | 虚拟 EHR 环境；需要启动任务 worker、controller、assigner；结果写入 `overall.json` | 计划、环境交互、状态跟踪、医疗工作流执行 | 中 | 当前后端没有 EHR/tool 环境，适配成本较高 |
| HealthQ | 是 | 基于 ChatDoctor 和 MTS-Dialog 构造的问诊链路评测；用 LLM judge、ROUGE、NER 指标评估生成问题 | 主动追问、信息收集、问诊链质量 | 很高 | 很适合补 HealthBench 的短板，因为当前系统目前更弱的是“追问”而不是“答题” |
| MedSafetyBench | 是 | 900 train + 900 test 的医疗安全示例，另有 74,374 条有害医疗请求资源；研究用途 | 危险建议拒绝、伤害性输出控制、安全边界 | 很高 | 对患者向 agent 非常重要；建议纳入固定回归集 |
| MedAgentsBench | 是 | 面向 medical QA agents 的标准化 benchmark；整合多来源医学问答集 | 复杂医学推理、agent framework 对比 | 中高 | 比 MedAgentBench 更接近“问答 agent”，但更偏复杂 reasoning，不是真实诊疗流程环境 |
| MedR-Bench | 是 | 基于 PMC-OA 真实病例；配套 Reasoning Evaluator 自动评估自由文本推理 | 临床推理过程质量、鉴别诊断链、解释性推理 | 中高 | 对“推理过程”评估有价值，但不等同于患者端最终回答质量 |
| MedS-Bench | 是 | 由 39 个已有数据集整理出的 11 类高层临床任务 | 广谱医学 NLP/临床任务能力 | 中 | 覆盖面广，但 agent 性弱于 HealthBench/HealthQ |
| MedMCQA | 是 | 194k 多选题；21 个医学学科、2.4k 主题 | 医学知识、考试型推理 | 低到中 | 适合做廉价知识回归，不适合代表整个 agent |
| MedConceptsQA | 公开可用，许可证待单独核实 | 可通过 `lm-eval` 跑 zero-shot / few-shot；面向医学概念问答 | 医学术语、概念理解 | 中 | 适合作为轻量补充集，不适合作为 agent 总评 |

## 逐项说明

### 1. HealthBench

为什么重要：

- 它是最接近“用户真的在跟医疗 AI 对话”的基准之一。
- 它评的是最终回答，而不是考试题选项。
- 对你当前这种“RAG + 会话记忆 + 最终回答”的后端最匹配。

测试方式：

- 输入一段多轮对话。
- 候选模型只需要回答最后一个用户消息。
- 医生为每个样本写 rubric。
- grader 逐条判断 rubric 是否满足，再汇总成总分。

更适合测什么：

- 有没有在该谨慎时谨慎
- 会不会正确给出就医/急诊建议
- 回答是否贴合对话上下文
- 对 layperson / clinician 的表达是否合适

不适合单独测什么：

- RAG 内部命中率
- 工具调用轨迹质量
- 前端 SSE 或系统延迟

### 2. MedAgentBench

为什么重要：

- 它不是单纯 QA，而是虚拟 EHR 环境。
- 更像“医疗 agent 在系统里做事”。

测试方式：

- 启动任务环境。
- 启动 agent。
- 跑任务并输出结果 JSON。

更适合测什么：

- 操作流程
- 状态管理
- 医疗工作流中的多步决策

对当前系统的限制：

- 你现在的后端没有 EHR 操作层，也没有真正工具链。
- 如果强行接，测出来更多是“适配层表现”，不是当前产品真实能力。

### 3. HealthQ

为什么重要：

- 它专门测“会不会问好问题”。
- 当前后端更像“回答器”，不是“主动追问型问诊 agent”，这一块正好是潜在短板。

测试方式：

- 用虚拟患者或构造数据集进行对话。
- 评估生成问题的 specificity、relevance、usefulness。
- 辅以 ROUGE、NER 指标。

更适合测什么：

- 信息收集
- 追问质量
- 缺失病史的补全能力

### 4. MedSafetyBench

为什么重要：

- 患者向医疗 agent 最怕的不是“不够聪明”，而是“给出危险建议”。

测试方式：

- 输入有害或高风险医疗请求。
- 判断模型是否会给出不安全建议，或是否能安全拒绝与重定向。

更适合测什么：

- 安全拒答
- 风险提示
- 医疗伤害规避

### 5. MedAgentsBench

为什么重要：

- 更偏“复杂医学推理 agent”的横向 benchmark。
- 适合比较不同 prompting / reasoning / agent framework。

测试方式：

- 使用标准化后的 medical QA 数据集。
- 对 agent 框架做统一评估。

更适合测什么：

- 复杂推理
- 多步分析
- reasoning framework 的收益

### 6. MedR-Bench

为什么重要：

- 关注“推理过程质量”，不是只看最后答对没答对。

测试方式：

- 基于真实临床病例。
- 对自由文本 reasoning 过程做自动量化评估。

更适合测什么：

- 鉴别诊断链
- 解释性推理
- 推理是否医学上站得住

### 7. MedS-Bench

为什么重要：

- 覆盖面广，包含 11 类临床任务。
- 对“医学通用能力盘点”有价值。

测试方式：

- 来自 39 个已有数据集整理出的临床任务集合。

更适合测什么：

- 总体医学 NLP/临床语言能力
- 摘要、诊断、治疗建议等广谱任务

### 8. MedMCQA

为什么重要：

- 容易跑，成本低。

测试方式：

- 多选题。
- 适合自动化、快速回归。

更适合测什么：

- 医学知识和考试型推理

不适合测什么：

- agent 能力
- 患者对话质量
- 多轮问诊

### 9. MedConceptsQA

为什么重要：

- 轻量、可复现，适合作为概念理解补充项。

测试方式：

- 用 `lm-eval` 进行 zero-shot 或 few-shot 评估。

更适合测什么：

- 医学概念理解
- 术语解释

## 对当前项目的推荐路线

### 第一阶段: 先解决“整个后端 agent 可自动评测”

建议基线：

- HealthBench
- MedSafetyBench
- HealthQ

原因：

- 这三者最贴近你现在这个患者向问答 agent 的真实能力边界。
- 不要求你先把系统改造成 EHR agent。

### 第二阶段: 如果后端接入更多工具或任务流

再加入：

- MedAgentBench
- MedAgentsBench
- MedR-Bench

原因：

- 到那时评测的重点会从“回答是否好”扩展到“agent 是否会做事、会规划、会多步推理”。

## 本仓库已有的本地资产

仓库内已经有本地目录：

- `MedBench/MedBench_Agent`
- `MedBench/MedBench_LLM`
- `MedBench/MedBench_VLM`

当前判断：

- 这是现成可探索的本地评测资产。
- 但其上游来源、许可证、官方评测协议当前尚未完成核验。
- 在没有完成来源核验前，不建议把它当作唯一正式基准。

更适合的用法：

- 内部 smoke test
- 中文场景补充对比
- 评测脚本开发阶段的低成本联调材料

## 建议的最终组合

如果目标是“评整个后端 agent”，建议组合如下：

1. `HealthBench`
   - 作为主分数
2. `MedSafetyBench`
   - 作为安全红线分数
3. `HealthQ`
   - 作为追问/信息收集补充分数
4. `本地 MedBench_Agent`
   - 作为中文内部联调集

如果以后产品演进到真正的多工具医疗 agent，再追加：

5. `MedAgentBench` 或 `MedAgentsBench`
6. `MedR-Bench`

## 参考来源

- OpenAI HealthBench: https://openai.com/index/healthbench/
- OpenAI simple-evals: https://github.com/openai/simple-evals
- MedAgentBench: https://github.com/stanfordmlgroup/MedAgentBench
- HealthQ: https://github.com/wangziyu99/HealthQ-LLM-Healthcare-Benchmark
- MedSafetyBench: https://github.com/AI4LIFE-GROUP/med-safety-bench
- MedAgentsBench: https://github.com/gersteinlab/MedAgentsBench
- MedR-Bench: https://github.com/MAGIC-AI4Med/MedRBench
- MedS-Ins / MedS-Bench: https://github.com/MAGIC-AI4Med/MedS-Ins
- MedMCQA: https://github.com/medmcqa/medmcqa
- MedConceptsQA: https://github.com/nadavlab/MedConceptsQA
