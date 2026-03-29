# New API 平台运营技术方案与商业分析

## 一、项目概述

### 1.1 项目定位

New API 是一个**统一的 LLM API 网关 + AI 资产管理系统**。核心价值是让用户只需对接一套 API，就能调用 30+ 家大模型供应商的服务，同时提供计费、权限、负载均衡等企业级管理能力。

### 1.2 开源溯源

```
One API (JustSong, MIT License)
    └── New API (QuantumNous, AGPLv3 License)
            └── aipaibox.com 等商业化实例
```

New API 在 One API 基础上增加了：新 UI（Semi UI）、数据看板、Claude/Gemini 格式互转、Responses API、视频生成任务系统、订阅计费、多种 OAuth、国际化等大量功能。数据库完全兼容 One API，可以无缝迁移。

### 1.3 技术栈

| 层 | 技术 |
|---|---|
| 后端语言 | Go |
| Web 框架 | Gin |
| ORM | GORM（支持 SQLite / MySQL / PostgreSQL） |
| 缓存 | Redis（可选内存缓存） |
| 前端 | React + Semi UI（字节跳动） + Vite |
| 部署 | Docker / Docker Compose |
| 性能分析 | Pyroscope / pprof |

---

## 二、核心技术架构

### 2.1 Adaptor 适配器模式

整个项目最核心的技术设计。`relay/channel/adapter.go` 定义了统一的 Adaptor 接口：

```go
Adaptor interface {
    GetRequestURL()              // 构造上游请求地址
    SetupRequestHeader()         // 设置认证头
    ConvertOpenAIRequest()       // OpenAI 格式转换
    ConvertClaudeRequest()       // Claude 格式转换
    ConvertGeminiRequest()       // Gemini 格式转换
    ConvertImageRequest()        // 图片请求转换
    ConvertEmbeddingRequest()    // Embedding 请求转换
    DoRequest() / DoResponse()   // 执行请求并处理响应
}
```

每个供应商实现自己的 Adaptor，共 **40+ 个适配器**，覆盖：
- OpenAI、Claude、Gemini、DeepSeek、通义千问(Ali)、文心一言(Baidu)、讯飞、智谱、腾讯混元
- AWS Bedrock、Azure、Vertex AI、Cloudflare Workers AI
- Ollama、Cohere、Mistral、Perplexity、xAI、Coze、MiniMax、Replicate 等

### 2.2 请求处理流水线

```
用户请求 → TokenAuth(鉴权) → ModelRateLimit(限流) → Distribute(选渠道) → Relay(转发)
                                                          │
                                                   根据模型+权重+优先级
                                                   选择最佳渠道(Channel)
                                                          │
                                               GetAdaptor(apiType) → 具体适配器
                                                          │
                                               格式转换 → 发请求 → 处理响应 → 计费
```

### 2.3 核心数据模型

| 模型 | 作用 |
|---|---|
| Channel | 上游渠道（API Key + 供应商类型 + 支持的模型列表 + 权重/优先级） |
| Token | 用户 API Key（配额、模型限制、IP 白名单、分组） |
| User | 用户账户（余额、角色、OAuth 绑定） |
| Pricing | 模型定价（输入/输出/缓存比率，分组定价） |
| Ability | 渠道能力映射（Group × Model × ChannelId，含优先级和权重） |
| Log | 调用日志（模型、Token 用量、耗时、渠道） |
| Task | 异步任务（Midjourney/Suno/视频生成等长时间任务） |

### 2.4 主要功能模块

1. **API 代理转发** — 支持 Chat、Responses、Image、Audio、Embedding、Rerank、Realtime 等全部 OpenAI 接口
2. **异步任务系统** — Midjourney 绘图、Suno 音乐、Kling/海螺/Sora 视频生成，通过轮询获取结果
3. **计费系统** — 按 Token 用量计费，支持缓存计费、图片/音频独立比率、订阅制
4. **支付系统** — EPay、Stripe、Creem、微信对接
5. **OAuth 登录** — Discord、LinuxDO、Telegram、OIDC、微信、自定义 OAuth
6. **渠道管理** — 自动测速、自动禁用、上游模型同步、余额查询
7. **国际化** — 中/英/法/日 多语言

