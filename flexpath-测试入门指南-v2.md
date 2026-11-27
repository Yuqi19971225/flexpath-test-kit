# FlexPath 测试入门指南

> 面向：从云存储 SDN 管控面转到 AI 高性能网络、负责 FlexPath（基于 Mooncake TENT）**整体测试**的工程师
> 目标：第 1 天能动手，第 2 周能独立跑通三大场景的骨架，第 6 周拿出可签字的验收判据
> 版本：v2（2026-11）· 所有 TENT 相关结论均已对公开文档核对，关键处给出出处
> 说明：FlexPath 是团队自研组件，涉及实现细节的地方标注【待确认】，需与设计文档或 mentor 核对

---

## 0. 怎么用这份文档

### 0.1 先读这三段，其余当手册查

1. **第 3 章**（TENT 真实能力地图）—— 你测试的对象一多半是 TENT 的既有能力，不是 FlexPath 新写的代码。分不清这一点，你会把上游的已知行为当成 bug 提单。
2. **第 5 章**（三大场景设计）—— 三个场景各自最容易被判"假通过"的地方，以及怎么用 TENT 的现成开关构造对照实验。
3. **第 7 章**（动手实验）—— 六个 lab（Lab 0~5），前三个**今天在任何一台 Linux/容器上就能做**，不需要 NPU、不需要 UB 交换机。

### 0.2 你真正要交付的东西

| 交付物 | 具体形态 | 完成标志 |
|---|---|---|
| 可重复的故障注入能力 | `fault.py`：端口 down / flap / netem 丢包时延 / 打流压水线；TENT 侧再加 `enable_auto_failover_on_poll`、`max_failover_attempts` 等开关 | 注入-恢复闭环 100% 成功，且每次注入有时间戳 |
| 分层可归因的度量 | 一套 Prometheus 抓取 + `tent_*` 指标看板 + tebench JSONL 归档 | TTFT 掉了能回答"选路 / 重试 / 降级 / 排队"哪一环 |
| 没有争议的判据 | 《验收判据 v0.1》，每条判据绑定一个指标名和采集方式 | 开发、PM、测试三方签字 |

---

## 1. 你的角色：不是"验收时跑一遍"

组件测试负责人真正稀缺的能力，是**把"性能提升"变成可证伪的命题**。三件事：

1. **定义"提升"的对照物。** 没有 B1（故障 + 关闭增强）基线，"FlexPath 提升了 TTFT"这句话在评审会上不成立。
2. **证明"没坏"。** KV 传错了不会报错，只会输出乱码或答非所问。字节级 + 语义级 + 业务级三层校验，是你技术话语权的来源。
3. **在开发写完之前就把可观测性要到。** 第 9 章那张表，建议 D5 之前发出去。

你的 SDN 背景在这里 100% 复用：多路径调度 = 数据面选路，降级 = FRR，回切 = 路由收敛，冷却 = 抑制震荡（dampening）。**唯一的心智切换是时间尺度**：控制面容忍秒级收敛，数据面要求亚毫秒切换且不丢一个字节。

---

## 2. 业务与协议底座（够用即可，别陷进去）

### 2.1 KV 传输在推理链路里的位置

```
请求 → 调度/排队 → [Prefill 节点] --KV Cache--> [Decode 节点] → 逐 token 输出
                        │                            ▲
                     HBM → FlexPath → 网络 → HBM
                     └── TTFT 的关键组成          └── TPOT 的稳态来源
```

一条 KV 请求的生命周期（**你所有断言的坐标系**）：

```
业务          FlexPath            TENT Runtime            对端(NPU/UB)
 │ ①submit ──▶│                      │                      │
 │            │ ②选实例/取连接 ────▶ │                      │
 │            │                      │ ③选 transport/rail   │
 │            │                      │ ④切 slice 分发 ────▶ │
 │            │                      │ ⑤提交 WR/异步 IO     │
 │            │                      │◀── ⑥完成事件 ─────── │
 │            │ ⑦失败→重试/降级 ───▶ │                      │
 │◀─ ⑧完成/降级通知 ──────────────── │                      │
```

对齐到模块：②=实例框架+连接管理，③④=多路径调度（TENT DeviceSelector / TransportSelector），⑤⑦=异步 IO + 降级（TENT failover），①③=参数配置，HBM 侧=内存管理，整体=本地设备管理。

### 2.2 先会算这笔账：KV 到底多大

```
bytes/token = 2 × n_layers × n_kv_heads × head_dim × dtype_bytes
```

典型 GQA（64 层 / 8 KV head / head_dim 128 / FP16）≈ **128 KB/token**：

| 上下文 | KV 总量 | 25Gbps VPC(~3GB/s) | 100G(~12GB/s) | 200G(~25GB/s) | 400G(~45GB/s) |
|---|---|---|---|---|---|
| 4K | 0.5 GB | 0.17 s | 42 ms | 20 ms | 11 ms |
| 16K | 2 GB | 0.67 s | 167 ms | 80 ms | 44 ms |
| 32K | 4 GB | 1.33 s | 333 ms | 160 ms | 89 ms |
| 128K | 16 GB | 5.3 s | 1.33 s | 640 ms | 356 ms |

**这张表就是场景二的存在理由**：32K 请求在 UB 400G 下 89ms，掉到 VPC 25G 就是 1.33s，TTFT 从"几百毫秒"变"秒级"，SLO 必破。所以"降级到 VPC 保障可接受"必须配合**请求侧策略**（缩 batch、减并发、放宽 SLO、前缀复用），单靠网络降级救不回来。这句话建议你早点在会上讲——它会立刻把你和"只会跑脚本的测试"区分开。

> MLA（DeepSeek 系）的 KV 是压缩 latent，量级差别很大，必须用真实模型参数重算，不能套表。

### 2.3 TTFT / TPOT 分解

```
TTFT = 排队等待 + Prefill 计算 + KV 拉取传输 + 首 token 采样
TPOT ≈ Decode 单步 = 权重读取 + KV 读取 + TP/EP 集合通信 + 调度开销
```

两个判断，建议和开发对齐后写进测试计划：

- KV 传输**直接**在 TTFT 关键路径上 → 场景一/二用 TTFT 做判据成立。
- KV 传输**通常不在** TPOT 关键路径上（传完才开始 decode）。FlexPath 影响 TPOT 的真实路径是**资源争抢**：背景 KV 流量占满 UB → Decode 的集合通信排队；FlexPath 的轮询/拷贝抢占 decode 的核；若实现边传边算，KV 传输就进入 TPOT 关键路径。
- 所以 **"提升 TPOT"的测试本质是干扰测试**：背景 KV 大流量 + decode 并发，测 TPOT p99 的劣化幅度。这条最容易漏，也最容易出彩。

---

## 3. TENT 真实能力地图

