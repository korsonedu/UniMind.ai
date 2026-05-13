# Prompt 模板抽取与版本管理系统 (Prompt Management System)

## 1. 背景与动机
随着多智能体管线（Multi-Agent Pipeline）的引入，系统中将存在大量的 Prompt。如果将这些 Prompt 硬编码（Hardcode）在 Python 文件中，会带来以下问题：
- **迭代困难**：修改 Prompt 需要重启后端服务。
- **缺乏追溯**：无法知道是哪个版本的 Prompt 导致了 AI 输出格式错乱（幻觉）。
- **无法 A/B 测试**：无法客观比较“严厉的 Reviewer Prompt”和“温和的 Reviewer Prompt”哪一个更有效。

我们需要一个 **Prompt as Code/Data** 的基建，提升 AI 管线的稳定性和可控性。

## 2. 核心架构设计

### 2.1 存储策略：数据库化 vs 文件化
我们采用 **混合存储策略 (Hybrid Storage)**：
- **开发与版本控制层 (Git)**：Prompt 模板作为 YAML/JSON 文件存储在代码库中（例如 `backend/core/prompts/`）。这保证了 Prompt 和代码一起接受 Git 版本控制。
- **运行时与动态下发层 (Database)**：系统启动时或收到 Webhook 时，将文件中的 Prompt 同步到数据库的 `PromptTemplate` 表中。运行时直接从内存/缓存读取，且允许管理员在后台页面动态微调。

### 2.2 数据模型设计 (Data Model)
```python
class PromptTemplate(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="例如: AI_QUESTION_REVIEWER")
    version = models.CharField(max_length=20, help_text="例如: v1.2.0")
    content = models.TextField(help_text="Prompt 的系统指令内容, 支持 Jinja2/F-string 变量占位符")
    agent_role = models.CharField(max_length=50, choices=[('GENERATOR', '出题者'), ('REVIEWER', '审核者'), ...])
    model_provider = models.CharField(max_length=50, default='gpt-4o')
    temperature = models.FloatField(default=0.7)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

## 3. 核心功能与工作流

### 3.1 变量注入引擎 (Variable Injection)
Prompt 不应包含具体的业务数据。必须提供标准化的变量占位符。
例如 `AI_QUESTION_GENERATOR` 模板：
```text
你是一个 431 金融考研专家。
当前的考纲知识点是：{{ knowledge_point_name }}。
请生成一道难度约为 {{ elo_target }} 的单选题。
```
在 Python 代码中，通过字典 kwargs 统一渲染。

### 3.2 灰度测试与效果回溯 (A/B Testing & Evaluation)
结合多智能体对抗系统，Prompt 管理系统可以自动收集数据：
- 如果 `Generator_v1.0` 生成的题目被 `Reviewer` 打回的概率是 40%。
- 微调 Prompt 后发布 `Generator_v1.1`，打回概率降低到 15%。
管理员可以在后台直接看到这个统计数据，从而用数据驱动 Prompt 的迭代，而不是凭感觉盲调。

## 4. 后续 AI 编码指南 (For AI Assistant)
- **提取硬编码**：全面扫描 `quizzes/ai_workflow.py`，将所有大段的三引号 `"""..."""` 字符串提取出来。
- **建立基类**：编写一个 `PromptManager` 单例类或缓存服务，封装 `get_prompt(name, version='latest')` 方法。
- **防呆设计**：当从数据库获取 Prompt 失败时，必须 Fallback 到本地默认的 YAML 文件，保证服务不宕机。