---

## 三、渠道选择与负载均衡机制

### 3.1 缓存数据结构

```go
group2model2channels: map[group] → map[model] → []channelId   // 启用的渠道索引
channelsIDM:          map[channelId] → *Channel                // 全部渠道详情
```

Ability 表是桥梁，联合主键为 `(Group, Model, ChannelId)`，每条记录带有 Priority（优先级）和 Weight（权重）。

### 3.2 初始化过程 (InitChannelCache)

1. 从数据库加载全部 Channel 和 Ability 记录
2. 构建 `group → model → []channelId` 的三级映射（只包含 enabled 的渠道）
3. 每个 model 下的 channelId 列表按 Priority 降序排序
4. 定时同步（SyncChannelCache，默认每隔 N 秒从数据库重新加载）

### 3.3 选择算法 (GetRandomSatisfiedChannel)

**第一步：查找候选渠道**

```go
channels = group2model2channels["default"]["gpt-4o"]
// 得到: [channelId: 5, 3, 8, 12, 1] (已按 priority 降序排列)
```

**第二步：按 Priority 分层**

```
Priority 100: channel 5, channel 3     ← retry=0 用这组
Priority 50:  channel 8, channel 12    ← retry=1 用这组
Priority 0:   channel 1                ← retry=2 用这组
```

retry 值作为索引选择优先级层：
- retry=0 → 最高优先级
- retry=1 → 次高优先级
- retry >= 优先级总数 → 退回最低优先级

**第三步：同一优先级内，按 Weight 加权随机**

```go
// priority=100 层:
// channel 5: weight=80, channel 3: weight=20
totalWeight = 100
randomWeight = rand(0, 100)
// 权重越大被选中概率越高
```

平滑处理：
- 所有权重为 0 → 每个渠道等概率（各加 100）
- 平均权重 < 10 → 乘以 100 放大，减少随机偏差

### 3.4 渠道亲和性 (Channel Affinity)

请求成功后记录 `(key_value → channel_id)` 映射，带 TTL（默认 3600 秒）。下次相同客户请求时优先复用同一渠道。

支持的 Key 提取方式：
- `context_int` — 从上下文取整数（如 user_id、token_id）
- `context_string` — 从上下文取字符串
- `gjson` — 从请求 body 中用 JSON Path 提取值

亲和性对以下场景至关重要：
- **Prompt Caching** — 同一账号连续请求才能命中缓存
- **Codex --resume** — previous_response_id 绑定特定账号
- **成本优化** — 缓存命中率直接影响利润

### 3.5 重试机制

```
首次请求: retry=0 → Priority 最高层 → 加权随机选一个
第1次重试: retry=1 → Priority 次高层 → 加权随机选一个
第2次重试: retry=2 → Priority 第三层 → ...
```

Auto 分组跨组重试：每个分组穷尽所有优先级后才轮到下一个分组。

### 3.6 完整流程图

```
请求 model=gpt-4o
        │
        ▼
  ① 亲和性缓存命中？ ──yes──▶ 直接使用上次成功的渠道
        │no
        ▼
  ② 从 group2model2channels["default"]["gpt-4o"] 取候选列表
        │
        ▼
  ③ 按 Priority 去重降序排列，用 retry 值选择优先级层
        │
        ▼
  ④ 同层内按 Weight 加权随机选中一个渠道
        │
        ▼
  ⑤ 请求成功 → 记录亲和性，下次优先用
     请求失败 → retry++ → 回到 ③ 降一级优先级重选
```

---

## 四、Prompt Caching 与渠道亲和性

### 4.1 OpenAI Prompt Caching

- **自动触发**：前缀 ≥ 1024 tokens 完全相同即可命中
- **粒度**：以 128 tokens 递增匹配
- **条件**：同一 API Key / Organization
- **TTL**：约 5-10 分钟，高频使用可保持更久
- **折扣**：缓存命中 token 约 50% off