> 出处：[TENT Overview](https://kvcache-ai.github.io/Mooncake/design/tent/overview.html) 及同目录 8 个子页。建议按"Overview → Failover → **Deadline Scheduling** → QoS → Metrics → Testing → Slice Spraying → Transport Selector → tebench"顺序读，一天能读完。Deadline 那页放前面，因为它解释了"降级钩子"和准入队列，是你理解场景二的关键。

### 3.1 三个设计选择

1. **动态传输选择**：应用只说"搬什么数据"，不说"用哪条 rail"。每次请求由运行时按当下条件选。
2. **声明式接口**：跨异构 fabric（UB / RDMA / TCP / SHM）统一 API。
3. **切片喷洒 + 弹性**：大传输切成 slice 独立调度，失败按 slice 粒度重试/改路，对应用透明。

### 3.2 对象模型（按这个建测试台账）

| 概念 | 含义 | 测试含义 |
|---|---|---|
| Instance / Batch | 引擎实例 / 一次提交的请求集合 | 多实例隔离、批量提交的部分失败 |
| Segment | 注册过的可访问内存区 | 注册/注销/跨进程/泄漏 |
| Request | 一次逻辑传输，含 `priority`、`intent_type`、`transport_hint`、`policy_name` | 语义单元，重试必须幂等 |
| Task / Slice | 切片后的执行单元 | **故障注入的最小粒度**，重试单位 |
| Transport | 后端（UB/RDMA/TCP/SHM/NVLink…） | 性能与故障表现的分界 |
| Rail | (local NIC, remote NIC) 一条物理路径 | 故障域单位，健康度来源 |
| Policy | 配置里的选路规则（priority/intent/size/device/transport 列表） | 配置生效、冲突、非法值 |

> 一个容易漏的工程事实：TENT 按 range 构造 `tent.Request`，小请求碎片化场景有固定开销。性能用例必须覆盖"多 range、小 size"形态，不能只测大块顺序传输。

### 3.3 选路与切片：默认不是"智能"

关键事实（来自 [Slice Spraying](https://kvcache-ai.github.io/Mooncake/design/tent/slice-spraying.html)）：

- `transports/rdma/enable_smart_scheduling` **默认 `false`**（官方说明：部分平台上有调度问题，暂时默认关闭）。默认行为是 **NUMA 最高层内 round-robin**。
- 打开后进入 smart 模式：按 `predicted_time = (inflight_bytes + slice_bytes) / ewma_bandwidth × numa_penalty` 打分选设备；每 100 次调用有 1 次 probe 轮询全部设备（防 EWMA 饿死）。
- NUMA 惩罚默认 `[1.0, 5.0, 10.0]`；`strict_local_numa`（或 `MC_STRICT_LOCAL_NUMA`）会**直接排除**跨 NUMA NIC——注意这是把性能问题转成可用性问题：没有本地 NIC 就分配失败。
- `closest_tier_only=true` 让本地和远端 NIC 都只用最近层。官方给了 8×H20 + 4×400G 的实测：默认 round-robin 下 3:1 聚合出现 PFC pause 16 万次、P99 2.9ms；打开后 PFC 归零、P99 547µs。**这是你报告里最有说服力的一类数据，也是"拥塞"场景最真实的成因。**

**测试推论**：场景一/二的"多路径调度"必须**分两套跑**：`enable_smart_scheduling=false`（基线）与 `=true`（宣称能力）。默认态下你测到的 round-robin 不具备拥塞规避能力，把结论混在一起会得出错误结论。

### 3.4 失败处理：三层机制，别混成一层

出处：[TENT Failover](https://kvcache-ai.github.io/Mooncake/design/tent/failover.html)。

**第一层：跨 transport failover（`TransferEngineImpl`）**

```
完成阶段 FAILED → resubmitTransferTask → failover_count++ → xport_priority++ → 下一个 transport
预算耗尽     → InvalidEntry("Failover limit exceeded, all transports exhausted")
提交阶段非 OK → 同样 failover（历史上不重试，现已实现）
```

| 配置项 | 默认 | 测试用途 |
|---|---|---|
| `enable_auto_failover_on_poll` | `true` | 置 `false` 让 poll 变成只观察，验证"是 poll 触发还是 progress 触发" |
| `max_failover_attempts` | `3` | `0`=完全关闭（造"无增强"基线 B1）；`1`=只切一次（边界） |

**第二层：rail 级暂停与恢复（`RailMonitor`）**

| 配置项 | 默认 | 含义 |
|---|---|---|
| `transports/rdma/rail_error_threshold` | `3` | 窗口内错误数达阈值→暂停该 rail |
| `transports/rdma/rail_error_window_secs` | `10` | 滑动窗口 |
| `transports/rdma/rail_cooldown_secs` | `30` | 初始冷却，跨恢复周期翻倍，上限 300s |
| `transports/rdma/rail_probe_interval_secs` | `1` | 暂停期探针间隔，`0` 关闭探测 |
| `transports/ub/endpoint_cooldown_ms` | `1000` | UB rail 冷却（UB 侧阈值 3 次 / 10s） |

状态机是 Closed → Open(冷却) → Half-Open(只放**一个** trial) → Closed。**时钟到期本身不证明链路健康，只是允许一次试探**——这个设计细节值得你在用例里专门验证：冷却到期后如果有并发流量，是不是真的只放了一个 trial（日志关键字 `Rail half-open: ...`）。

**第三层：准入队列里的 deadline 丢弃（`DegradationHooks`）**

TENT 确实有降级钩子，但它不在 failover 里，而在**准入队列**里。出处：[TENT Deadline Scheduling](https://kvcache-ai.github.io/Mooncake/design/tent/deadline-scheduling.html)。

这条链路是 opt-in 的（`enable_runtime_queue` 默认 `false`）：

```
Request{deadline_ns, priority}
      ↓ submitTransfer
准入队列（enable_runtime_queue）
  tryAdmit        : 容量限制 + EDF 插入
  pickForDispatch : promotion → 预测 MLU → 超阈则 CANCELED 并触发 on_local_decode_suggested
      ↓
Transport（RDMA/UB）
  设备选择 : 选哪张卡
  带宽仲裁 : 这张卡上的投递顺序（deadline_bw_arbitration）
      ↓
完成 → tent_deadline_mlu_permille（实测 MLU）
```

| 配置项 | 默认 | 测试含义 |
|---|---|---|
| `enable_runtime_queue` | `false` | 不开这条路径，下面所有行为都不存在 |
| `runtime_queue/deadline_aware` | `false` | 开 EDF；关闭时是 FIFO |
| `runtime_queue/promotion_slack_ns` | `0` | 剩余松弛低于此值则插队；`0` 关闭 |
| `runtime_queue/mlu_local_threshold`（θ_local） | `0.0` | `0` 关闭丢弃；**设 <1.0 会把预测能成功的请求也丢掉**，官方建议 1.2~1.5 |
| `runtime_queue/max_dispatch_bytes` | `64 MiB` | 单请求超过它会在 submit 阶段被拒 |
| `runtime_queue/progress_fallback_interval_us` | `50000` | RDMA 完成不唤醒 progress worker，靠这个 50ms 定时器补窗口 |
| `transports/rdma/deadline_bw_arbitration` | `false` | 卡内按紧迫度排序，**只在同一 priority tier 内重排** |

**三个必须知道的语义/限制**：

1. **丢弃对调用方只表现为 `CANCELED`。** 引擎装的是空 `DegradationHooks`，也没有公开的注册 API。所以"上层收到降级信号去做本地重算"这件事，**目前在 TENT 里是断的**——要么 FlexPath 自己接上，要么业务只能靠轮询到 CANCELED 再补救。
2. **只有 RDMA/UB 路由且非 staged 的 owner 可被丢弃**；只有 TCP 的主机上，EDF 与 promotion 仍生效，但丢弃和卡内仲裁**什么都不做**——这是设计如此，不是配错了。
3. **`progress_fallback_interval_us=50ms` 是一个尾时延下限。** RDMA 完成不唤醒 worker，dispatch 窗口最多要等 50ms 才补位。如果你的 TTFT 判据卡在几十毫秒量级，这个定时器会直接吃掉预算——**必须单独测一条**。

**对你们场景的意义**：这是"保障可接受的 KV 读写"最自然的接口——业务给 KV 传输带上 deadline，传不完就早点拿到 CANCELED 去走本地重算/压缩，而不是白等 1.3 秒。但如果你们的"降级到 VPC"是想**换一条慢路径继续传**，那 deadline 机制帮不上：它只会取消，不会改路。

**这是最重要的判断**：

> 三条路径的开关、触发条件、结果都不一样，但对外都叫"降级"。你的用例必须先标明在测哪一条：
>
> - **换路（failover）**：只由返回状态驱动。官方 Known Gaps 明确写"没有基于时延的『这条 transport 健康但太慢，换一条』信号" → **拥塞不会换路**。
> - **丢弃（deadline drop）**：只在准入队列开启且请求带 deadline 时存在，结果是 `CANCELED`，**不会改路**。
> - **拥塞降级**：TENT 完全没有，一定是 FlexPath 自研。
>
> 所以场景二实际是 2~3 个测试对象：故障分支（可复用上游资产）、拥塞分支（零现成资产、全靠你），以及启用时的丢弃分支（上游有单测，但"上层怎么响应 CANCELED"没人测）。

### 3.5 QoS：三级优先级，四个机制，没有总开关

出处：[TENT QoS](https://kvcache-ai.github.io/Mooncake/design/tent/qos.html)、[Transport Selector](https://kvcache-ai.github.io/Mooncake/design/tent/transport-selector.html)。

| 优先级 | 值 | 典型用途 |
|---|---|---|
| `PRIO_HIGH` | 0 | 元数据、控制消息、时延敏感（**创建 Request 时的默认值**） |
| `PRIO_MEDIUM` | 1 | 交互查询、serving |
| `PRIO_LOW` | 2 | 批量数据、后台任务 |

四个机制：

1. **per-worker 优先队列**：每 worker 三条队列，严格 HIGH→MEDIUM→LOW 排空。
2. **优先级提升（防饿死）**：等待超 `priority_promotion_timeout_us`（默认 10ms）后升一级；`priority_promotion_per_entry`（默认 false）决定是"整队提升"还是"逐条提升"。
3. **全局时间片协调**：多进程通过共享内存轮转 slot，默认 `slot_rotation_interval_ms=2`（3 slot / 6ms 一个周期）；`shared_quota_shm_path` 为空则关闭。
4. **优先级感知的设备过滤**：`enable_priority_filtering`（默认 true），`local_rotation_interval_us=200`。

另外选路策略里可以用 `priority`、`intent_type`（`foreground_get` / `background_prefetch` / `migration` / `checkpoint` / `weight_loading` / `staging_internal`）、`service_level`、`traffic_class` 做匹配，比"给每个请求手工设优先级"更适合业务侧接入。

**测试推论（很关键）**：

- **没有一个叫"开启 QoS"的开关**。per-worker 队列默认就在生效；全局 slot 要配 `shared_quota_shm_path` 才启用；设备过滤是另一回事。所以场景三的"关闭 QoS 基线 A"不能靠找开关，只能靠**构造对照**：把 KV 也设成 HIGH（等价于取消优先级差异），或把 `priority_promotion_timeout_us` 调到极大/极小。
- **默认所有请求都是 HIGH**。如果业务侧没把 KV 请求显式设成 `PRIO_LOW`，你的 A/B 对照会得到"完全没差别"，然后误判"QoS 不生效"。这是场景三最大的假阴性陷阱。
- **10ms 提升阈值是"实时性"的隐形上限**：KV 洪峰持续时，LOW 队列里的条目 10ms 后就会被提升，元数据的"绝对优先"只在 10ms 窗口内成立。EMS 的 SLO 若要求 p99 ≤ 5ms，这个默认值可能不够——这正好是一条高价值用例（见 FP-S3-011）。

### 3.6 可观测性：TENT 已经给了你大半套

出处：[TENT Metrics](https://kvcache-ai.github.io/Mooncake/design/tent/metrics.html)。**注意：metrics 默认编译关闭**，要 `-DTENT_METRICS_ENABLED=ON`；运行时可用 `metrics.enabled` / `TENT_METRICS_ENABLED` 再关。HTTP 端点 `/metrics`（Prometheus）、`/metrics/json`、`/metrics/summary`、`/health`。

最该用的几组：

| 关注点 | 指标 | 为什么重要 |
|---|---|---|
| 失败切换是否发生 | `tent_transport_failover_total{from,to}` | 非零=引擎在自救；突增=某条链路坏了 |
| 逻辑 vs 物理 | `tent_logical_requests_started_total`、`tent_transport_attempts_total`、`tent_transport_attempt_outcomes_total` | **守恒等式**：`logical started = outcomes + inflight`、`attempts = attempt outcomes + inflight`。一次 failover = 1 个逻辑 outcome + 2 个物理 attempt。**这就是"重复投递"的检测手段**：attempts 明显多于预期，说明同一逻辑传输被投了多次 |
| 时延分布 | `tent_read_latency_us`、`tent_write_latency_us`（histogram，按 transport） | 直接给 p99，不用自己算 |
| 分阶段归因 | `tent_stage_queue_wait_us`、`tent_stage_dispatch_us`、`tent_stage_transport_us` | **排队慢 vs 提交慢 vs 传输慢**，这是"分层可归因"的现成答案 |
| 失败分类 | `tent_task_failures_total{transport,reason}`（submit/poll/timeout/canceled） | 区分"注入的故障"和"自己写错的调用" |
| 在飞与注册 | `tent_inflight_attempts`、`tent_registered_buffer_bytes` | 泄漏与背压 |
| 每 rail 负载 | `TransferEngine::getNicLoadStats()`（`device_name` / `inflight_bytes` / `ewma_bandwidth_bps`） | 验证切片喷洒是否真的分散 |
| deadline 是否达成 | `tent_deadline_mlu_permille`（实测 MLU×1000，1000 是达标/超时边界）、`tent_deadline_infeasible_total`（提交时已过期） | 业务带 deadline 时，这是"按时到达率"的直接证据 |

**缺口**（第 9 章会变成给开发的诉求）：没有 per-priority 队列深度指标（官方写"requires instrumentation"）；UB rail 健康（暂停/错误数/重建次数）只在 `RailMonitor` 里，不是 Prometheus series，得通过 transport 读；没有"当前每条请求选了哪条 rail"的 per-request 埋点（只有分阶段聚合）；**被 deadline 丢弃的请求不产生任何指标**（它没跑过），只能从 `CANCELED` 状态和相关日志看出来——这是你埋点诉求的第一优先级。

### 3.7 测试钩子：上游已经把"造故障"做成了框架

出处：[TENT Testing](https://kvcache-ai.github.io/Mooncake/design/tent/testing.html)。这套东西直接决定了你 L0/L1 的工作量。

- **`FakeTransport`**：走同样的 `Transport` 契约（capabilities / submit `Status` / `TransferStatus`），不搬一个字节。真实 `TransferEngineImpl` 不改动。
- **`FaultProxyTransport`**：装饰器，支持 submit 失败、`COMPLETED→FAILED`、install 失败、可选延迟。位置在 `mooncake-transfer-engine/tent/transport/fault_proxy/`。
- **`swapTransportForTest`**：把 fake 换进 `transport_list_` 的某个 slot，`resolveTransport()` 与 `resubmitTransferTask()` 仍走生产路径。
- **能证明什么**：跨 transport failover、预算耗尽、poll vs `progressBatch` 恢复、worker/freeBatch 竞态、队列/指标行为。
- **不能证明什么**：DMA 完整性、verbs 级 WC 错误、GPU 注册、NVLink 链路故障、真实异步 RPC 时序。这些要靠 `tebench --check_consistency=true` 或多节点硬件 CI。
- **两个坑**：① CPU-only 主机必须 `USE_CUDA=OFF`，否则 `resolveTransport()` 直接返回 `UNSPEC`，注入的故障根本轮不到执行；② staging（`ProxyManager`）的触发条件目前只挂在 NVLink/MNNVL/TPU 上，CPU-only 环境**无法**覆盖 `transferEventLoop`。

跑法（官方命令，注意先编 `mooncake_common`，否则 `tent_link_group` 的 archive 依赖不生效）：

```bash
cmake -S . -B build-tent \
  -DUSE_TENT=ON -DUSE_CUDA=OFF \
  -DWITH_STORE=OFF -DWITH_STORE_RUST=OFF \
  -DBUILD_UNIT_TESTS=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build-tent --target mooncake_common -j
ctest --test-dir build-tent/mooncake-transfer-engine/tent/tests --output-on-failure
```

### 3.8 已知缺口 = 你的高风险清单

官方 `Known Gaps` 里对你最有用的几条：

1. 跨 transport failover 没有时延信号 → 拥塞不降级（场景二的核心缺口）。
2. 提交阶段的重复投递风险：`ShmTransport` 这类在 submit 循环内就启动同步拷贝的 transport，回退时可能产生"同内容重复传输"；对 KV 语义是 data-level no-op，但**会污染你的写入计数和带宽统计**。
3. 合并请求（merged/alias）只能由 owner 重投，派生 alias 必须跟随；测错会看到"重复物理提交"。
4. UB 的 bonding 设备 failover、多 rail 冷启动 bootstrap 仍需鲲鹏/URMA 硬件验证。
5. FakeTransport 覆盖不到的路径（staging、真实 WC 错误）只能靠硬件 CI。

Deadline 调度另有 6 条官方 `Known Limits`，其中 4 条会直接影响你的用例设计：

6. **丢弃不通知上层**：引擎装的是空 `DegradationHooks`，没有公开注册 API，调用方只能观察 `CANCELED`。
7. **RDMA 完成不唤醒 progress worker**：靠 `progress_fallback_interval_us`（50ms）定时器补 dispatch 窗口——**这是尾时延的硬下限**。
8. **failover 后仍占着 RDMA 的账**：请求按 RDMA 入场、失败后走 TCP 恢复，它的字节仍记在 `dispatching_bytes_` 里，导致后续预测偏悲观，直到它完成。
9. **混合 submit 绕过队列**：一个 submit 里同时有 staged 和非 staged owner，整批不进队列，后续请求的 drop 预测会低估前面的排队量。

**把这 9 条直接抄进风险清单**（xlsx 的「风险清单」页已收录对应条目），比你自己臆想风险靠谱得多。

---

## 4. FlexPath 七大模块 ↔ TENT 能力 ↔ 测试主轴

> 用法：这张表是你的测试分析（Test Analysis）底稿，每行展开 3–8 条用例（xlsx 已展开）。**第三列最关键**：先分清"上游已有"还是"FlexPath 新增"，决定你是复用上游测试还是从零设计。

| FlexPath 模块 | 大概率对应 | 上游有无 | 测试主轴 | 你的发力点 |
|---|---|---|---|---|
| 实例框架 | Instance 生命周期、`construct()`/`swapTransportForTest`/shutdown | 有 | 生命周期矩阵、kill -9、双实例隔离 | 异常退出后的半初始化状态（上游测试不覆盖进程级） |
| 连接管理 | Segment/Endpoint、连接池、`EndpointStore`、`retireLocalDevice` | 有 | 半开连接、重连风暴、连接上限 | 建链时延与"连接数上限"的明确报错 |
| 异步 IO | Batch/Task、`getTransferStatus`、`progressBatch`、completion、准入队列 | 有 | 乱序/丢失完成、cancel、超时、大 batch、EDF/dispatch 窗口 | cancel 后是否仍回调；1 个逻辑请求对应几次 attempt；50ms 补窗口的影响 |
| 参数实例配置 | `transfer-engine.json`、`MC_TENT_CONF`、policy 数组 | 有 | 组合爆炸、非法值、热更新 | **非法值静默取默认**是重灾区 |
| 本地设备管理 | 设备发现、端口状态、`getNicLoadStats`、NUMA | 有 | 掉卡、热插拔、绑错设备、状态缓存 | UB 侧 `recordEndpointRebuild`、设备退役 |
| 降级处理 | ① cross-transport failover ② RailMonitor 暂停/半开 ③ 准入队列 deadline 丢弃 + 降级钩子（空实现）④ **FlexPath 自己的拥塞判定** | ①~③ 有，④ 无 | 触发阈值、防抖、回切、不卡死、CANCELED 语义 | ③ 的钩子要自己接；④ 是纯新增，必须自己定判据 |
| 内存管理 | MR 注册/注销、缓冲池、`registered_buffer_bytes` | 有 | 泄漏、碎片、OOM、跨进程 | 72h 斜率、destroy 后无残留 |

**旁路（经其他 NPU 转发）不在上表**——公开 TENT 文档里没有 peer-NPU 中继，只有"直连不可用时经 host memory 的 staged transfer"。所以旁路是 **FlexPath 的纯新增能力**，测试要从零设计：几跳、如何选 peer、环路检测、级联故障、对被借道 NPU 本地传输的干扰。这一块没有上游资产可抄。

---

## 5. 三大验收场景的可执行设计

### 5.0 通用方法论

#### (1) 三方基线：缺一个就没法证明收益

| 基线 | 含义 | 怎么造（TENT 语境） |
|---|---|---|
| **B0** | 无故障、正常路径 | 默认配置，`enable_smart_scheduling` 保持与 B2 一致 |
| **B1** | 注入故障 + **关闭增强** | TENT 侧 `max_failover_attempts=0`；FlexPath 侧关旁路/关降级。这是"没有 FlexPath 会怎样" |
| **B2** | 注入故障 + FlexPath 正常 | 被测对象 |

报告里每个数字写成 `B2 vs B0（劣化 x%）/ B2 vs B1（改善 y%）`。只给 B2 绝对值，评审必被问死。

**注意 B1 的构造陷阱**：`max_failover_attempts=0` 会让任务直接 `FAILED`，业务侧可能立刻重试到别的节点，看起来"也没事"。所以 B1 必须固定业务重试策略，否则你测的是业务的重试能力，不是 FlexPath 的。

#### (2) 故障注入四要素（每个用例都要写全）

```
① 注入点：物理(拔纤/关光模块) / 交换机(端口 shutdown/ACL) / 主机(驱动/工具置 down) / 进程(自身故障)
② 注入方式：确定、可脚本化、可指定目标端口与 rail
③ 注入时机：建链前 / 传输中(in-flight) / 空闲期 —— 三者行为完全不同，都要测
④ 恢复方式：自动恢复 / 人工恢复 / 只恢复一半（验证回切）
```

**必须先确认的能力边界**：UB 口大概率不吃 `tc netem`（不是标准以太网栈）。先花半天验证"这个口到底能被什么手段置 down / 注入丢包"，把结论写进测试计划。**不能动交换机就要明确声明覆盖度打折**，别等到验收会才说。

#### (3) 判据模板

```
在【拓扑 X + 故障 Y + 负载 Z + 配置 C】下：
  在飞请求失败数 = 0
  传输成功率 = 100%
  TTFT p99 ≤ A ms，且相对 B0 劣化 ≤ B%
  故障注入 → 首次重试/改路 ≤ C ms；→ 新路径承载流量 ≤ D ms
  数据校验错误 = 0，重复写 = 0（用 metrics 守恒等式判，见 6.3）
  恢复后 ≤ E s 回到最优路径，观察窗内回切次数 ≤ 1
```

A/B/C/D/E 是你和开发、PM 一起定的，**写进测试计划并签字**。建议每个数字后面标"来源"：设计文档 / 实测基线 / 业务 SLO。

### 5.1 场景一：UBC/UBG 部分网口故障或拥塞 → 多路径调度 + 其他 NPU 旁路

#### 拆成 6 条可测断言

| 断言 | 内容 | 观测手段（尽量用现成的） |
|---|---|---|
| S1-A1 | 单端口故障时在飞传输不失败，切片自动改路 | `tent_transport_failover_total` 从 0 变正；`tent_task_failures_total{reason="poll"}` 受控；业务侧零报错 |
| S1-A2 | 多端口/整 rail 故障时仍可用，带宽有下界 | tebench `BW (GB/s)` / `P99 Tx`；`tent_stage_transport_us` 分布 |
| S1-A3 | 拥塞（不故障）时靠多路径分流降低尾时延 | 对比 `enable_smart_scheduling` 开/关的 `P99 Tx`；`getNicLoadStats` 的 `ewma_bandwidth_bps` 分布 |
| S1-A4 | 旁路经其他 NPU 转发成功、数据一致、跳数代价可接受 | 旁路成功率、跳数计数（FlexPath 埋点）、`tent_read_latency_us` 增量 |
| S1-A5 | 传输中注入故障不产生重复写/静默错 | 守恒等式（`logical` vs `attempts`）+ checksum + 端到端输出比对 |
| S1-A6 | 双故障（主路径 + 旁路 peer 同时挂）能正确衔接降级 | 降级事件时序、是否 hang、有无明确终态 |

#### 故障注入矩阵

| 维度 | 取值 |
|---|---|
| 拓扑 | 同超节点 / 跨超节点经 UBG / 跨 rail / 主备同交换机 |
| 故障类型 | 端口 down / flap / 丢包 / 时延增大 / 带宽压满 / 光模块误码 |
| 规模 | 1 口 / 1 rail 全口 / 半数口 / 单 NPU 全断 |
| 时机 | 建链前 / 传输中 / 空闲 |
| 负载 | 单请求大 KV / 多请求并发 / 混合大小 / 长稳背景流 |

#### 三个必须单独设计的子项

**(a) smart scheduling 开/关对照**（这是场景一的分母，也最容易漏）
默认 `false` 是 round-robin，不具备拥塞规避。必须证明"打开后"才有宣称的分流效果；否则你的"多路径调度有效"结论是假的。

**(b) 旁路专项**
- **环路**：A→B、B→A 同时旁路是否成环；
- **级联**：peer NPU 自己也在传数据，旁路流量把它拖垮多少（**干扰测试**，测 peer 本地吞吐下降百分比）；
- **跳数代价**：多一跳的时延/带宽衰减曲线（这是报告里最有说服力的图）；
- **选 peer 策略**：为什么选它？选错（跨 NUMA、拥塞节点）时表现如何；
- **旁路的可见性**：你怎么知道流量真的走了旁路，而不是重试到了 VPC？——必须有日志或计数器，否则这条断言不可证。

**(c) 与 TENT 的职责边界**
故障瞬间，TENT 的 rail 暂停（3 次/10s，冷却 30s 起）和 FlexPath 的"改路/旁路"可能同时生效。**要测它们是否打架**：比如 TENT 已暂停 rail A，FlexPath 又把流量调度到 A 的旁路，形成"绕一圈回到坏链路"。这是典型的"两层保护互相干扰"，也是你最容易挖到真 bug 的地方。

#### 陷阱清单

- 只看"业务没报错"就判通过 → KV 错了不报错，只输出乱码。**必须语义级校验**。
- 只在空闲时注入 → 漏掉 in-flight，漏掉 slice 级重试与幂等。
- 端口 down 后交换机侧残留表项，导致"看起来恢复了但流量回不去"。
- 用 `ifconfig down` 模拟与真实光模块故障的时序差异很大，结论必须标注模拟手段。
- 带宽下界没定义就跑 → 事后无法判断"掉 40% 算不算通过"。

### 5.2 场景二：多路径调度降级到 VPC，保障可接受的 KV 读写

#### 先分清三条完全不同的路径

| 分支 | 触发条件 | 结果 | 谁实现 | 你的测试资产 |
|---|---|---|---|---|
| **① 故障改路** | transport 返回 `FAILED`（提交或完成阶段） | 同一 task 换到 fallback transport 继续传 | TENT cross-transport failover | 可复用上游 FakeTransport 测试 + 自己补硬件侧 |
| **② 拥塞降级** | 慢但没失败（丢包率、时延、带宽水位） | 换到 VPC 继续传，性能下降但可用 | **FlexPath 自己** | **零现成资产，全靠你设计** |
| **③ deadline 丢弃** | 预测在 deadline 内传不完（需开准入队列） | **不传了**，任务变 `CANCELED`，由上层决定重算/压缩 | TENT 准入队列（钩子空实现） | 上游有单测，但"上层怎么响应"没人测 |

**这三条最容易被混为一谈**，而它们的验收判据完全相反：① 要求"传输不失败"，② 要求"降级后仍可接受"，③ 要求"该丢就丢、且上层知道要重算"。把 ③ 的用例写成 ① 的断言（比如"失败数必须为 0"），就会把正确行为判成 bug。

这一区分如果没和开发对齐，你的用例会写出一堆"期待 TENT 在拥塞时降级"的错误断言。

#### 必须回答的 7 个问题

| # | 问题 | 测法 | 判据 |
|---|---|---|---|
| B1 | 什么条件算"不可用"？ | 端口 down / 持续丢包 / 时延超阈 / 带宽不足 分别注入 | 决策与实际故障类型匹配；**拥塞必须能被 FlexPath 而非 TENT 捕获** |
| B2 | 会不会误判？ | 100ms~2s 瞬时抖动脉冲 ×20 | 不降级，或降级后 1 个观察窗内回切 |
| B3 | 决策有多快？ | 注入时间戳 T0 → 首个字节走 VPC 的 T1（日志/抓包） | ≤ C ms |
| B4 | 降级后"可接受"是多少？ | VPC 路径带宽/时延/成功率 + 端到端 TTFT | 见下方三档定义 |
| B5 | 降级期间数据对吗？ | 全量 checksum + 守恒等式 + greedy 输出比对 | 0 错误、0 重复投递 |
| B6 | 恢复后回切吗？ | 恢复链路，观察流量是否回到 UB、多久 | ≤ D s，回切次数 ≤ 1 |
| B7 | 会不会永久卡在降级？ | 故障保持 ≥1h 后恢复 | 必须回切 |

**B6/B7 有个容易被忽略的细节**：TENT 每条新请求从 priority 0 重新解析，本身没有粘滞；**卡住只可能发生在 FlexPath 自己的状态机里**。所以这两条用例要抓 FlexPath 的状态迁移日志，而不是盯 `tent_transport_failover_total`。

#### "可接受"怎么写才不扯皮

```
硬门槛（不满足则不验收）：
  - 传输成功率 100%，静默错误 0，重复写 0
  - TTFT p99 ≤ <SLO>（按业务定，长上下文可设 5s）
软目标（达成即优秀）：
  - 降级后有效 KV 带宽 ≥ 40% 原路径
  - TTFT p99 相对 B0 劣化 ≤ 50%
观察项（只记录不判）：
  - VPC 路径 CPU 占用、重传率、与业务 VPC 流量的相互影响
```

**如果你们选择「丢弃 + 本地重算」而不是「降级到 VPC」**，判据要换一套（这是另一种"可接受"）：

```
  □ 预测超时的请求被 CANCELED 的比例符合设计（不多丢、不少丢）
  □ 从提交到 CANCELED 的时延 ≤ ___ ms（要早，不能等快到期才丢）
  □ 上层确实对 CANCELED 做了处理（重算/降级），没有静默丢弃请求
  □ 被丢弃的请求没有产生部分写入（半写坏块 = 0）
  □ 不丢：预测能赶上的请求，实际达成率 ≥ ___%
```

最后一条尤其重要：θ_local 设低于 1.0 会把"预测能成功"的请求也丢掉，官方在真机上实测过这种情况。**"不多丢"必须用 `tent_deadline_mlu_permille` 的实测分布交叉验证**，不能只看丢弃计数。

> 提醒：40% / 50% 是经验初值，**必须用你自己的实测基线重标**。写进签字文档的数字要有出处。

#### VPC 路径特有测试（线上最容易炸）

- MTU / 分片：大块 KV 走 VPC 的分片与重组，MTU 不一致场景；
- CPU 开销：TCP 栈拷贝打满核，反过来拖慢 decode → **TPOT 劣化**（这条和 5.1 的干扰测试共用一套负载）；
- 加密/隧道：IPsec/VXLAN 的带宽与 CPU 双重损失；
- 与业务 VPC 争抢：VPC 不是专线，测"背景业务流 + 降级 KV 流"共存；
- 跨 AZ 时延基线：先测空载 RTT，再算传输时间。
- `hp_tcp` 只支持 host memory（官方限制），如果降级路径选了它而 buffer 在 NPU 上，会多一次 staging——**要么测出这个额外开销，要么明确不支持**。

### 5.3 场景三：QoS 优先级（EMS 元数据 > KV 数据）

#### 先解决"有意义的拥塞"

没有拥塞，优先级测试全是假通过。两种手段，建议都用：

1. **tebench 背景流压水线**（80%~95%）——不需要真业务；
2. **真实 PD 分离负载**（vLLM/MindIE + 并发请求）——更接近验收。

#### 对照实验设计（灵魂）

```
A：拥塞 + 优先级无差异（KV 也设为 HIGH / 关闭全局 slot）→ EMS p99 劣化基线
B：拥塞 + EMS=HIGH，KV=LOW                             → 改善幅度
C：不拥塞 + 同样配置                                     → 确认 QoS 无额外开销
```

**只有 A/B 对比能证明优先级生效**。只跑 B 等于没测。

由于 TENT 没有"QoS 总开关"，A 组的构造方式要写清楚（三选一，写进用例备注）：
- 把 KV 也设成 `PRIO_HIGH`（最贴近"没有优先级"的语义）；
- `shared_quota_shm_path=""` 关闭全局协调；
- `priority_promotion_timeout_us` 调成 0（立即提升，等价于无优先级）。

#### 用例族（每条都能落到一个可观测对象）

| # | 用例 | 观测 | 判据 |
|---|---|---|---|
| C1 | 拥塞下 EMS 元数据 p99 | 客户端侧 RPC 时延（不是服务端） | 开 QoS 后改善 ≥ x%，且 ≤ 实时性阈值 |
| C2 | KV 是否被饿死 | KV 吞吐、`tent_stage_queue_wait_us` | KV 吞吐下降 ≤ y%，无饿死 |
| C3 | 优先级映射正确性 | policy 的 `priority`/`intent_type` 是否命中预期 transport；`service_level`/`traffic_class` 是否下发到 RDMA | 配置与行为 100% 一致 |
| C4 | 跨路径一致性 | UBC / UBG / VPC 三条路径各跑一轮 | 三条都生效（VPC 上通常靠 DSCP+TC，最容易断链） |
| C5 | 元数据洪峰 | 批量 segment 注册/查询 10k 次 | 无丢弃、p99 达标 |
| C6 | 异常配置 | 非法值、全高、运行中改、与限速冲突 | 明确报错；全高时有兜底 |
| C7 | 反向干扰 | 元数据流量过大时压制 KV | 应有限制，不能反向饿死 |

#### 三个必须验证的机制细节

1. **默认全是 HIGH** → 检查业务侧 KV 请求是否真的设了 `PRIO_LOW`。用日志或策略命中情况证明，不能只看配置。**这是最容易的假阴性**。
2. **10ms 提升阈值** → 在 KV 持续洪峰下，LOW 队列 10ms 后被提升，元数据的绝对优先只在 10ms 窗口成立。用例：`priority_promotion_timeout_us` 取 10ms（默认）/ 1s / 极大，看 EMS p99 曲线是否出现拐点。若拐点落在 SLO 附近，默认值就不够，是**配置问题还是设计问题**要拉开发一起判。
3. **全局 slot 的残留** → `/dev/shm/mooncake_rdma_slots` 上次异常退出会残留，导致新进程行为异常。用例：kill -9 后不清理直接重启，看是否自愈（官方 troubleshooting 明确建议 `rm -f /dev/shm/mooncake_rdma_slots`，说明这不是自动处理的场景）。
4. **优先级与 deadline 仲裁的叠加** → 若同时开了 `deadline_bw_arbitration`，卡内是按紧迫度排序的，但**只在同一 priority tier 内**。也就是说：HIGH 的元数据永远先于 LOW 的 KV，不管 KV 的 deadline 多紧。这条既是设计保证（元数据优先），也是潜在事故点（KV 的 deadline 被 HIGH 流量永久挤压）。用例：HIGH 小包持续 + LOW 大包带紧 deadline，看 LOW 的 `tent_deadline_mlu_permille` 是否被压到 >1；如果会，就是"保了元数据饿死数据"的量化证据。

#### 观测难点与解法

- 元数据 RPC 时延要在**客户端侧**打点（服务端看不到排队）；
- 要区分"网络排队"和"服务端处理慢" → 用 trace id 贯穿，或对比 `tent_stage_queue_wait_us`；
- 优先级是否生效，最硬的证据是**每队列计数/丢包计数**——但 TENT 默认不暴露，需要加埋点（正好是第 9 章的诉求 3）；
- 端到端时延只能证明"有差别"，不能证明"差别来自优先级"，别把它当唯一证据。

### 5.4 场景 ↔ 用例 ↔ 断言对照

| 验收场景 | 核心断言 | 用例区间 |
|---|---|---|
| 场景一 多路径 + 旁路 | S1-A1~A6 | FP-S1-001 ~ FP-S1-016 |
| 场景二 VPC 降级 / 丢弃 | B1~B7 + 丢弃闭环 | FP-S2-001 ~ FP-S2-016 |
| 场景三 QoS | C1~C7 + 仲裁叠加 | FP-S3-001 ~ FP-S3-013 |
| 支撑性模块质量 | 7 模块基础正确性 | FP-M-001 ~ FP-M-041 |
| 性能与长稳 | 基线、干扰、回归 | FP-P-001 ~ FP-P-006 |

---

## 6. 指标体系与判据

### 6.1 四层指标

```
业务层：TTFT p50/p90/p99 · TPOT p50/p99 · 吞吐(tokens/s, req/s) · goodput(SLO内吞吐)
KV 层 ：单请求传输时延 p99 · 有效带宽 · 成功率 · 重试率 · 降级率
传输层：per-rail 带宽/利用率/重传 · 选路分布 · 切换次数 · 建链时延
资源层：CPU · RSS · HBM · QP/MR/fd/线程 · 中断/轮询占比
```

### 6.2 必测数字 → 落到具体指标名

| # | 指标 | 采集方式（可直接用） |
|---|---|---|
| 1 | TTFT p99 | 客户端 benchmark（vLLM/MindIE 或自研 driver） |
| 2 | TPOT p99 | 同上；**必须单独做干扰场景** |
| 3 | 有效 KV 带宽 | `rate(tent_read_bytes_total[1m])` 或 tebench `BW (GB/s)` |
| 4 | KV 传输时延 p99 | `tent_read_latency_us` / `tent_write_latency_us` 的 histogram quantile；tebench `P99 Tx` |
| 5 | 传输成功率 | `tent_logical_request_outcomes_total{outcome="success"}` / 总数 |
| 6 | 静默错误率 | checksum + 语义级输出比对（见 6.3） |
| 7 | 故障检测时延 | 注入时间戳 + 首个 failover 日志/指标变化 |
| 8 | 切换完成时延 | 注入时间戳 + 新 transport 的 `tent_transport_attempts_total` 起量 |
| 9 | 降级生效时延 | 注入时间戳 + 首字节走 VPC（FlexPath 埋点） |
| 10 | 回切时延/次数 | FlexPath 状态机日志；`tent_stage_*` 的 transport 标签变化 |
| 11 | 降级期带宽保持率 | tebench 前后对比 |
| 12 | 长稳泄漏斜率 | `tent_inflight_attempts`、`tent_registered_buffer_bytes`、fd/RSS 采样 |
| 13 | deadline 达成率（专项） | `tent_deadline_mlu_permille` 的 ≤1000 占比；`tent_deadline_infeasible_total`；CANCELED 计数 |

### 6.3 数据完整性：三层校验 + 一个守恒等式

1. **字节级**：源/目的 KV 内存块 checksum（CRC32/SHA256），逐 slice 比对。
2. **语义级**：同一 prompt 在"正常路径"和"故障路径"下 greedy 解码，输出 token 序列逐位一致。
3. **业务级**：多轮对话/长上下文抽检（防"小概率错块恰好在无关位置"）。

**重复写的检测，用守恒等式比写入计数器更省事**：

```
logical started = logical outcomes + logical inflight
physical attempts = attempt outcomes + inflight attempts
```

一次正常的 failover 应该是：1 个 logical 成功 + 2 个物理 attempt（1 失败 1 成功）。如果 `tent_transport_attempts_total` 的增长明显超过"注入的故障数 × 预期重试次数"，就是重复投递。这个判据比在目标端加写入计数器更容易落地——但**两者都要**，因为守恒等式只能发现"多投了"，发现不了"投给了错误的目标"。

> 性能测试时关掉校验，正确性测试时全开。校验本身会拉低带宽 10%~30%，混在一起测出的数字没有可比性。

### 6.4 长稳与泄漏

- 24h/72h，每小时随机注入一次故障（类型/端口/时机随机）；
- 监控 fd、线程、QP、MR、RSS、HBM、连接数、日志大小、`tent_registered_buffer_bytes`；
- 判据是**增长斜率趋近 0**，不是"绝对值没爆"；故障恢复后指标必须回到基线带内。
- 特别注意 UB 侧：`recordEndpointRebuild` 会因 endpoint 重建计数，长稳看它是否单调增长（那是 bootstrap 没收敛）。

---

## 7. 动手实验：从零到能跑（Lab 0~2 不需要 NPU）

> 目标不是"跑通"，是**每一步都产出一份能进报告的记录**。每个 lab 末尾的"记录"就是附录 C 模板的字段。

### Lab 0：版本指纹与能力盘点（30 分钟，无需硬件）

**目标**：任何一份测试报告，第一页都能回答"在什么软硬件上得出的结论"。

```bash
# 1. 代码指纹
git -C $MC rev-parse HEAD && git -C $MC describe --tags --always --dirty
# 2. 构建配置指纹（把 CMakeCache 里的关键项抓出来）
grep -E "USE_TENT|USE_CUDA|USE_ASCEND|TENT_METRICS_ENABLED|BUILD_UNIT_TESTS" build/CMakeCache.txt
# 3. 设备与驱动
npu-smi info            # 有 NPU 时
ibv_devinfo -l 2>/dev/null | head   # RDMA 环境
# 4. 时间同步
chronyc tracking || timedatectl status
```

**记录**：CANN/驱动/固件、Mooncake commit、FlexPath 版本、模型与 KV 形态、拓扑（超节点数/NPU 数/每 NPU 的 UBC·UBG 数）、注入手段能力、背景流量。

**常见坑**：不锁 CANN 与固件版本，两周后复现不出来；`chronyc` 没装导致时延分解全错。

### Lab 1：编译 + 跑上游测试（半天，任意 Linux/容器）

**目标**：建立对"这套代码怎么测"的直觉，顺便验证你的工具链。

按 3.7 的命令编译并 `ctest`。然后**精读并通过调试三个测试**：

1. `engine_failover_e2e_test.cpp` 里的 `SubmitStageFailureFailsOverToSecondary` —— 看它怎么用 `FaultProxyTransport` 制造 submit 失败，怎么断言"主用 1 次、备用 1 次"。
2. 预算耗尽类用例（`max_failover_attempts` 取 0/1/3）—— 看它怎么断言"不再触碰预算外的 transport"。
3. `tent_rail_monitor_test` —— 看它怎么验证冷却、半开、单 trial。

```bash
# 只跑某个测试（gtest 过滤，二进制名以 build 产物为准）
./build-tent/mooncake-transfer-engine/tent/tests/<test_binary> --gtest_filter='*Failover*'
```

**期望**：`cuda-off` 全绿；`tent_*transport_test` 因无硬件 skip，这是**预期行为**，不代表数据面被测过（官方特意强调这点）。

**记录**：测试总数/通过/跳过数、被 skip 的用例列表（这些就是硬件环境要补的洞）。

### Lab 2：单机 tebench 打通（1 小时，无需 NPU）

**目标**：有了它，场景一/二/三的"传输层"都可以先脱离业务跑。

```bash
# 终端 1：target（打印出 segment name）
./tebench --backend=tent --metadata_type=p2p --seg_type=DRAM --xport_type=tcp

# 终端 2：initiator（把 <SEG> 换成终端 1 打印的）
./tebench --backend=tent --metadata_type=p2p --seg_type=DRAM --xport_type=tcp \
  --target_seg_name=<SEG> --op_type=read --duration=5 \
  --start_block_size=65536 --max_block_size=1048576 \
  --start_batch_size=1  --max_batch_size=16 \
  --start_num_threads=1 --max_num_threads=8

# 正确性冒烟（会跑 mix 模式并回读校验）
./tebench --backend=tent --target_seg_name=<SEG> --check_consistency=true --duration=5
```

**期望**：看到 `BW (GB/s)`、`Avg Tx`、`P99 Tx`、`P999 Tx` 四类数字；`--check_consistency=true` 下无校验失败。

**顺手做的两件事**：
- `--split_output_jsonl=sw.jsonl`，得到每个传输的 `submit_us` / `wait_us` / `polls`——**这是你以后区分"提交慢"和"完成慢"的第一手数据**；
- 用 `--request_interval_us` 做开环/闭环对比，理解"节流后的时延不等于引擎时延"。

**常见坑**：tebench 参数随版本变化，所有 flag 以 `--help` 为准；`block_size × batch_size × threads` 超过 buffer 会整组 skip，别把"全 skip"当成通过。

### Lab 3：把 metrics 接起来（半天）

**目标**：让"分层可归因"从口号变成看板。

```bash
cmake -S . -B build-metrics -DUSE_TENT=ON -DUSE_CUDA=OFF -DTENT_METRICS_ENABLED=ON ...
# 配置文件里打开
# { "metrics": { "enabled": true, "http_port": 9100 }, ... }
curl -s localhost:9100/metrics | grep -E "tent_(logical|transport_attempt|stage_)"
```

**必做的三件事**：

1. **验证守恒等式**：跑 1000 次传输，检查 `logical started = outcomes + inflight`；再人为制造 1 次 failover，检查 attempts 是否 +2。
2. **验证分阶段归因**：人为用 `tc` 加 10ms 时延，看 `tent_stage_transport_us` 是否右移，而 `queue_wait` 是否不变。
3. **抄一份 Grafana 查询**（官方给了吞吐/请求率的写法），把 `tent_read_bytes_total` 按 transport 拆开。

**常见坑**：忘记 `-DTENT_METRICS_ENABLED=ON`，所有指标静默为空（默认编译关闭，零开销）；`/health` 只表示 metrics HTTP 进程活着，**不代表引擎健康**——别拿它做存活探针。

### Lab 4：第一次故障注入（半天，需要能置 down 的口）

**目标**：拿到"注入→检测→切换"三段时延的第一个数字。

```bash
# 0. 记录 T0（精确到 ms，用 date +%s.%N）
T0=$(date +%s.%N)
# 1. 注入（手段以你环境为准：端口 down / 交换机 shutdown / tc netem / FlexPath 注入 API）
tc qdisc add dev ethX root netem delay 10ms loss 1%    # 仅标准以太网口适用
# 2. 观察 120s：metrics 曲线 + 日志
grep -E "Transport failover|Rail half-open|Rail recovered|Task failover limit" flexpath.log
# 3. 恢复
tc qdisc del dev ethX root
```

**期望**：日志出现 `Transport failover: X -> Y (attempt 1/3)`；`tent_transport_failover_total` 阶跃；业务侧零失败。

**记录**：T0、首次 failover 时间、切换完成时间、恢复时间、回切时间、期间 `P99 Tx` 变化。

**必须诚实标注的**：UB 口可能不支持 `tc`；此时要么用交换机/驱动手段，要么明确写"本次结论仅覆盖主机侧模拟，不能外推到光模块故障"。

### Lab 5：QoS 三组对照（1 天）

**目标**：第一次拿到"优先级真的生效"的证据。

**第一步，用 tebench 拿报告指标**（不需要改代码）：

```bash
./tebench --target_seg_name=<SEG> --backend=tent \
  --start_num_threads=16 --max_num_threads=16 \
  --qos_classes=foreground:4:1000:4:12.5,checkpoint:12:0:1:10.0 \
  --qos_link_capacity_gbps=25 \
  --qos_output_jsonl=qos-A.jsonl
```

输出含 `slo_attainment`、`p99_us`、`goodput_gbps`、`jain_fairness`、`isolation_leakage`、`total_utilization`。

**注意**：tebench 的 QoS 模式是**报告口径**，官方明确说"不改变任一 backend 的调度策略"。所以它只能给你"业务指标长什么样"，**不能证明优先级生效**。

**第二步，写一个 100 行的 driver 真正设优先级**：构造两组 `Request`，一组 `priority=PRIO_HIGH`（模拟 EMS），一组 `PRIO_LOW`（模拟 KV），在拥塞下跑，对比 p99、`tent_stage_queue_wait_us`。再重复 A/B/C 三组。

**记录**：A/B 的 EMS p99 差值（改善幅度）、KV 吞吐下降、C 组的额外开销。

---

## 8. 30/60/90 天计划

### D1–D5：建立坐标（不写生产代码）

| 天 | 动作 | 产出 |
|---|---|---|
| D1 | 读第 2、3 章 + TENT Overview/Failover/QoS 三个文档 | 一页术语表 + 20 条疑问 |
| D2 | Lab 0 + 找 mentor 过一遍 FlexPath 架构（重点问：哪部分是自己写的） | 环境指纹表、模块归属表 |
| D3 | Lab 1：编译 + ctest + 读三个 failover 测试 | 一页《TENT 怎么测的》 |
| D4 | Lab 2：单机 tebench 跑通 + `--check_consistency` | 第一张带宽/时延曲线 |
| D5 | 发出第 9 章的 10 条可测性需求 | 开发确认回执 |

### W2–W4

| 周 | 目标 | 交付物 | 完成标准 |
|---|---|---|---|
| W2 | 基线 + 注入能力 | B0 基线报告 v1、`fault.py` | 注入-恢复闭环 100%；B0 覆盖 4K/16K/32K × 并发 1/8/32 |
| W3 | 场景一骨架 | 场景一报告 v1 | P0 用例 60% 通过或缺陷已提单；有"跳数代价"曲线 |
| W4 | 判据定稿 | 《验收判据 v0.1》 | 三方签字；每条判据有指标名与采集方式 |

### M2–M3

| 阶段 | 目标 | 交付物 |
|---|---|---|
| M2 | 场景二/三全链路（含拥塞分支——这是 FlexPath 自研部分，风险最高） | 场景二/三报告、测试框架 v1 |
| M3 | L0/L1 进 CI、72h 长稳 + 混沌、性能回归看板 | 体系文档、看板、下阶段风险与投入建议 |

**每周固定**：周一同步风险，周五出一页纸（数字 + 图 + 阻塞项）。

---

## 9. 测试左移：10 条可测性需求（已按"上游有无"标注）

> 这样提需求，开发不会觉得你在加活：先说"TENT 已经有了"，再说"FlexPath 还差什么"。

| # | 需求 | 上游状态 | 你要它做什么 |
|---|---|---|---|
| 1 | per-request 结构化埋点：request_id、选中 transport/rail、slice 分布、重试次数、失败原因码、各阶段耗时 | 部分有（`tent_stage_*` 是聚合，非 per-request） | 加 request_id 串联 |
| 2 | 选路决策日志：候选集、打分、排除原因、可回放 | 无 | 至少要能回答"为什么没走 B 路" |
| 3 | **per-priority 队列深度与出队计数** | 官方明确"requires instrumentation" | 场景三的硬证据 |
| 4 | 降级/丢弃事件：触发条件、阈值、决策耗时、影响范围、CANCELED 的丢弃原因 | deadline 丢弃上游有状态无指标；拥塞降级为 FlexPath 自研 | 状态机事件流带因果 id |
| 5 | 健康度快照接口：每个端口/rail 的状态与最后更新时间 | `getNicLoadStats` 只有 inflight/ewma | 要能查"暂停中/冷却中/半开" |
| 6 | 测试专用故障注入 API：强制某 transport 失败、强制走某 rail、注入延迟 | 上游有 `swapTransportForTest`（仅单测） | 要能在集成环境用 |
| 7 | 确定性开关：固定 seed、pin rail、关后台探测 | `score_jitter_range` 部分可用 | 复现用 |
| 8 | 资源计数：QP/MR/fd/线程/池的实时值与高水位 | 部分（`tent_registered_buffer_bytes`、`tent_inflight_attempts`） | 补齐 fd/线程/QP |
| 9 | 标准 metrics 端点 | **已有**（`/metrics`，需编译开关） | 确认交付版本带 `TENT_METRICS_ENABLED=ON` |
| 10 | 干净的销毁语义：destroy 后可断言"无残留" | 上游有 quarantine 机制 | 提供残留检测接口 |

---

## 10. 高频坑清单

### 通用（20 条）

1. 只测"业务没报错"，不做数据校验 —— KV 错了不报错，只输出乱码。
2. 只在空闲时注故障，漏掉 in-flight。
3. 没有 B1 基线，"FlexPath 提升了性能"无法证明。
4. 用端到端 TTFT 判断一切，无法归因到模块。
5. 忽略 TPOT 的干扰路径，验收时拿不出 TPOT 数据。
6. 用 `ifconfig down` 代替真实故障，结论过度外推。
7. 冷却/恢复期行为不测，导致"卡在降级"上线。
8. 回切抖动（flapping）不测。
9. 把瞬时抖动判为故障，降级过于激进。
10. 重复投递不测（checksum 查不出重复写）。
11. 小请求碎片化不测（单 range 有固定开销）。
12. 长稳只看"没崩"，不看斜率。
13. 性能测试开着校验和日志，数字偏低。
14. 不锁版本（CANN/驱动/固件），结论不可复现。
15. 背景流量不隔离，基线被污染。
16. 时间不同步（chrony），时延分解全错。
17. CPU 没绑核/中断没隔离，抖动掩盖真实问题。
18. 多实例/多进程不测，全局态串扰。
19. 配置只测合法值，非法值静默取默认最危险。
20. 报告只有平均值，没有 p99 和曲线。

### TENT/FlexPath 特有（16 条，都是真实约束）

21. **`enable_smart_scheduling` 默认 false**，不显式打开就是在测 round-robin，"多路径调度有效"的结论不成立。
22. **拥塞不会触发 TENT 的 failover**（只有返回状态驱动），场景二的拥塞分支必须有 FlexPath 自己的实现与判据。
23. **所有 Request 默认 `PRIO_HIGH`**，业务侧不显式设 LOW，QoS 对照会得到"没差别"。
24. **没有"QoS 总开关"**，A 组基线要构造，不能靠关开关。
25. **`priority_promotion_timeout_us` 默认 10ms**，会吃掉"绝对优先"，是隐性 SLO 上限。
26. **metrics 默认编译关闭**，交付版本不带 `-DTENT_METRICS_ENABLED=ON`，你的看板全空。
27. **`/health` 不是引擎健康**，只是 metrics HTTP 存活。
28. **`logical` 与 `attempts` 是两套账**，用错一套会把 failover 误判为重复投递。
29. **`max_failover_attempts=0` 造 B1 时**，业务重试会掩盖失败，必须固定业务重试策略。
30. **`strict_local_numa` 把性能问题转成可用性问题**，测试环境若开它，可能大量 `DeviceNotFound`。
31. **`shared_quota_shm_path` 残留**（`/dev/shm/mooncake_rdma_slots`）会让重启后的进程行为异常。
32. **CPU-only 环境覆盖不到 staging 与真实 WC 错误**，别把 `cuda-off` 全绿当成数据面通过。
33. **`hp_tcp` 只支持 host memory**，buffer 在 NPU 上会多一次 staging。
34. **`progress_fallback_interval_us=50ms`**：RDMA 完成不唤醒 progress worker，dispatch 窗口最多等 50ms 才补位——它是尾时延的硬下限，别把这段算进"引擎慢"。
35. **被 deadline 丢弃的请求不产生任何指标**，只在状态上体现为 `CANCELED`；不专门看状态，你会漏掉一整类"请求消失了"的故障。
36. **θ_local（`mlu_local_threshold`）设低于 1.0** 会把预测能成功的请求丢掉；官方实测过"丢掉的全是能赶上的"。调参前先读 Worked Example。

---

## 11. 学习资源（已核对，按优先级）

**必读（1–2 天）**

- **TENT 论文**：[arXiv:2604.00368](https://arxiv.org/abs/2604.00368)（HTML 版 [ar5iv](https://ar5iv.labs.arxiv.org/html/2604.00368)）。重点读：设计动机、切片喷洒、故障恢复、对"stuck in fallback"的批评。
- **TENT 关键文档 9 页**（含 tebench，比论文更贴近你手上的代码）：
  [Overview](https://kvcache-ai.github.io/Mooncake/design/tent/overview.html) ·
  [Failover](https://kvcache-ai.github.io/Mooncake/design/tent/failover.html) ·
  [QoS](https://kvcache-ai.github.io/Mooncake/design/tent/qos.html) ·
  [Metrics](https://kvcache-ai.github.io/Mooncake/design/tent/metrics.html) ·
  [Testing](https://kvcache-ai.github.io/Mooncake/design/tent/testing.html) ·
  [Slice Spraying](https://kvcache-ai.github.io/Mooncake/design/tent/slice-spraying.html) ·
  [Transport Selector](https://kvcache-ai.github.io/Mooncake/design/tent/transport-selector.html) ·
  [Deadline Scheduling](https://kvcache-ai.github.io/Mooncake/design/tent/deadline-scheduling.html) ·
  [tebench](https://kvcache-ai.github.io/Mooncake/performance/mooncake/tebench.html)
- **Mooncake 论文**：[ACM TOS, DOI 10.1145/3773772](https://dl.acm.org/doi/10.1145/3773772)（FAST'25 Best Paper）。

**选读（按需）**

- [TENT Roadmap #1058](https://github.com/kvcache-ai/Mooncake/issues/1058)：多 rail 调度、tracing/observability 的规划——"还没做"的能力就是你测试要重点兜的。
- [PR #1984](https://github.com/kvcache-ai/Mooncake/pull/1984)：恢复冷却后的 RDMA rail + failover e2e 测试 → **测试设计的最佳参考**。
- [PR #2155](https://github.com/kvcache-ai/Mooncake/pull/2155)：RDMA transport 失败处理改进，含 `testOnlyIsRailAvailable` 等测试钩子。
- [PR #2764](https://github.com/kvcache-ai/Mooncake/pull/2764)：deadline-infeasible drop + degradation hook——你们"降级处理"模块最该读的一个 PR。
- [PR #2828](https://github.com/kvcache-ai/Mooncake/pull/2828)：在鲲鹏超节点上启用 TENT UB transport（Phase 3），含 `ub_phase3_test_guide.md`。
- 命名变更：[CANN hcomm PR](https://atomgit.com/cann/hcomm/pull/4370) 把 `COMM_PROTOCOL_UBC_CTP` 改为 `UB_CTP`、`UBG` 改为 `UB_RTP`，保留兼容别名。**看到新旧两套名字不要以为是两个东西**。
- 昇腾侧 PD 分离接入：vllm-ascend 的 PD disaggregation 文档（950 产品线默认走 UB 超平面 / UBC 协议，可选 UBG/UBoE）——这是你们环境的直接参考。
- [PR #1519](https://github.com/kvcache-ai/Mooncake/pull/1519)（ubshmem）、[issue #1773](https://github.com/kvcache-ai/Mooncake/issues/1773)（UB via URMA）：理解 UB 在 Mooncake 里的实现路径。

**命令速查（以团队实际工具为准，先用 `-h` 确认语法）**

```bash
npu-smi info
hccn_tool -i <id> -h          # 链路/端口操作，语法以 --help 为准
ethtool / ip -s link          # 端口统计、错包
ib_write_bw / ib_read_lat     # perftest
tc qdisc add ... netem delay|loss
dmesg -T | tail
```

---

## 12. 待确认问题清单（去问 mentor，一次问完）

> 前 7 条我已从公开资料给出**部分答案**，问的时候可以直接说"我查到的是 X，我们这边是不是这样"，效率高很多。

1. **FlexPath 哪些模块是自己写的、哪些直接调 TENT？** 有没有设计文档/接口文档？
2. **"部分网口故障"具体指几个口、哪种故障**（down / 误码 / 拥塞）？拥塞的判定权在 FlexPath 还是 TENT？（公开资料：TENT 不做拥塞换路）
3. **"通过其他 NPU 旁路"的实现方式**：转发几跳、有没有环路检测、peer 怎么选？（公开 TENT 无此能力，确认是自研）
4. **你们用不用 TENT 的 deadline / 准入队列？** 如果用，`enable_runtime_queue`、`deadline_aware`、`θ_local` 现在是什么值？谁来接 `on_local_decode_suggested`（现在是空钩子）？如果不用，场景二就只剩"换路继续传"一条，判据完全不同。
5. **VPC 降级路径的实现**：TCP？`hp_tcp`？加密？带宽上限？（公开：`hp_tcp` 仅 host memory）
6. **EMS 元数据具体是哪些 RPC/消息**？与 KV 是否共用同一物理路径？走 TENT 的 `PRIO_HIGH` 还是另有通道？
7. **QoS 的实现层次**：只用 TENT 的 priority 队列，还是也配了 RDMA `service_level`/`traffic_class` / UB VL / 交换机队列？
8. **降级判定的阈值、观察窗、防抖参数默认值**是多少？可配吗？
9. **验收的对比基线是谁**？有没有历史数据或竞品（NIXL）数据？
10. **TTFT/TPOT 的 SLO 目标值与负载模型**？（模型、上下文、并发、cache 命中率）
11. **测试环境**：几台机器、几个超节点、能否操作交换机、是否有独立环境、注入手段能力边界？
12. **现有哪些测试资产**可以复用（脚本、框架、数据集）？
13. **里程碑**：什么时候要第一版验收报告？与 TENT 上游的关系（fork 还是 patch）？升级策略？

---

## 附录 A：术语表

| 术语 | 含义 |
|---|---|
| PD 分离 | Prefill / Decode 分离部署，KV Cache 需跨节点传输 |
| TTFT / TPOT | 首 token 时延 / 逐 token 间隔（也叫 ITL） |
| KV Cache | 注意力 K/V 缓存，长上下文下体积巨大 |
| GQA / MLA | 分组查询注意力 / 多头潜在注意力，决定 KV 大小 |
| Prefix Cache | 前缀复用，命中率直接影响 TTFT，测试必须固定 |
| TE / TENT | Mooncake Transfer Engine / 其后继运行时 |
| Slice / Spraying | 请求切片 / 多 rail 分散传输 |
| Rail | (local NIC, remote NIC) 一条独立物理路径 |
| Degradation / Reintegration | 降级 / 故障恢复后重新纳入最优路径 |
| Stuck in fallback | 降级后永久回不去（TENT 靠每请求重解避免；FlexPath 若加状态机需自证） |
| UB / 灵衢 | 统一总线（UnifiedBus），超节点互联协议 |
| UBC / UBG | UB 芯片侧端口 / UB 网关侧端口；公开代码中 `UBC_CTP → UB_CTP`（值 4）、`UBG → UB_RTP`（值 9），旧名保留为兼容别名 |
| URMA | 统一远程内存访问，鲲鹏/昇腾上的 UB 编程接口 |
| EMS | 元数据服务（**定义待确认**） |
| VPC | 虚拟私有云网络，降级目标路径 |
| MR / QP / WR / CQ | 内存注册 / 队列对 / 工作请求 / 完成队列 |
| PFC | 优先级流控，拥塞时反压上游，是尾时延的主要成因之一 |
| Admission Queue | 准入队列：请求进 transport 前的排队层，负责 EDF 排序、promotion、deadline 丢弃 |
| MLU | deadline 可行性比值：`(bytes_ahead + length)/bandwidth ÷ 剩余窗口`；<1 预计达标，>1 预计超时 |
| EDF | Earliest Deadline First，最早截止优先 |
| θ_local / `mlu_local_threshold` | 丢弃阈值；预测 MLU 达到它就 CANCELED。官方建议 1.2~1.5，<1.0 会误丢 |
| CANCELED | 被准入队列丢弃后的任务终态；目前不产生指标，只能从状态观察 |
| B0 / B1 / B2 | 无故障基线 / 故障无增强 / 故障有 FlexPath |

## 附录 B：环境自检 Checklist

- [ ] 驱动 / 固件 / CANN / Mooncake commit / FlexPath 版本已记录
- [ ] `npu-smi info` 全部健康，无告警
- [ ] 所有目标端口 link up，速率符合预期
- [ ] 两节点 RPC 互通，metadata 后端（p2p/etcd/redis）可用
- [ ] 最小传输（1MB）成功，再做 1GB 量级
- [ ] 单口 / 多口 / 多 rail 基线带宽已测并记录
- [ ] chrony 时间同步正常
- [ ] CPU 绑核、中断亲和、irqbalance 状态已记录
- [ ] 无其他业务流量干扰，或已量化背景流量
- [ ] 故障注入手段已验证**可注入且可恢复**，并记录能力边界（能否动交换机、UB 口吃不吃 tc）
- [ ] 校验链路已验证能检出人为篡改
- [ ] `-DTENT_METRICS_ENABLED=ON` 已编译，`/metrics` 可抓取
- [ ] `enable_smart_scheduling` 当前值已记录（默认 false）
- [ ] `max_failover_attempts` / `enable_auto_failover_on_poll` 当前值已记录
- [ ] `/dev/shm/mooncake_rdma_slots` 残留情况已确认

## 附录 C：一次故障注入实验的记录模板

```
实验名称：S1-单口故障-传输中注入-32K并发8
日期/版本：2026-11-xx / FlexPath 0.x / Mooncake <commit> / CANN x.x
拓扑：2 超节点 × 4 NPU，NPU3 有 2×UBC
配置：enable_smart_scheduling=false / max_failover_attempts=3 / metrics=on
基线：B0 TTFT p99=1.42s，KV BW=38GB/s（记录日期与配置）
变量：仅关闭 NPU3 的 UBC-1 端口
步骤：
  1. 启动 decode 侧 8 并发 32K 请求
  2. 稳定 60s，记录 B0 段
  3. 注入（记录 T0，精确到 ms）
  4. 观察 120s：TTFT/TPOT/带宽/重试/选路/metrics
  5. 恢复（T1），观察 120s 回切
  6. 全量 checksum + 输出一致性比对 + 守恒等式核对
证据：metrics 截图/JSONL、日志片段（failover/rail 关键字）、曲线链接
预期：失败=0；切换≤500ms；TTFT 劣化≤25%；回切≤60s；错误=0；attempts 增量符合预期
实际：
结论：PASS/FAIL
遗留：
```

---

**最后一句**：这个组件最难的测试不在"造故障"，而在"证明没坏"——KV 传错了不会报错。把 6.3 的三层校验 + 守恒等式做成默认武器，再把 5.2 的"拥塞不降级"这个缺口早点摆到桌面上，你在这个团队的技术话语权就立住了。

