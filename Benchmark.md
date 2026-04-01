# 医疗 Agent 测试数据集分类与详细信息（2026 年 4 月最新版）

作者：Grok 团队（基于 GitHub、arXiv、项目官网实时验证）  
更新时间：2026 年 4 月

## 说明

以下覆盖此前汇总的核心医疗 Agent 基准：

- MedAgentBench
- AgentClinic
- MedAgentBoard
- MedAgentsBench
- HealthBench
- MedBench v4
- FHIR-AgentBench

分类依据：

- 是否开源：代码和数据是否在 GitHub / Hugging Face 公开
- 是否支持本地部署使用：是否可通过 Docker、脚本、`pip`、HF 等方式本地运行

传统数据集（如 MedQA、PubMedQA、MIMIC-IV）虽然可适配 Agent，但并非专用 Agent 基准，因此仅在“其他”部分简要提及。以下链接均为公开可用。

## 分类概述

| 数据集名称 | 是否开源 | 是否本地部署 | 主要入口 / 下载 | 数据规模 | 主要评估指标 | 推荐优先级 |
| --- | --- | --- | --- | --- | --- | --- |
| MedAgentBench (Stanford) | 是（MIT） | 是（Docker） | GitHub + 项目页 | 100 患者 / 300 任务 / 78 万+记录 | Success Rate（整体 / 查询 / 动作） | ★★★★★（EHR 首选） |
| AgentClinic | 是（MIT） | 是（Python） | GitHub + 网站 | 约 335 病例（MedQA + NEJM） | 诊断准确率、交互质量、偏置鲁棒性 | ★★★★☆（多模态对话） |
| MedAgentBoard | 是 | 是（Python / uv） | GitHub + 网站 | 多任务（MedQA、MIMIC 等） | 准确率、ROUGE、AUROC、专家评估 | ★★★★☆（多代理协作） |
| MedAgentsBench (Gerstein) | 是（MIT） | 是（HF + 脚本） | GitHub + HF | 约 894 个高难问题 | 复杂推理准确率、错误分析 | ★★★★（硬推理） |
| FHIR-AgentBench | 是（CC-BY） | 是（Python + GCP 本地模拟） | GitHub | 2,931 临床问题 | FHIR 检索 Recall / Precision + 答案正确性 | ★★★★（FHIR / EHR 查询） |
| HealthBench (OpenAI) | 是（eval 框架） | 是（eval 脚本） | GitHub + Blob | 5,000 多轮对话 + 48,562 rubric | 加权 rubric 得分（准确性、安全性） | ★★★★（真实咨询） |
| MedBench v4（中文） | 部分（平台） | 否（云平台） | 云平台 | 70 万+任务（24 科、91 亚科） | Agent 轨道得分（最高 85.3） | ★★★★★（中文 / 监管） |

## 1. 完全开源 + 支持本地部署

推荐优先用于本地测试。

### MedAgentBench

副标题：Stanford，最真实 EHR Agent 基准

- 开源：是（MIT License）
- 本地部署：是（Docker + Conda / Python 3.9）
- 入口网站：https://stanfordmlgroup.github.io/projects/medagentbench/
- GitHub 与下载：https://github.com/stanfordmlgroup/MedAgentBench
- 数据目录：`data/medagentbench/`
- 参考答案（`refsol.py`）：https://stanfordmedicine.box.com/s/fizv0unyjgkb1r3a83rfn5p3dc673uho

数据集测试信息：

- 规模：100 份真实去标识患者档案，包含 785,207 条记录（Lab、Vital、Procedure、Diagnosis、Medication）
- 任务：300 个执业医师编写的临床任务，覆盖 10 大类别，如数据检索、检验订购、药物管理
- 环境：FHIR-compliant 虚拟 EHR，可通过 Docker 本地运行
- 评估：Success Rate（整体 / 查询 / 动作），支持 GPT-4o、Claude 等 API 或本地模型
- 运行方式：

```bash
docker run FHIR server
python -m src.start_task
python -m src.assigner
```

- 输出：JSON 结果
- 性能示例：Claude 3.5 Sonnet 达到 69.67%

### AgentClinic

副标题：多模态临床模拟基准

- 开源：是（MIT）
- 本地部署：是（`pip install -r requirements.txt` + Python 脚本）
- 入口网站：https://agentclinic.github.io/
- GitHub 与下载：https://github.com/SamuelSchmidgall/AgentClinic
- 数据文件：`agentclinic_medqa.jsonl`、`agentclinic_nejm.jsonl`（含扩展版）

数据集测试信息：

- 规模：AgentClinic-MedQA 215 病例；AgentClinic-NEJM 120 个多模态病例
- 任务：Patient / Doctor / Moderator 多代理交互 + 工具调用 + 24 种偏置模拟
- 评估：诊断准确率、交互次数、偏置鲁棒性、信心度
- 运行方式：

```bash
python agentclinic.py --openai_api_key YOUR_KEY --inf_type llm
```

- 支持：本地 HF 模型，或 OpenAI / Replicate

### MedAgentBoard

副标题：多代理协作全面基准

- 开源：是（代码、prompts、结果全部开源）
- 本地部署：是（`uv sync` + Python 3.10+，支持本地 LLM）
- 入口网站：https://medagentboard.netlify.app/
- GitHub 与下载：https://github.com/yhzhu99/medagentboard
- 补充说明：数据与 prompts 含 Google Drive 链接