### 4.2 Claude Prompt Caching

- **显式标记**：需要在请求中设置 `cache_control`
- **TTL**：5 分钟（ephemeral）
- **写入成本**：高于普通输入（约 1.25x）
- **读取折扣**：约 90% off

### 4.3 跨命令缓存生效条件

| 场景 | 是否命中缓存 |
|------|-------------|
| 相同系统提示，不同用户指令 | 命中 — 共享前缀被缓存 |
| 两次命令间隔 > 10 分钟 | 可能失效 — 缓存过期 |
| 系统提示本身变了 | 不命中 — 前缀变了 |
| 共享前缀 < 1024 tokens | 不命中 — 太短 |
| 亲和性 TTL 过期，换了渠道 | 不命中 — 不同 API Key |

### 4.4 亲和性配置建议

- 亲和性 TTL ≥ 工作时长（如设 4 小时）
- 系统提示尽量稳定
- 命令间隔控制在 5-10 分钟内

---

## 五、Codex 支持

### 5.1 Codex 渠道特点

- 走 ChatGPT 的 `/backend-api/codex/responses` 接口，不是 OpenAI 官方 API
- Key 不是 `sk-` API Key，而是 OAuth JSON 对象（含 access_token、account_id、refresh_token）
- 只支持 `/v1/responses` 和 `/v1/responses/compact` 端点
- 支持模型：gpt-5、gpt-5-codex、gpt-5-codex-mini、gpt-5.1-codex 等

### 5.2 `--resume` 支持

平台支持 `codex --resume`，通过 `previous_response_id` 字段透传实现。

**关键前提**：必须配置 Channel Affinity，确保同一客户的请求始终路由到同一个 Codex 账号，否则 `previous_response_id` 在其他账号上找不到。

---

## 六、计费系统

### 6.1 计费架构

```
客户 ←──── New API 计费（向客户收费）────→ 平台运营方
                    │
                    ▼
         OpenAI/Claude 官方计费（实际成本）
```

两套独立体系，平台在中间赚差价或做成本管控。

### 6.2 计费公式

**模式1：倍率模式（Ratio，默认）**

```
最终费用 = (输入Token × 1
         + 输出Token × 补全倍率
         + 缓存命中Token × 缓存倍率
         + 缓存创建Token × 缓存创建倍率
         + 图片Token × 图片倍率
         + 音频Token × 音频倍率)
         × 模型倍率 × 分组倍率
```

基准单位：1 = $0.002 / 1K tokens（USD = 500）

**模式2：固定价格模式（Price）**

```
最终费用 = 模型固定价格 × 分组倍率
```

### 6.3 主要模型倍率参考

| 模型 | 模型倍率 | 对应官方输入价 |
|------|---------|-------------|
| gpt-4o | 1.25 | $2.5/M tokens |
| gpt-4o-mini | 0.075 | $0.15/M tokens |
| gpt-4.1 | 1.0 | $2/M tokens |
| gpt-5 | 0.625 | $1.25/M tokens |
| o3 | 1.0 | $2/M tokens |
| o3-pro | 10.0 | $20/M tokens |
| claude-sonnet-4 | 1.5 | $3/M tokens |
| claude-opus-4 | 7.5 | $15/M tokens |
| deepseek-chat | 极低 | ¥1/M tokens |
| gemini-2.5-pro | 0.625 | $1.25/M tokens |
| gemini-2.5-flash | 0.15 | $0.3/M tokens |

### 6.4 计费生命周期

```
请求进来
    │
    ▼
① 预扣费 (PreConsumeTokenQuota)
    检查用户余额和 Token 余额是否足够
    先扣一笔预估费用（防止透支）
    │
    ▼
② 转发到上游 OpenAI/Claude
    │
    ▼
③ 上游返回 usage（实际 token 消耗）
    │
    ▼
④ 结算 (PostConsumeQuota / PostTextConsumeQuota)
    根据实际 usage 计算真实费用
    与预扣费的差额多退少补
    支持钱包扣费或订阅额度扣费
    │
    ▼
⑤ 记录日志 (RecordConsumeLog)
    记录：用户、渠道、模型、token数、费用、耗时
    │
    ▼
⑥ 余额预警 (checkAndSendQuotaNotify)
    余额低于阈值时通知用户（邮件/Bark/Gotify/Webhook）
```

