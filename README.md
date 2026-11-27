# 从这里开始

> 一套给"接手 FlexPath 整体测试"的人用的开工材料：一份主文档、一份用例矩阵、一个生成脚本。
> 目标很具体：**今天下午能动手，两周能跑通三大场景的骨架，六周能拿出可签字的验收判据。**
> 说明：个人整理的入门材料，非官方文档；涉及组件实现的部分以团队设计文档为准。

---

## 1. 这套材料解决什么问题

FlexPath 建在 Mooncake TENT 之上，而 TENT 本身已经提供了选路、切片、失败恢复、优先级队列、指标、压测工具和单测框架。所以测试负责人真正的难点不是"写用例"，而是三件事：

1. **分清哪部分能力是上游给的、哪部分是 FlexPath 新写的。** 分不清，就会把上游的已知行为当 bug 提单，也会把"上游本来就没有"的能力漏测。
2. **把"性能提升"变成可证伪的命题。** 没有对照组，"TTFT 降低了"这句话在评审会上不成立。
3. **证明"没坏"。** KV 传错了不会报错，只会输出乱码或答非所问。

这套材料就是围绕这三点组织的。

---

## 2. 四个最该记住的判断

**① 你测的东西，一多半是 TENT 的既有能力。**
先建"上游已有 / FlexPath 新增"的映射，再决定复用上游测试还是从零设计。见《指南》第 4 章。

**② TENT 里有三条互不相同的"降级"，判据完全相反。**

| 路径 | 触发 | 结果 | 判据 |
|---|---|---|---|
| 换路（failover） | transport 返回 `FAILED` | 同一 task 换 fallback transport 继续传 | 传输不失败 |
| deadline 丢弃 | 预测在 deadline 内传不完（需开准入队列） | 任务 `CANCELED`，**不传了** | 该丢就丢、上层知道要重算 |
| 拥塞降级 | 慢但没失败 | 换到 VPC 继续传 | 降级后仍可接受 |

关键事实：TENT 的换路**只由返回状态驱动**，官方文档明确写"没有基于时延的『这条健康但太慢，换一条』信号"。所以**拥塞不会换路**——你们场景二里"拥塞→降级 VPC"这条分支，一定是 FlexPath 自研的。

**③ 场景三最容易"假通过"，因为默认所有请求都是 HIGH。**
`Request.priority` 默认 `PRIO_HIGH`。业务侧没把 KV 显式设成 `PRIO_LOW`，A/B 对照会得到"完全没差别"，然后误判"QoS 不生效"。而且**没有"QoS 总开关"**——"关闭 QoS"的基线只能用"优先级无差异"或"关掉全局 slot"来构造。

**④ 有一个 50ms 的硬下限藏在准入队列里。**
`progress_fallback_interval_us` 默认 50ms：RDMA 完成不唤醒 progress worker，dispatch 窗口最多要等 50ms 才补位。TTFT 判据卡在几十毫秒量级时，这个定时器会直接吃掉预算。单独立一条用例，别把它算成"引擎慢"。

---

## 3. 文件导航

| 文件 | 是什么 | 什么时候看 |
|---|---|---|
| [flexpath-测试入门指南-v2.md](flexpath-测试入门指南-v2.md) | 主文档。TENT 能力地图 → 三场景可执行设计 → 指标体系 → 6 个 lab → 90 天计划 | 现在，按第 0 章顺序读 |
| [flexpath-测试用例矩阵-v2.xlsx](flexpath-测试用例矩阵-v2.xlsx) | 92 条用例（含"观测指标/证据"和"依赖/关键开关"两列）+ 指标判据 + **TENT 配置速查（32 项）** + 风险清单 + 环境矩阵 + 90 天计划 | 做实验前先看「TENT 配置速查」页 |
| [scripts/gen_test_matrix_v2.py](scripts/gen_test_matrix_v2.py) | 上表的生成脚本，带字段数/层级/优先级断言校验 | 要改用例时改脚本重跑，别手改 xlsx |

> xlsx 的「优先级」列是建议值：P0 有 56 条（61%），建议第一周和 PM 一起收敛到 20~25 条作为本阶段门槛，其余降 P1。P0 太多等于没有优先级。

---

## 4. 今天下午就能做的三件事

**第一件（30 分钟）：建立版本指纹。**
照《指南》Lab 0 跑一遍，产出"环境指纹表"。没有这张表，两周后你复现不出今天的结论。

**第二件（2 小时）：把上游测试跑起来。**
不需要 NPU、不需要交换机，任何 Linux/容器都行：

