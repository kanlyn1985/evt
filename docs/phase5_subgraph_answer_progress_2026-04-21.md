# Phase 5 子图驱动答案进展

## 本轮目标

把 `knowledge_subgraph` 从查询上下文里的统计摘要，推进成答案层真正消费的对象。

## 本轮完成

1. `query_api.build_query_context()` 生成的 `knowledge_subgraph` 已补充：
   - `seed_fact_ids`
   - `seed_edge_ids`
   - `wiki_page_types`

2. `answer_api.answer_query()` 已在答案前对 facts 做子图信号标注：
   - `seed_fact_ids` 命中加权
   - `seed_entity_ids` 关联加权
   - `wiki source facts` 加权
   - `wiki_page_types` 与意图一致性加权

3. `_select_answer_facts()` 不再只做参数特化，已扩成：
   - `parameter` -> 参数型子图优先
   - `process` -> `transition_fact / process_fact` 优先
   - `definition` -> `term_definition / concept_definition` 优先

4. `definition` 类问题增加 wiki 主题页兜底：
   - 当 facts 不足时，从 wiki markdown 页的 `## 定义` 段提取答案

5. `constraint / comparison` 已接入统一答案事实选择：
   - `constraint` -> `threshold / requirement / table_requirement` 优先
   - `comparison` -> `comparison_relation` 优先

6. 已新增统一知识主链回归：
   - [tests/generated/knowledge_chain_regression_cases_2026-04-21.json](E:/AI_Project/opencode_workspace/KB1/tests/generated/knowledge_chain_regression_cases_2026-04-21.json)
   - [scripts/run_knowledge_chain_regression.py](E:/AI_Project/opencode_workspace/KB1/scripts/run_knowledge_chain_regression.py)
   - [docs/knowledge_chain_regression_report_2026-04-21.json](E:/AI_Project/opencode_workspace/KB1/docs/knowledge_chain_regression_report_2026-04-21.json)

7. graph relation 已开始直接参与答案侧返回：
   - `has_constraint`
   - `has_comparison`
   - 当 `query_context` 未带出 graph edges 时，答案层会按最终答案 facts 回补相关 graph edges

8. `requirement / threshold` 已新增知识对象字段：
   - `topic`
   - `scope_type`
   当前 `scope_type` 至少区分：
   - `index`
   - `preface`
   - `overview`
   - `appendix_rule`
   - `normative_requirement`
   - `general_requirement`

## 当前效果

- `CC阻值`
  - 已由参数子图驱动答案选择
  - 能返回控制导引相关阻值集合

- `CP时序`
  - 已由 process 子图驱动答案选择
  - 能优先返回 `transition_fact`

- `V2G的定义是什么`
  - 当 facts 未回流时，能用 wiki 页兜底返回定义

- `急停有什么要求`
  - 已由 `constraint` 类型事实优先回答

- `V2X包括哪些类型`
  - 已由 `comparison_relation` 事实优先回答
  - 并可返回 `has_comparison` graph edge

- `急停有什么要求`
  - 现在除 requirement facts 外，也可返回 `has_constraint` graph edge
  - requirement / threshold 已开始带 `topic + scope_type`

## 当前判断

Phase 5 已从“子图存在”推进到“子图参与答案选择”。

系统主链当前更接近：

`query -> wiki -> graph -> facts -> answer`

但还没有彻底完成下面两件事：

1. graph edge 目前已经能参与答案侧返回，但还没有深度参与“事实裁剪”。
2. confidence 还没有把 wiki-fallback definition 计入单独置信逻辑。
3. `constraint / comparison` 目前已能稳定回答，但尚未像 parameter/process 一样形成稳定的 wiki/graph 子图入口。
4. `constraint` 现在已具备 topic/scope 对象化基础，但答案层还需要进一步利用 `topic` 做强约束，而不是只做加权。

## 下一步建议

1. 把 `constraint / comparison` 也接入同一套子图优先答案选择。
2. 让 graph edge relation type 真正参与答案裁剪，而不只是做背景信号。
3. 补一套统一的“知识主链回归集”，覆盖：
   - definition
   - parameter
   - process
   - constraint
   - comparison