### 6.5 缓存计费详情

系统精确跟踪 prompt caching 的各种 token：

| Token 类型 | 说明 | 对应倍率 |
|-----------|------|---------|
| CacheTokens | 缓存命中的 token（便宜） | CacheRatio (默认 0.5) |
| CacheCreationTokens | 缓存写入的 token（贵） | CacheCreationRatio (默认 1.25) |
| CacheCreationTokens5m | Claude 5分钟TTL缓存写入 | CacheCreationRatio5m |
| CacheCreationTokens1h | Claude 1小时TTL缓存写入 | CacheCreationRatio1h |

---

## 七、服务器配置方案（100 用户）

### 7.1 资源消耗特征

New API 本质是反向代理，不做 AI 推理，瓶颈主要在网络 I/O 和数据库写入。

### 7.2 配置推荐

**基础方案（日常使用）**

| 组件 | 配置 | 说明 |
|------|------|------|
| CPU | 2 核 | Go 协程高效，代理转发不吃 CPU |
| 内存 | 4 GB | 渠道缓存 + Redis + 流式连接缓冲 |
| 硬盘 | 40 GB SSD | 数据库 + 日志 |
| 带宽 | 5-10 Mbps | 主要瓶颈，流式响应吃带宽 |
| 数据库 | SQLite | 100 用户够用 |
| Redis | 可选 | 建议上，用于亲和性缓存 |
| 云服务器 | 阿里云/腾讯云 2C4G 轻量 | 约 100-200 元/月 |

**高频方案（Codex 重度编码场景）**

| 组件 | 配置 | 说明 |
|------|------|------|
| CPU | 4 核 | 流式 SSE 并发多时需要 |
| 内存 | 8 GB | 每个流式连接占缓冲区 |
| 硬盘 | 80 GB SSD | 日志量大 |
| 带宽 | 20-30 Mbps | 100 路流式同时跑，最关键瓶颈 |
| 数据库 | PostgreSQL/MySQL | 高频写日志时 SQLite 可能瓶颈 |
| Redis | 必须 | 亲和性 + 渠道缓存 + 限流 |
| 云服务器 | 4C8G | 约 200-400 元/月 |

### 7.3 瓶颈优先级

```
带宽（高）◀── 最大瓶颈！100路流式输出并行，峰值需 20+ Mbps
内存（中）──── 每个流式连接读写缓冲，默认 64MB 上限/连接
数据库（中）── 每次请求写一条日志，开 BATCH_UPDATE 缓解
CPU（低）──── 只做 JSON 转换和路由选择
磁盘（低）──── 日志和数据库，定期清理
```

### 7.4 Docker Compose 配置参考

```yaml
services:
  new-api:
    image: calciumion/new-api:latest
    environment:
      - SQL_DSN=postgresql://root:password@postgres:5432/new-api
      - REDIS_CONN_STRING=redis://redis
      - BATCH_UPDATE_ENABLED=true    # 批量写库减少 DB 压力
      - STREAMING_TIMEOUT=300        # Codex 会话长，超时设大
      - STREAM_SCANNER_MAX_BUFFER_MB=64
      - TZ=Asia/Shanghai
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
```

### 7.5 扩容指标

| 指标 | 预警值 | 应对 |
|------|-------|------|
| CPU 持续 > 70% | 扩核 | 很少发生 |
| 内存 > 80% | 加内存 | 流式连接多时可能 |
| 带宽打满 | 升带宽或多节点 | 最先遇到的瓶颈 |
| 数据库慢查询 | 换 MySQL/PG | SQLite 在 200+ QPS 时会卡 |
| 客户数 > 500 | 多节点部署 | 加 SESSION_SECRET + Redis |

---

## 八、上游账号规划（100 用户）