数据集测试信息：

- 4 大任务：
  - Medical (Visual) QA
  - Lay Summary 生成
  - EHR 预测建模
  - 临床工作流自动化
- 数据源：MedQA、PubMedQA、PathVQA、Cochrane、MIMIC-IV（PhysioNet 需申请）、TJH Hospital
- 评估：准确率、ROUGE-L / SARI、AUROC / AUPRC、专家评估
- 运行方式：

```bash
bash medqa/run.sh
python -m medagentboard.xxx
```

### MedAgentsBench

副标题：复杂医学推理基准

- 开源：是（MIT）
- 本地部署：是（HF + `requirements.txt` + 脚本）
- 入口：无独立网站，见 arXiv 2503.07459
- GitHub 与下载：https://github.com/gersteinlab/medagents-benchmark
- Hugging Face 数据集：https://huggingface.co/datasets/super-dainiu/medagents-benchmark

加载示例：

```python
load_dataset("super-dainiu/medagents-benchmark", "MedQA")
```

数据集测试信息：

- 规模：约 894 道 hard 问题，来自基座模型准确率低于 50% 的子集
- 来源：MedQA、PubMedQA、MedMCQA、MMLU-Pro、MedXpertQA 等过滤得到
- 评估：多步推理准确率、思考模型表现、Agent 框架对比
- 运行方式：

```bash
./run_experiments_all.sh
```

- 分析文件：`misc.ipynb`

### FHIR-AgentBench

副标题：FHIR 互操作 EHR Agent 基准

- 开源：是（CC-BY-4.0）
- 本地部署：是（Python + vLLM 本地模型 + GCP FHIR 模拟）
- 入口：arXiv 2509.19319
- GitHub 与下载：https://github.com/glee4810/FHIR-AgentBench
- MIMIC-IV FHIR Demo：https://physionet.org/content/mimic-iv-fhir-demo/2.1.0/

数据集测试信息：

- 规模：2,931 个真实临床问题（基于 MIMIC-IV FHIR）
- 任务：FHIR 资源检索 + 自然语言推理
- 评估：检索 Recall / Precision + 答案正确性（`evaluation_metrics.py`）
- 运行方式：

```bash
配置 config.yml
运行 Agent
python evaluation_metrics.py
```

## 2. 开源评估框架 + 数据公开可访问

### HealthBench

副标题：OpenAI 真实健康对话基准

- 开源：是（eval 框架 + 数据）
- 本地部署：是（standalone eval 脚本，支持本地模型适配）
- 入口网站：https://openai.com/index/healthbench/
- GitHub 与下载：https://github.com/openai/simple-evals
- 数据 JSONL（Eval / Hard / Consensus）：https://openaipublic.blob.core.windows.net/simple-evals/healthbench/
- 补充：也可使用社区 Hugging Face 镜像

数据集测试信息：

- 规模：5,000 多轮真实对话，覆盖 49 种语言、26 个专科
- 标注：48,562 条医师 rubric
- 任务：多轮咨询、安全性、实用性
- 评估：基于 GPT-4.1 的自动 rubric 打分（加权总分）
- 运行方式：

```bash
python -m simple-evals.healthbench_eval
```

- 支持：本地 LLM

## 3. 云平台为主（非完全本地部署）

### MedBench v4

副标题：中文最大规模医疗基准

- 开源：部分（平台与论文公开，无完整本地数据集 dump）
- 本地部署：否（云提交式评测）
- 入口网站：https://medbench.opencompass.org.cn/
- 备用入口：arXiv 2511.14439

数据集测试信息：

- 规模：70 万+专家标注任务，覆盖 24 大科、91 个亚科
- 轨道：LLM / 多模态 / Agent 专用轨道
- 参考成绩：平均 79.8 分，Claude-based 最高 85.3 分
- 评估：对齐中国临床指南 + 安全性（88.9）
- 使用方式：云平台注册提交答案或通过 API 评测
- 推荐场景：中文 Agent 优先

## 其他重要基准

简要补充，自 Awesome 列表提取。

- LiveMedBench / MedConsultBench / MedInsightBench / CP-Env：均有 arXiv 公开论文，多数提供 GitHub 代码并可本地运行，但数据规模较小或需要申请。详见：https://github.com/AgenticHealthAI/Awesome-AI-Agents-for-Healthcare
- 传统适配数据集：MedQA（Hugging Face）、MIMIC-IV（PhysioNet）、CBLUE（天池）均可本地使用，但需要自行构建 Agent 环境

## 全面资源入口

- Awesome-AI-Agents-for-Healthcare：https://github.com/AgenticHealthAI/Awesome-AI-Agents-for-Healthcare
- 收录情况：20+ 基准索引

## 建议

- 优先从 MedAgentBench（真实 EHR）和 MedBench v4（中文 Agent）入手
- 大多数项目支持 `pip` / `conda` + Docker，通常几分钟内可启动
- 注意 API 密钥要求（如 OpenAI / Claude）或本地 vLLM 部署前置条件
- 评估重点建议关注：成功率、hallucination、安全性、多轮完整性

## 后续可补充内容

如果需要，我可以继续补充以下内容：

- 单个数据集的完整运行脚本
- 性能对比 Excel
- Docker 一键部署包
- 某个基准的更多细节，例如 LiveMedBench
