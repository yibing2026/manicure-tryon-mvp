# 美甲智能运营日报 v1

- 日期：2026-06-10
- 数据口径：official style labels + mock popularity + try-on quality report + Agent Workflow

## 今日趋势洞察

- style_12：热度 95，场景 party，风格 cool-girl，质检 pass
- style_03：热度 94，场景 party，风格 luxury，质检 pass
- style_08：热度 92，场景 party，风格 cool-girl，质检 pass
- style_24：热度 91，场景 party，风格 luxury，质检 unknown
- style_11：热度 90，场景 wedding，风格 elegant，质检 pass

## 增长预警

- style_12：增长 0.28，关键词 black, green, luxe
- style_08：增长 0.26，关键词 black, chrome, sharp
- style_03：增长 0.24，关键词 rose, dark, statement
- style_24：增长 0.23，关键词 mirror, blue, jewel
- style_09：增长 0.22，关键词 black, star, glam

## 推荐池与复查队列

- 可进入推荐池：11 款
- 需要复查：2 款
- 暂不推荐：0 款

## 今日运营动作

- 将 style_12, style_03, style_08 放入今日高热推荐位。
- 将质检为 review 的款式先进入复查队列，生成更高质量试戴图后再主推。
- 围绕高频场景和风格制作首页推荐标题与专题入口。
- 使用运营 Copilot 对 party / wedding / dating 等高价值场景分别生成活动文案。

## 风险提示

- 当前热度来自 mock 数据，仅用于 MVP 验证，不能等同真实用户行为。
- 质检 v1 是规则评估，仍需要人工抽检关键样例。
- review 款式不建议直接进入首页主推，避免用户看到低质量试戴结果。

## LLM 运营策略增强

- 状态：skipped
- 说明：Run `npm run report:ops:llm` to enable LLM strategy generation.

## 下一步执行

- 今日先上线 pass 且热度靠前的款式进入推荐池。
- 对 review 样例执行 Workflow 中建议的质量重试命令。
- 收集真实曝光、点击、试戴、收藏、预约数据，用于替换 mock 热度。