### 8.1 OpenAI API 账户等级

| Tier | 充值门槛 | RPM | TPM (gpt-4o) | 适合规模 |
|------|---------|-----|-------------|---------|
| Tier 1 | $5 | 500 | 30,000 | 10 人以下 |
| Tier 2 | $50 | 5,000 | 450,000 | 30-50 人 |
| Tier 3 | $100 | 5,000 | 800,000 | 50-80 人 |
| Tier 4 | $250 | 10,000 | 2,000,000 | 100-200 人 |
| Tier 5 | $1,000+ | 10,000 | 30,000,000 | 500+ 人 |

**推荐方案**

方案 A（单账号）：1 个 Tier 4 账号（充值 $250+），管理简单，prompt caching 效果最好。

方案 B（多账号分流）：3 个 Tier 2 账号（各充 $50+），总 RPM 15,000，单号挂了不影响全部，但 caching 分散。

### 8.2 Claude API 账户等级

| Tier | 充值门槛 | RPM | TPM (Sonnet) |
|------|---------|-----|-------------|
| Tier 1 | $5 | 50 | 40,000 |
| Tier 2 | $40 | 1,000 | 80,000 |
| Tier 3 | $200 | 2,000 | 160,000 |
| Tier 4 | $400 | 4,000 | 400,000 |

Claude RPM 限制比 OpenAI 严格得多，单账号不够。

**推荐**：2-3 个 Tier 3 或 Tier 4 账号轮换。

### 8.3 Codex 场景

Codex 渠道走 ChatGPT OAuth，不是 API Key：
- 需要多个 ChatGPT Plus/Pro 账号（$20-200/月/个）
- 建议 5-10 个账号轮换
- 必须配 Channel Affinity 保证 --resume 正常

### 8.4 综合渠道配置

```
OpenAI 渠道:
├── 渠道1: Tier 4 主号     权重80  优先级100
├── 渠道2: Tier 2 备号     权重20  优先级100
└── 渠道3: Azure 备用      权重50  优先级50

Claude 渠道:
├── 渠道4: Tier 3 账号A    权重50  优先级100
├── 渠道5: Tier 3 账号B    权重50  优先级100
└── 渠道6: Tier 2 备号     权重30  优先级50

Codex 渠道:
├── 渠道7: ChatGPT 账号1   权重30  优先级100
├── 渠道8: ChatGPT 账号2   权重30  优先级100
└── ...5-10 个账号轮换
```

### 8.5 月固定成本估算

| 项目 | 数量 | 单价 | 月费 |
|------|------|------|------|
| OpenAI Tier 4 | 1 个 | 按用量，预充 $250 | 按实际消耗 |
| OpenAI Tier 2 备号 | 1 个 | 预充 $50 | 按实际消耗 |
| Claude Tier 3 | 2 个 | 各预充 $200 | 按实际消耗 |
| ChatGPT Plus (Codex) | 5-10 个 | $20/月 | $100-200/月 |
| 云服务器 4C8G | 1 台 | ≈ ¥300/月 | ¥300/月 |
| 固定成本合计 | | | ≈ $150-250/月 |
| API 消耗（变动） | 100 人 | 取决于使用量 | $500-5000/月 |

---

## 九、30% 毛利润定价策略

### 9.1 成本结构

```
总成本 = API 调用成本（变动，占 90%+）+ 固定成本（服务器/账号，占 5-10%）
```

### 9.2 定价核心公式

```
30% 毛利 → 售价 = 成本 ÷ (1 - 30%) = 成本 × 1.43
```

### 9.3 分组倍率设置

```json
{
  "default":  1.5,     // 普通用户：50% 加价（含固定成本摊销）
  "vip":      1.35,    // VIP 用户：35% 加价
  "svip":     1.25,    // 大客户：25% 加价（量大走量）
  "internal": 1.0      // 内部使用：成本价
}
```

### 9.4 模型倍率策略

保持默认模型倍率（与官方价格对齐），利润全部通过分组倍率实现。