```bash
cmake -S . -B build-tent -DUSE_TENT=ON -DUSE_CUDA=OFF \
  -DWITH_STORE=OFF -DWITH_STORE_RUST=OFF -DBUILD_UNIT_TESTS=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build-tent --target mooncake_common -j
ctest --test-dir build-tent/mooncake-transfer-engine/tent/tests --output-on-failure
```

跑完做一件事：**数一下多少用例被 skip**。被 skip 的（真实 transport、NVLink、GPU 注册）就是将来必须用硬件环境补的洞。这份清单本身就是你进组的第一份交付物。

**第三件（1 小时）：单机 tebench 打通。**
`--backend=tent --xport_type=tcp --check_consistency=true`，拿到第一张带宽/时延曲线。有了它，三个场景的传输层都能先脱离业务跑。

---

## 5. 第一周日历

| 天 | 做什么 | 当天产出 |
|---|---|---|
| D1 | 读《指南》第 2、3 章 + TENT 的 Overview / Failover / Deadline / QoS 四页 | 一页术语表 + 20 条疑问 |
| D2 | Lab 0 + 找 mentor 过架构，**核心问题：哪部分是我们自己写的** | 环境指纹表、模块归属表 |
| D3 | Lab 1：编译 + ctest + 精读三个 failover 测试 | 一页《TENT 怎么测的》，能说清 FakeTransport 能证明/不能证明什么 |
| D4 | Lab 2：单机 tebench + `--check_consistency` + `--split_output_jsonl` | 第一张曲线，第一次区分"提交慢"和"完成慢" |
| D5 | 把《指南》第 9 章的 10 条可测性需求发出去 | 开发确认回执（目标：≥6 条进版本） |

> D5 是整个第一周最有价值的动作。埋点等代码写完再补，成本翻倍，而且很多补不上。

---

## 6. 需要确认的 4 个前提

下面 4 条会显著改变测试方案（完整 13 条见《指南》第 12 章）：

1. **FlexPath 哪些模块是自研、哪些直接调 TENT？** 有没有设计文档？——决定你能复用多少上游测试资产。
2. **"拥塞"的判定权在谁**？TENT 不做换路，那 FlexPath 里是哪段代码、什么阈值？
3. **用不用 TENT 的 deadline / 准入队列**（`enable_runtime_queue`、`deadline_aware`、`θ_local`）？谁来接 `on_local_decode_suggested`？——这决定场景二是"换路继续传"还是"丢弃后重算"，判据完全不同。
4. **测试环境能力边界**：几台机器、能否动交换机、UB 口能不能被置 down / 限速？——UB 口大概率不吃 `tc netem`，这直接决定覆盖度声明怎么写。

---

## 7. 使用边界

- **依据的是公开资料**：TENT 文档 9 页（含 tebench）、arXiv 论文、Mooncake/CANN 的 PR。FlexPath 的实现细节看不到，涉及实现结构的地方标了【待确认】。
- **UB 细节需以你们 fork 为准**：`kunpeng_ub_transport.md` 与 `ub_phase3_test_guide.md` 正文未能完整核对（后者只在 UB 使能的 PR 分支）。
- **tebench 的 flag 会随版本变化**，文档里的命令都要用 `--help` 复核一遍。
- **判据里的数字（25%、40%、500ms、60s）是经验初值**，必须用你们的 B0 基线重标，并在评审时注明出处。

---

## 8. 一页纸的验收判据骨架（可直接拿去开会）

```
在【拓扑 + 故障类型 + 负载 + 配置开关】下：

硬门槛
  □ 在飞请求失败数 = 0（换路场景）；CANCELED 比例符合设计（丢弃场景）
  □ 传输成功率 = 100%（tent_logical_request_outcomes_total）
  □ 静默错误 = 0（checksum + greedy 输出逐位比对）
  □ 重复投递 = 0（logical/attempts 守恒等式）
  □ EMS 元数据 p99 ≤ ___ ms（拥塞下，仅场景三）

性能门槛
  □ TTFT p99 ≤ ___ ms，相对 B0 劣化 ≤ ___%
  □ TPOT p99 劣化 ≤ ___%（仅干扰场景）
  □ 降级期 KV 带宽 ≥ 原路径 ___%
  □ 旁路跳数时延增量 ≤ ___ ms

时序门槛
  □ 故障检测 ≤ ___ ms
  □ 切换/降级完成 ≤ ___ ms
  □ 恢复后 ≤ ___ s 回切，观察窗内切换次数 ≤ 1
  □ dispatch 窗口补位 ≤ 50ms（progress_fallback 上限）
```

把空格填上、标注每格出处、拉开发+PM 签字——这就是你第一个月最重要的交付物，比跑通多少条用例都重要。