可选微调：
| 模型 | 默认倍率 | 调整建议 | 原因 |
|------|---------|---------|------|
| gpt-4o | 1.25 | 保持 | 主力模型，对标市场价 |
| gpt-4o-mini | 0.075 | 保持 | 低价引流 |
| claude-sonnet-4 | 1.5 | 保持 | 和市场一致 |
| claude-opus-4 | 7.5 | 可调到 8.0 | 高端用户价格不敏感 |
| o3-pro | 10.0 | 可调到 11.0 | 同上 |
| deepseek 系列 | 很低 | 保持 | 价格优势引流 |

### 9.5 缓存倍率 — 隐性利润来源

这是关键利润点。官方对缓存命中打折，但平台不必完全传递给用户：

| 供应商 | 官方缓存折扣 | 默认缓存倍率 | 建议设置 | 利润差 |
|--------|------------|------------|---------|-------|
| OpenAI | 50% off | 0.5 | 0.7 | 吃 20% 差价 |
| Claude | 90% off | 0.1 | 0.3 | 吃 20% 差价 |
| Gemini | 75% off | 0.25 | 0.4 | 吃 15% 差价 |

示例计算：
```
OpenAI 缓存 token:
  你从 OpenAI 买: 0.5 × 原价
  你卖给用户:     0.7 × 原价 × 1.5(分组倍率) = 1.05 × 原价
  利润 = 1.05 - 0.5 = 0.55 × 原价 → 毛利率 52%

缓存命中越多，实际利润率远超 30%
```

### 9.6 面向客户的定价表（普通用户 default 分组）

以 ¥ / 百万 tokens 为单位：

| 模型 | 官方价格 | 售价 (×1.5) | 成本 | 毛利率 |
|------|---------|------------|------|-------|
| gpt-4o 输入 | ¥18.25 | ¥27.4 | ¥18.25 | 33% |
| gpt-4o 输出 | ¥73.0 | ¥109.5 | ¥73.0 | 33% |
| gpt-4o 缓存命中 | ¥9.1 | ¥19.2 | ¥9.1 | 53% |
| claude-sonnet 输入 | ¥21.9 | ¥32.9 | ¥21.9 | 33% |
| claude-sonnet 输出 | ¥109.5 | ¥164.3 | ¥109.5 | 33% |
| claude-sonnet 缓存命中 | ¥2.19 | ¥9.86 | ¥2.19 | 78% |
| gpt-4o-mini 输入 | ¥1.1 | ¥1.6 | ¥1.1 | 33% |
| deepseek-v3 输入 | ¥1.8 | ¥2.7 | ¥1.8 | 33% |

### 9.7 利润测算模型

假设 100 用户月消耗 $3,000 上游 API 费用：

```
上游 API 成本:
  普通 token 成本: $2,100
  缓存 token 成本 (占 30%): $900 × 0.5(官方折扣) = $450
  实际上游成本: $2,550

平台收入:
  普通 token 收入: $2,100 × 1.5 = $3,150
  缓存 token 收入: $900 × 0.7 × 1.5 = $945
  总收入: $4,095

固定成本: $145

毛利 = $4,095 - $2,550 - $145 = $1,400
毛利率 = $1,400 / $4,095 = 34.2%
```

### 9.8 New API 后台配置汇总

```
运营设置 → 分组倍率:
{"default": 1.5, "vip": 1.35, "svip": 1.25, "internal": 1.0}

运营设置 → 缓存倍率（调高吃差价）:
{"gpt-4o": 0.7, "claude-sonnet-4": 0.3, "claude-opus-4": 0.3, "gemini-2.5-pro": 0.4}

运营设置 → 缓存创建倍率:
保持官方一致或微调（Claude 写缓存 1.25 → 保持或调到 1.3）

运营设置 → 额度显示:
QuotaDisplayType: "CNY"（人民币显示更直观）
```

---

## 十、运营关键动作

### 10.1 技术层面

1. **必须配 Channel Affinity** — 缓存命中率从 0% 提到 30-50%，直接多赚 5-10% 毛利
2. **设置用户限流** — 防止单用户打满上游 RPM 影响其他人
3. **开启 BATCH_UPDATE** — 减少数据库写入压力
4. **定期对账** — 对比 OpenAI/Claude 账单和 New API 日志消耗

### 10.2 商业层面

1. **月初预充值机制** — 让用户先充值再使用，保证现金流
2. **Codex 用户单独定价** — ChatGPT 账号是固定月费，可按月订阅收费
3. **分组差异化** — VIP 客户给折扣换忠诚度
4. **充值档位折扣** — 利用 AmountDiscount 配置，大额充值给优惠

### 10.3 监控指标

| 指标 | 关注点 |
|------|-------|
| 缓存命中率 | 越高利润越好，目标 > 30% |
| 用户沉没率 | 充值后未消耗的比例 |
| 渠道可用率 | 上游账号是否被限流/封禁 |
| 单用户成本 | 是否有异常高消耗用户 |
| 日志写入延迟 | 数据库是否成为瓶颈 |

---

## 十一、市场风险与合规

### 11.1 合规注意事项

- 根据《生成式人工智能服务管理暂行办法》，不得在中国向公众提供未经注册的生成式 AI 服务
- 用户必须遵守 OpenAI/Claude 的使用条款
- New API 使用 AGPLv3 许可证，如需闭源商用需联系 QuantumNous 获取商业许可

### 11.2 低价竞争者分析（¥20 = "$700" 模式）

这类平台的常见手法：

1. **倍率障眼法** — 显示大数字，实际模型倍率调高 50-100 倍，扣费极快
2. **模型偷换** — 标称 GPT-4o，实际转发到 DeepSeek/Gemini Flash 等低成本模型
3. **免费额度薅羊毛** — 用各平台试用/免费 API 当上游
4. **高沉没率** — 多数用户用不完，利润来自未消耗的充值

**不建议采用此模式**，原因：利润极薄或亏损、合规风险高、用户无忠诚度、随时可能因上游封号而崩溃。

### 11.3 正规运营优势

| 维度 | 正规运营 | 低价模式 |
|------|---------|---------|
| 客单价 | ¥100-500/月 | ¥20 一次性 |
| 毛利率 | 30%+ | 5% 或亏损 |
| 上游质量 | 官方 API，稳定 | 混杂不稳定 |
| 用户信任 | 高 | 低 |
| 合规风险 | 低 | 高 |
| 生命周期 | 长期可持续 | 短期 |

---

## 十二、行业术语解析：满血反重力

### 12.1 问题

> 满血反重力，这个概念是什么意思

### 12.2 解答

这是中国 AI API 转售市场中常见的营销术语，拆开来看：

#### 满血（Full Spec / Unthrottled）

在 AI API 语境下，"满血"意味着：
- 提供的是**官方原版、无阉割**的模型能力
- 没有降低 `max_tokens`、`context window` 等参数上限
- 没有在中间层做 prompt 截断或响应过滤（超出合规要求之外的）
- 与直接调用 OpenAI/Claude 官方 API 的效果一致

与之对应的是"阉割版"——一些低价平台会偷偷限制上下文长度、降低输出质量、或用小模型冒充大模型来压缩成本。

#### 反重力（Anti-Gravity）

这个词更偏营销概念，通常表达：
- **价格低得"违反物理定律"**——即以远低于官方定价的价格提供满血服务
- 暗示平台有特殊的成本优势（批量折扣、企业协议、区域定价差等）

#### 合在一起

**"满血反重力"** = 声称以极低价格提供完整、无阉割的官方模型能力。

这本质上是一个营销话术。实际上，结合我们之前分析的低价平台盈利模式（通过 `QuotaPerUnit` 调整显示汇率，¥20 显示为 $700），很多"反重力"定价的背后是通过调高内部汇率让用户**看起来**便宜，实际消耗速度和官方持平甚至更高。真正能做到低价满血的，通常依赖企业级批量折扣或 Batch API 等异步渠道。

---

*文档生成时间：2026-03-26*
*基于 QuantumNous/new-api 项目源码分析*
