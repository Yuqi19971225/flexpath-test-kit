#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 FlexPath 测试资产工作簿：用例矩阵 / 指标判据 / TENT 配置速查 / 风险清单 / 环境矩阵 / 90 天计划。

用例矩阵共 15 列，每条用例绑定到具体的 TENT 配置项、metrics 名或日志关键字；
写入前对字段数、层级取值、优先级取值做断言校验；行高按列宽估算后自适应，避免长文本被裁切。

输出：flexpath-测试用例矩阵-v2.xlsx
"""

import math

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

OUT = "flexpath-测试用例矩阵-v2.xlsx"

TITLE_FILL = PatternFill("solid", fgColor="1F4E79")
HEAD_FILL = PatternFill("solid", fgColor="2E75B6")
BAND_FILL = PatternFill("solid", fgColor="EAF1F8")
P0_FILL = PatternFill("solid", fgColor="FFC7CE")
P1_FILL = PatternFill("solid", fgColor="FFEB9C")
P2_FILL = PatternFill("solid", fgColor="E2EFDA")

WHITE_BOLD = Font(color="FFFFFF", bold=True, size=10)
BODY = Font(size=10)
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

LEVELS = {"L0", "L1", "L2", "L3"}
PRIORITIES = {"P0", "P1", "P2"}


def style_sheet(ws, headers, widths, title, subtitle):
    ws.sheet_view.showGridLines = False
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    c = ws.cell(row=1, column=1, value=title)
    c.font = Font(color="FFFFFF", bold=True, size=14)
    c.fill = TITLE_FILL
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 30

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(headers))
    c = ws.cell(row=2, column=1, value=subtitle)
    c.font = Font(size=9, italic=True, color="595959")
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[2].height = 20

    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=3, column=i, value=h)
        c.font = WHITE_BOLD
        c.fill = HEAD_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BORDER
        ws.column_dimensions[get_column_letter(i)].width = widths[i - 1]
    ws.row_dimensions[3].height = 34
    ws.freeze_panes = "A4"


def fill_rows(ws, rows, start=4, band=True, center_cols=()):
    for r, row in enumerate(rows, start=start):
        for c, val in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=val)
            cell.font = BODY
            cell.border = BORDER
            cell.alignment = Alignment(
                horizontal="center" if c in center_cols else "left",
                vertical="top",
                wrap_text=True,
            )
            if band and r % 2 == 0:
                cell.fill = BAND_FILL


def autofit_rows(ws, widths, start_row, end_row, min_h=18, line_h=13.5, max_h=170):
    """按列宽估算换行行数并设置行高——openpyxl 不会自动调整行高，不设会导致长文本被裁切。"""
    for r in range(start_row, end_row + 1):
        lines = 1
        for c, w in enumerate(widths, start=1):
            v = ws.cell(row=r, column=c).value
            if v is None:
                continue
            text = str(v)
            eff = sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)
            cap = max(w - 1, 6)
            lines = max(lines, math.ceil(eff / cap))
        ws.row_dimensions[r].height = min(max_h, max(min_h, lines * line_h + 4))


# ---------------------------------------------------------------- 说明
wb = Workbook()
ws = wb.active
ws.title = "说明"
ws.sheet_view.showGridLines = False
ws.column_dimensions["A"].width = 22
ws.column_dimensions["B"].width = 112

ws.merge_cells("A1:B1")
c = ws["A1"]
c.value = "FlexPath 测试用例矩阵 v2 · 使用说明"
c.font = Font(color="FFFFFF", bold=True, size=16)
c.fill = TITLE_FILL
c.alignment = Alignment(vertical="center", indent=1)
ws.row_dimensions[1].height = 40

intro = [
    ("这是什么",
     "配套《FlexPath 测试入门指南》的测试资产底稿：用例矩阵 + 指标判据 + 风险清单 + TENT 配置速查 + 环境矩阵 + 90 天计划。"),
    ("怎么用",
     "① 先跑 P0；② 把「通过判据」里的 x/y/z 换成和开发/PM 谈定的数字，并在备注里写明出处（设计文档/实测基线/业务 SLO）；③ 每跑一条更新「状态」列；④ 「依赖/关键开关」列就是你的实验配置清单。"),
    ("ID 规则",
     "FP-M-* 模块级（L0/L1）；FP-S1/S2/S3-* 对应三大验收场景（多为 L2）；FP-P-* 性能与长稳。"),
    ("层级定义",
     "L0 单机/单测（无需真网）；L1 组件集成（2 节点真 UB/RDMA）；L2 场景验收（完整环境）；L3 长稳与混沌。"),
    ("优先级",
     "P0 = 不做完不能验收；P1 = 本版本必须覆盖；P2 = 有余力再补。注意：当前 P0 有 56 条（占 61%），建议第一周与 PM 一起收敛到 20~25 条作为本阶段门槛，其余降为 P1——P0 太多等于没有优先级。"),
    ("重要提醒",
     "所有判据中的百分比/毫秒都是建议初值，必须结合真实模型、真实拓扑、真实 SLO 重新标定后再签字。"),
    ("数据来源",
     "TENT 公开设计文档（Overview / Failover / QoS / Metrics / Testing / Slice Spraying / Transport Selector）、tebench 指南、Mooncake 论文与 PR；FlexPath 实现细节标注为待确认，需与设计文档核对。"),
    ("最大风险点",
     "TENT 有三条互不相同的「降级」路径：failover 换路（只由返回状态驱动，拥塞不触发）、准入队列 deadline 丢弃（CANCELED，钩子为空）、以及 FlexPath 自研的拥塞降级。三者判据相反，验收前必须确认归属，否则用例会写错对象。"),
]
r = 3
for k, v in intro:
    ws.cell(row=r, column=1, value=k).font = Font(bold=True, size=11, color="1F4E79")
    ws.cell(row=r, column=1).alignment = Alignment(vertical="top", indent=1)
    cc = ws.cell(row=r, column=2, value=v)
    cc.font = Font(size=11)
    cc.alignment = Alignment(wrap_text=True, vertical="top")
    r += 1

r += 1
ws.cell(row=r, column=1, value="工作表导航").font = Font(bold=True, size=12, color="1F4E79")
r += 1
nav = [
    ("用例矩阵", "92 条用例，覆盖 7 大模块 + 3 大验收场景 + 性能长稳，每条绑定可观测对象"),
    ("指标与判据", "19 个必测指标的定义、采集方式（含 TENT 指标名）与目标值"),
    ("TENT 配置速查", "影响测试结论的 32 个配置项、默认值与对应用例——做实验前先看这页"),
    ("风险清单", "19 条技术与协作风险（含 9 条来自 TENT 官方 Known Gaps / Known Limits）"),
    ("环境与版本矩阵", "锁版本、锁拓扑、锁开关，保证结论可复现"),
    ("90 天计划", "按周拆解的动作与交付物"),
]
nav_start = r
for k, v in nav:
    ws.cell(row=r, column=1, value="  " + k).font = Font(size=11)
    ws.cell(row=r, column=2, value=v).font = Font(size=11)
    r += 1
autofit_rows(ws, [22, 112], 3, r - 1)

# ---------------------------------------------------------------- 用例矩阵
ws = wb.create_sheet("用例矩阵")
headers = ["用例ID", "层级", "场景/模块", "被测对象", "故障 / 前置条件", "注入 / 构造方式",
           "拓扑", "关键步骤", "观测指标 / 证据", "通过判据", "依赖 / 关键开关",
           "优先级", "自动化", "状态", "备注"]
widths = [13, 6, 12, 12, 28, 24, 16, 32, 28, 30, 24, 6, 8, 7, 20]
style_sheet(ws, headers, widths,
            "FlexPath 测试用例矩阵 v2",
            "P0 先跑通；判据数值需按真实模型/拓扑/SLO 标定后签字；「依赖/关键开关」列即实验配置清单")

rows = [
    # ---------------- 模块级：实例框架
    ("FP-M-001", "L0", "实例框架", "实例框架", "未 destroy 直接再次 init", "进程内重复调用 init", "单机",
     "init → init → 观察返回值与资源", "返回码、QP/MR 计数、日志", "第二次 init 明确报错或幂等成功；无资源翻倍",
     "—", "P0", "是", "待执行", ""),
    ("FP-M-002", "L1", "实例框架", "实例框架", "设备不可用导致 init 失败", "占用/禁用目标设备后 init", "2 节点",
     "制造失败 → 重试 init 3 次", "失败原因码、重试耗时、残留资源", "失败可识别、可重试；重试成功后无脏状态",
     "USE_CUDA=OFF 时 resolveTransport 返回 UNSPEC", "P0", "是", "待执行", "坑：静默半初始化"),
    ("FP-M-003", "L1", "实例框架", "实例框架", "有在飞传输时 destroy", "大块传输中调用 destroy", "2 节点",
     "提交 8GB → 50% 时 destroy", "在飞请求状态、崩溃/挂死、fd 残留", "不崩不挂；返回明确错误；进程可正常退出",
     "—", "P0", "是", "待执行", ""),
    ("FP-M-004", "L1", "实例框架", "实例框架", "进程被 kill -9", "传输中 kill -9 后重启", "2 节点",
     "kill → 重启 → 重新注册/传输", "对端连接残留、重连耗时", "对端 1 个观察窗内清理；重启后传输成功",
     "对端 EndpointStore / retireLocalDevice 行为", "P0", "是", "待执行", ""),
    ("FP-M-005", "L1", "实例框架", "实例框架", "同进程两个实例并发传输", "双实例各 4 并发", "2 节点",
     "并发跑 10 分钟", "两实例指标是否串扰、带宽分配", "互不影响；指标可独立归因",
     "—", "P1", "是", "待执行", ""),
    # ---------------- 连接管理
    ("FP-M-006", "L1", "连接管理", "连接管理", "对端进程挂起形成半开连接", "kill -STOP 对端 60s", "2 节点",
     "挂起 → 发起传输 → 恢复", "超时判定、连接回收、错误码", "按超时失败并可重连；不产生僵尸连接",
     "—", "P0", "是", "待执行", ""),
    ("FP-M-007", "L1", "连接管理", "连接管理", "长时间空闲后突发", "空闲 30min 后突发 100 请求", "2 节点",
     "空闲 → 突发 → 记录首请求时延", "首请求时延 p99、重连次数", "首请求时延 ≤ 稳态 2 倍",
     "—", "P1", "是", "待执行", ""),
    ("FP-M-008", "L1", "连接管理", "连接管理", "连接数达到上限", "并发建链 200/500/1000", "2 节点",
     "阶梯加压至上限", "建链失败率、时延、内存", "达上限有明确报错且不 OOM",
     "—", "P1", "是", "待执行", ""),
    ("FP-M-009", "L1", "连接管理", "连接管理", "对端反复重启（重连风暴）", "对端每 10s 重启一次 ×10", "2 节点",
     "持续观察重连频率与 CPU", "重连次数、CPU、退避曲线", "指数退避生效；CPU 无尖峰",
     "—", "P0", "是", "待执行", ""),
    # ---------------- 异步 IO
    ("FP-M-010", "L0", "异步IO", "异步 IO", "1024 个 range 的大 batch", "构造 1024 range × 4KB", "单机/2 节点",
     "提交 → 统计提交耗时与完成", "提交耗时、完成时延 p99、CPU", "提交耗时符合预算（注意单 range 固定开销）",
     "TENT 按 range 构 Request", "P0", "是", "待执行", "小请求碎片化是固有成本"),
    ("FP-M-011", "L1", "异步IO", "异步 IO", "完成事件乱序返回", "并发多 transport 混合传输", "2 节点",
     "并发 500 请求，比对 request→completion 映射", "错配数、丢失完成数", "映射 100% 正确；无丢失/重复回调",
     "—", "P0", "是", "待执行", ""),
    ("FP-M-012", "L1", "异步IO", "异步 IO", "提交后立即 cancel", "submit 后 0/1/10ms cancel", "2 节点",
     "三档时延 cancel", "cancel 返回值、是否仍回调、数据是否写了一半", "语义明确；不产生半写坏块",
     "—", "P0", "是", "待执行", ""),
    ("FP-M-013", "L1", "异步IO", "异步 IO", "超时边界", "把超时设为传输耗时的 0.5/1/1.5 倍", "2 节点",
     "三档超时参数各跑一轮", "超时误判率、重试次数", "1.5 倍不误判；0.5 倍正确超时并重试",
     "—", "P1", "是", "待执行", ""),
    ("FP-M-031", "L1", "异步IO", "异步 IO / metrics", "一次 failover 后账目是否守恒", "注入单次 poll 阶段失败", "2 节点",
     "跑 1000 次传输 → 制造 1 次 failover → 抓 /metrics", "logical started / outcomes / attempts 三组计数",
     "logical started = outcomes + inflight；attempts 增量 = 1 失败 + 1 成功",
     "TENT_METRICS_ENABLED=ON", "P0", "是", "待执行",
     "守恒等式是「重复投递」最省事的检测手段"),
    ("FP-M-032", "L1", "异步IO", "异步 IO / failover", "failover 预算边界", "max_failover_attempts 取 0 / 1 / 3", "2 节点",
     "三档各注入一次必然失败", "attempt 次数、最终状态、错误文案", "0=不重试直接 FAILED；1=只切一次；3=最多切三次",
     "max_failover_attempts 默认 3", "P0", "是", "待执行", "max_failover_attempts=0 即 B1 基线"),
    ("FP-M-033", "L1", "异步IO", "异步 IO / failover", "poll 观察模式下是否仍自救", "enable_auto_failover_on_poll=false", "2 节点",
     "注入完成后只看 getTransferStatus，不调 wait", "poll 期间状态、failover 计数", "poll 不再触发重投；内部完成路径仍能恢复",
     "enable_auto_failover_on_poll", "P1", "是", "待执行", "用于区分 poll 与 progress 两条恢复路径"),
    # ---------------- 参数配置
    ("FP-M-014", "L0", "参数配置", "参数实例配置", "参数正交组合", "正交表覆盖 transport/rail/超时/校验开关", "单机",
     "逐组合启动并做冒烟传输", "启动成功率、生效配置快照", "全部组合可启动；生效值与配置一致",
     "pairwise 降组合数", "P0", "是", "待执行", ""),
    ("FP-M-015", "L0", "参数配置", "参数实例配置", "非法 / 越界 / 空值", "负值、超大值、空串、类型错", "单机",
     "逐项注入非法配置", "返回值、是否静默取默认", "明确报错；禁止静默降级为默认值",
     "—", "P0", "是", "待执行", "静默取默认是重灾区"),
    ("FP-M-016", "L1", "参数配置", "参数实例配置", "运行中热更新配置", "传输中修改超时/阈值/优先级", "2 节点",
     "改配置 → 观察新请求是否生效", "生效时延、旧配置残留", "新请求按新配置；无重启；无中间态异常",
     "MC_TENT_CONF 是否需重启生效", "P1", "是", "待执行", ""),
    ("FP-M-017", "L1", "参数配置", "参数实例配置", "优先级配置冲突/配反", "EMS 优先级低于 KV", "2 节点",
     "配反后跑拥塞场景", "实际队列映射、元数据 p99", "能检出配置与预期不符并告警",
     "policy.priority 匹配", "P1", "是", "待执行", ""),
    ("FP-M-036", "L1", "参数配置", "Transport Selector", "policy 按 priority / intent 匹配", "配置两组 policy 分别匹配 HIGH 与 LOW", "2 节点",
     "同一端点提交不同 priority/intent 的请求", "命中的 policy name、实际 transport",
     "配置与命中 100% 一致；非法 intent 跳过该条而非变 catch-all",
     "policy[].priority / intent_type", "P0", "是", "待执行",
     "intent 可选 foreground_get/background_prefetch/migration/checkpoint"),
    ("FP-M-037", "L1", "参数配置", "Transport Selector", "transport_hint 固定路径", "hint=TCP 后注入 TCP 失败", "2 节点",
     "提交 hint 请求 → 注入故障", "首次 attempt 的 transport、failover 目标",
     "首次走 hint；failover 时排除 hint，不会绕回失败路径",
     "Request::transport_hint", "P1", "是", "待执行", ""),
    ("FP-M-038", "L1", "参数配置", "Device Selector", "device mask 生效性", "policy.devices 只放 1 张卡", "2 节点",
     "配置后打流，观察每设备流量", "getNicLoadStats 的 device_name 分布",
     "只有指定设备有流量；空列表=全设备（~0ULL）",
     "policy[].devices", "P1", "是", "待执行", ""),
    # ---------------- 设备管理
    ("FP-M-018", "L1", "设备管理", "本地设备管理", "掉卡 / 设备复位", "复位单张 NPU（谨慎，需隔离环境）", "2 节点",
     "复位 → 观察感知与恢复", "感知时延、误用已掉设备次数", "感知 ≤ 秒级；绝不向已掉设备提交",
     "retireLocalDevice / endpoint 隔离", "P0", "否", "待执行", "需环境权限"),
    ("FP-M-019", "L1", "设备管理", "本地设备管理", "多卡多口绑定错误", "故意绑定错误 device_id/端口", "2 节点",
     "错误绑定 → 传输 → 校验", "是否报错、是否走错 rail", "明确报错；不静默走错路径",
     "—", "P1", "是", "待执行", ""),
    ("FP-M-020", "L1", "设备管理", "本地设备管理", "端口状态缓存过期", "端口 down 但缓存仍为 up", "2 节点",
     "down 端口后立即查询健康快照", "快照与实际一致性、更新时间戳", "状态带时间戳；陈旧数据可识别",
     "getNicLoadStats 快照语义", "P1", "是", "待执行", ""),
    # ---------------- 降级处理
    ("FP-M-021", "L1", "降级处理", "降级处理", "降级阈值边界扫描", "丢包 0.1%~10% 逐档", "2 节点",
     "每档稳定 60s，记录是否降级", "降级点、误判率", "降级点落在设计区间；无抖动式反复切换",
     "FlexPath 拥塞判定（自研）", "P0", "是", "待执行", "TENT 侧不会因丢包降级"),
    ("FP-M-022", "L1", "降级处理", "降级处理", "脉冲抖动不应降级", "100ms/500ms/2s 故障脉冲", "2 节点",
     "脉冲注入 ×20 次", "降级次数、回切次数", "短脉冲不降级，或降级后快速回切；切换次数 ≤ 阈值",
     "—", "P0", "是", "待执行", "防抖参数验证"),
    ("FP-M-023", "L1", "降级处理", "降级处理", "长故障后回切", "故障 10min 后恢复", "2 节点",
     "恢复 → 观察路径与带宽", "回切时延、回切后带宽", "≤ 60s 回到原路径且带宽恢复 ≥ 95%",
     "—", "P0", "是", "待执行", "防 stuck-in-fallback"),
    ("FP-M-024", "L1", "降级处理", "降级处理", "链路临界抖动导致 flapping", "每 5s up/down ×20", "2 节点",
     "持续抖动 2 分钟", "切换次数、TTFT 抖动", "切换次数受限（滞后/冷却生效）",
     "rail_cooldown + 防抖窗", "P0", "是", "待执行", ""),
    ("FP-M-025", "L1", "降级处理", "降级处理", "降级事件是否通知上层", "注入降级", "2 节点",
     "观察回调/事件/日志", "通知时延、通知内容完整性", "上层可感知，含原因与当前路径",
     "—", "P1", "是", "待执行", ""),
    ("FP-M-034", "L1", "降级处理", "QoS / 调度", "低优先级是否会被饿死", "持续 HIGH 流量压满 + 少量 LOW 请求", "2 节点",
     "观察 LOW 请求的完成时延分布", "LOW 的完成时延 p99、提升日志",
     "LOW 在 priority_promotion_timeout_us 后被提升并完成，不被无限饿死",
     "priority_promotion_timeout_us=10000（默认）", "P0", "是", "待执行",
     "默认 10ms 提升会削弱「绝对优先」"),
    ("FP-M-035", "L1", "降级处理", "QoS / 全局协调", "多进程 slot 协调与残留", "两进程共享 quota + kill -9 后重启", "2 节点",
     "跑双进程 → kill -9 → 不清理 /dev/shm 直接重启", "slot 轮转、是否自愈、错误日志",
     "共享状态一致；残留可被发现或自动清理",
     "slot_rotation_interval_ms / shared_quota_shm_path", "P1", "是", "待执行",
     "/dev/shm/mooncake_rdma_slots 残留会让行为异常"),
    # ---------------- 内存管理
    ("FP-M-026", "L1", "内存管理", "内存管理", "高频注册 / 注销", "1000 次/分钟 ×10 分钟", "单机",
     "循环 register/unregister", "MR 计数、RSS、失败率", "计数回落；RSS 无单调增长",
     "tent_registered_buffer_bytes", "P0", "是", "待执行", ""),
    ("FP-M-027", "L1", "内存管理", "内存管理", "大块 + 碎片导致分配失败", "交替 8GB/64KB 分配", "单机",
     "制造碎片后申请大块", "失败率、错误码、恢复能力", "失败可识别可恢复；不 hang",
     "—", "P1", "是", "待执行", ""),
    ("FP-M-028", "L1", "内存管理", "内存管理", "跨进程句柄失效", "导出句柄后销毁源进程", "2 节点",
     "失效句柄继续传输", "错误码、是否崩溃", "明确失败；不越界访问",
     "—", "P1", "是", "待执行", ""),
    ("FP-M-029", "L1", "内存管理", "内存管理", "缓冲池耗尽", "并发压至池上限", "2 节点",
     "持续加压观察背压", "排队时延、拒绝策略", "背压生效；不 OOM 不丢数据",
     "—", "P1", "是", "待执行", ""),
    ("FP-M-030", "L0", "内存管理", "内存管理", "destroy 后资源无残留", "init → 传输 → destroy ×50", "单机",
     "循环 50 轮后检查", "fd/线程/MR/RSS", "全部回到初始值 ±噪声",
     "quarantine / teardown 路径", "P0", "是", "待执行", ""),
    ("FP-M-039", "L1", "降级处理", "准入队列 / deadline", "EDF 顺序是否生效", "enable_runtime_queue=true; deadline_aware 开/关", "2 节点",
     "同一时刻提交多个不同 deadline 的请求", "dispatch 顺序、完成顺序", "deadline_aware 开=最早截止先派发；关=FIFO",
     "enable_runtime_queue / deadline_aware", "P1", "是", "待执行", "两条开关都默认关"),
    ("FP-M-040", "L1", "降级处理", "准入队列 / deadline", "deadline-infeasible 丢弃语义", "θ_local=1.2 + 紧 deadline + 拥塞", "2 节点",
     "提交必然超时的请求，观察状态与副作用", "任务终态、指标、目标端是否被部分写",
     "终态为 CANCELED；不产生 deadline 指标；无部分写入；不占 dispatch 预算",
     "mlu_local_threshold", "P0", "是", "待执行", "钩子为空，调用方只能看 CANCELED"),
    ("FP-M-041", "L1", "异步IO", "准入队列 / progress", "dispatch 窗口补位延迟", "RDMA 完成后观察窗口何时补位", "2 节点",
     "单请求完成 → 立即提交新请求 → 测等待", "提交到开始传输的间隔",
     "≤ progress_fallback_interval_us（50ms）；不出现长时间空窗",
     "runtime_queue/progress_fallback_interval_us=50000", "P1", "是", "待执行",
     "RDMA 完成不唤醒 worker，这是尾时延硬下限"),
    # ---------------- 场景一
    ("FP-S1-001", "L2", "场景一 多路径", "连接管理/异步IO", "传输中关闭 1 个 UBC 端口", "主机侧置 down（记录 T0）", "2 超节点 8 NPU",
     "8 并发 32K 稳定 60s → 注入 → 观察 120s", "tent_transport_failover_total、失败数、切换时延、TTFT",
     "在飞失败=0；切换 ≤500ms；TTFT 劣化 ≤25%", "enable_smart_scheduling 与 B2 一致", "P0", "是", "待执行", "核心用例"),
    ("FP-S1-002", "L1", "场景一 多路径", "实例框架/设备管理", "建链前端口已 down", "先 down 再启动", "2 超节点 8 NPU",
     "down → 建立连接 → 传输", "建链失败率、是否自动绕行", "自动选择可用端口；无失败",
     "—", "P0", "是", "待执行", ""),
    ("FP-S1-003", "L2", "场景一 多路径", "多路径调度", "整条 rail 全断", "关闭同 rail 全部端口", "4 节点",
     "传输中全断 → 观察", "剩余带宽、成功率、TTFT", "成功率 100%；带宽 ≥ 设计下界",
     "—", "P0", "是", "待执行", ""),
    ("FP-S1-004", "L1", "场景一 多路径", "降级处理", "链路 flap（1s 周期）", "脚本循环 up/down ×30", "2 节点",
     "flap 期间持续传输", "切换次数、失败数、TTFT p99", "切换次数受限；失败=0",
     "rail_cooldown_secs / Half-Open 单 trial", "P0", "是", "待执行", ""),
    ("FP-S1-005", "L1", "场景一 拥塞", "多路径调度", "单 rail 压至 80% 水位", "tebench 背景流", "2 节点",
     "背景流稳定 → 发起 KV 传输", "P99 Tx、rail 利用率分布", "p99 ≤ 无拥塞 2 倍；流量向空闲 rail 倾斜",
     "enable_smart_scheduling=true", "P0", "是", "待执行", "默认 false 时预期不倾斜"),
    ("FP-S1-006", "L1", "场景一 拥塞", "多路径调度", "单 rail 压至 95% 水位", "tebench 背景流", "2 节点",
     "同上，更高水位", "p50/p99 时延、丢包重传", "不出现时延雪崩；无传输失败",
     "—", "P0", "是", "待执行", ""),
    ("FP-S1-007", "L1", "场景一 拥塞", "异步IO/多路径", "丢包 1% / 5%", "tc netem loss（仅以太网口）", "2 节点",
     "两档各跑 10min", "重传率、有效带宽、TTFT", "1% 下带宽下降 ≤20%；5% 下不失败",
     "—", "P1", "是", "待执行", ""),
    ("FP-S1-008", "L1", "场景一 拥塞", "多路径调度", "注入 1ms / 10ms 固定时延", "tc netem delay", "2 节点",
     "两档各跑一轮", "传输时延增量、是否绕行", "时延增量可解释；必要时绕行",
     "—", "P1", "是", "待执行", ""),
    ("FP-S1-009", "L2", "场景一 旁路", "多路径调度/降级", "主路径全断，经 peer NPU 旁路", "关闭主路径端口", "4 NPU 环状",
     "注入 → 观察是否走旁路 → 校验数据", "旁路成功率、跳数计数、额外时延、数据校验",
     "成功；时延增量 ≤ 阈值；校验 0 错误", "FlexPath 自研，需旁路埋点", "P0", "是", "待执行", "核心用例"),
    ("FP-S1-010", "L2", "场景一 旁路", "多路径调度", "A→B 与 B→A 同时旁路（环路）", "双向断主路径", "4 NPU",
     "构造对称故障", "是否成环、CPU、时延", "无环路；无包风暴",
     "—", "P0", "是", "待执行", ""),
    ("FP-S1-011", "L2", "场景一 旁路", "降级处理", "主路径 + 旁路 peer 同时故障", "先后注入两次故障", "4 NPU",
     "断主路径 30s 后再断 peer", "降级触发、是否 hang", "正确降级到 VPC 或明确失败；不 hang",
     "与场景二衔接点", "P0", "是", "待执行", "两层保护可能互相干扰"),
    ("FP-S1-012", "L2", "场景一 旁路", "多路径调度", "旁路对 peer 本地传输的干扰", "peer 同时跑本地 KV 传输", "4 NPU",
     "旁路开启前后测 peer 本地吞吐", "peer 吞吐下降 %、CPU", "下降 ≤ 15%（需标定）",
     "—", "P1", "是", "待执行", "干扰测试"),
    ("FP-S1-013", "L2", "场景一 多路径", "连接管理", "UBG 侧跨超节点端口故障", "关闭 UBG 上行端口", "2 超节点",
     "跨超节点传输中注入", "成功率、时延、是否降级", "按设计降级/绕行；业务可感知",
     "—", "P0", "是", "待执行", ""),
    ("FP-S1-014", "L2", "场景一 多路径", "设备管理", "光模块误码（非 down）", "物理手段或误码注入", "2 节点",
     "低速率误码下观察重传", "重传率、纠错、是否误判为故障", "可容忍误码；不误判整口故障",
     "—", "P2", "否", "待执行", "视环境能力"),
    ("FP-S1-015", "L2", "场景一 多路径", "Device Selector", "smart scheduling 开/关对照", "同一拥塞负载跑两遍", "2 节点",
     "false（默认 round-robin）与 true 各跑一轮", "P99 Tx、getNicLoadStats 的 ewma 分布",
     "true 相对 false 尾时延改善 ≥ x%；false 下如实记录「不具备拥塞规避」",
     "enable_smart_scheduling 默认 false", "P0", "是", "待执行",
     "不打开就是在测 round-robin，结论会失真"),
    ("FP-S1-016", "L2", "场景一 多路径", "Device Selector / PFC", "closest_tier_only 对 PFC 与尾时延", "构造跨 NUMA 接收 NIC 竞争", "2 节点",
     "开/关 closest_tier_only 各跑一轮", "PFC pause 帧计数、P99 Tx、聚合带宽",
     "开启后 PFC 显著下降、P99 收敛（参考官方 8×H20 实测）",
     "closest_tier_only / numa_penalties", "P1", "是", "待执行",
     "PFC 是拥塞场景最真实的成因"),
    # ---------------- 场景二
    ("FP-S2-001", "L2", "场景二 VPC降级", "降级处理", "触发条件匹配：端口 down", "关闭主路径端口", "2 超节点",
     "注入 → 观察决策依据", "触发条件、决策时延", "按设计条件触发；≤ C ms",
     "max_failover_attempts=3", "P0", "是", "待执行", ""),
    ("FP-S2-002", "L1", "场景二 VPC降级", "降级处理", "触发条件匹配：持续丢包", "5% 丢包持续 30s", "2 节点",
     "注入 → 观察是否降级", "触发阈值、时延", "达到阈值后降级；不早不晚",
     "FlexPath 拥塞判定（TENT 不降级）", "P0", "是", "待执行", ""),
    ("FP-S2-003", "L1", "场景二 VPC降级", "降级处理", "误判：100ms 脉冲", "单次短脉冲 ×20", "2 节点",
     "观察是否降级", "降级次数", "0 次误降级",
     "—", "P0", "是", "待执行", ""),
    ("FP-S2-004", "L1", "场景二 VPC降级", "降级处理", "误判：2s 抖动", "2s 抖动 ×10", "2 节点",
     "观察降级与回切", "降级次数、回切时延", "最多降级 1 次并快速回切",
     "—", "P1", "是", "待执行", ""),
    ("FP-S2-005", "L2", "场景二 VPC降级", "降级处理", "降级生效时延", "端口 down 精确打点", "2 节点",
     "T0 注入 → 首字节走 VPC 的 T1", "T1-T0", "≤ C ms（建议 ≤500ms，按实测标定）",
     "—", "P0", "是", "待执行", ""),
    ("FP-S2-006", "L2", "场景二 VPC降级", "多路径调度/降级", "降级后性能", "稳定降级态 10min", "2 节点",
     "测带宽/TTFT/TPOT", "VPC 带宽、TTFT p99、TPOT p99", "TTFT p99 ≤ SLO；带宽 ≥ 原路径 40%",
     "hp_tcp 仅 host memory", "P0", "是", "待执行", "需先定义「可接受」"),
    ("FP-S2-007", "L2", "场景二 VPC降级", "异步IO/内存管理", "降级期间数据一致性", "2GB 传输中降级", "2 节点",
     "全量校验 + 守恒等式 + 输出比对", "校验错误数、attempts 是否超预期", "均为 0",
     "TENT_METRICS_ENABLED=ON", "P0", "是", "待执行", "核心防线"),
    ("FP-S2-008", "L1", "场景二 VPC降级", "降级处理", "恢复后回切", "故障 5min 后恢复", "2 节点",
     "恢复 → 观察路径与带宽", "回切时延、回切次数、带宽恢复", "≤ 60s 回切；次数 ≤1；带宽 ≥95%",
     "—", "P0", "是", "待执行", ""),
    ("FP-S2-009", "L3", "场景二 VPC降级", "降级处理", "长时间降级不卡死", "故障保持 1h 后恢复", "2 节点",
     "1h 降级 → 恢复 → 观察", "是否回切、冷却探测行为", "必然回切；无 stuck-in-fallback",
     "TENT 每请求重解；FlexPath 状态机自证", "P0", "是", "待执行", "论文明确批评点"),
    ("FP-S2-010", "L1", "场景二 VPC降级", "内存管理/异步IO", "VPC 路径 MTU / 分片", "MTU 1500 与大块传输", "2 节点",
     "大块 KV 走 VPC，MTU 不一致", "分片数、重组失败、CPU", "无重组失败；CPU 增幅可接受",
     "—", "P1", "是", "待执行", ""),
    ("FP-S2-011", "L2", "场景二 VPC降级", "异步IO", "VPC 降级下 TPOT 劣化", "KV 大流量 + decode 并发", "2 节点",
     "降级态跑混合负载", "TPOT p99、CPU 占用、软中断", "TPOT 劣化 ≤ 阈值",
     "—", "P0", "是", "待执行", "TCP 拷贝开销"),
    ("FP-S2-012", "L1", "场景二 VPC降级", "降级处理", "与业务 VPC 流量争抢", "叠加背景业务流", "2 节点",
     "降级 + 背景流共存", "KV 带宽、业务时延", "双方均可接受；无明显饿死",
     "—", "P1", "是", "待执行", ""),
    ("FP-S2-013", "L1", "场景二 VPC降级", "降级处理", "降级中途再次故障", "VPC 也注入丢包", "2 节点",
     "降级后再注入", "是否再次降级/明确失败", "有明确终态；不无限重试",
     "max_failover_attempts 耗尽语义", "P1", "是", "待执行", ""),
    ("FP-S2-014", "L2", "场景二 VPC降级", "降级边界", "拥塞但链路未失败", "压水线至 90% 且不丢包", "2 节点",
     "持续拥塞 5min，观察是否降级", "tent_transport_failover_total、是否走 VPC",
     "明确记录：TENT 不会降级；FlexPath 是否降级按设计判据判定",
     "官方 Known Gaps：无时延信号", "P0", "是", "待执行",
     "本用例的价值是「证伪」而非「证真」"),
    ("FP-S2-015", "L2", "场景二 VPC降级", "降级处理", "降级后新请求是否回到 UB", "降级态持续 5min 后恢复链路", "2 节点",
     "恢复后发起新请求，观察首跳 transport", "新请求的 transport 分布、回切时间",
     "新请求在 ≤ 观察窗 内回到 UB；不存在粘滞降级",
     "TENT 每请求从 priority 0 重解", "P0", "是", "待执行",
     "若粘滞，问题在 FlexPath 状态机"),
    ("FP-S2-016", "L2", "场景二 降级", "降级处理 / 业务协同", "deadline 丢弃后的上层闭环", "KV 带 deadline + 拥塞", "2 节点",
     "CANCELED → 上层本地重算/压缩 → 请求最终成功", "CANCELED 比例、重算耗时、最终成功率、TTFT",
     "该丢的丢了且上层确实处理；最终成功率 100%；TTFT 不劣于硬等传输",
     "on_local_decode_suggested（当前空实现）", "P0", "是", "待执行",
     "这是「保障可接受」的另一条路，判据与换路完全不同"),
    # ---------------- 场景三
    ("FP-S3-001", "L2", "场景三 QoS", "QoS/多路径", "拥塞下关闭 QoS（基线 A）", "压 90% + 元数据请求；KV 也设为 HIGH", "2 节点",
     "跑 10min 采元数据时延", "EMS 元数据 p99、KV 吞吐", "记录基线值（不判 PASS/FAIL）",
     "无「QoS 总开关」，用优先级无差异构造", "P0", "是", "待执行", "对照必需"),
    ("FP-S3-002", "L2", "场景三 QoS", "QoS/多路径", "拥塞下开启 QoS（实验 B）", "同上，EMS=HIGH / KV=LOW", "2 节点",
     "跑 10min 采同样指标", "EMS p99、KV 吞吐", "EMS p99 改善 ≥ x% 且 ≤ 实时性阈值",
     "Request.priority", "P0", "是", "待执行", "核心用例"),
    ("FP-S3-003", "L1", "场景三 QoS", "QoS/多路径", "无拥塞时开 QoS（对照 C）", "低负载", "2 节点",
     "测吞吐与时延", "额外开销 %", "开销 ≤ 3%",
     "—", "P1", "是", "待执行", ""),
    ("FP-S3-004", "L2", "场景三 QoS", "QoS/多路径", "KV 是否被饿死", "全高优先级元数据流量", "2 节点",
     "元数据持续高压 + KV 传输", "KV 吞吐、tent_stage_queue_wait_us", "KV 吞吐下降 ≤ y%；无饿死",
     "priority_promotion_timeout_us", "P0", "是", "待执行", ""),
    ("FP-S3-005", "L1", "场景三 QoS", "Transport Selector", "优先级映射正确性", "配置 priority 与 policy 后抓包/查队列", "2 节点",
     "配置 → 抓包/查队列计数", "实际队列/VL/DSCP 与配置一致性", "100% 一致",
     "service_level / traffic_class", "P0", "是", "待执行", ""),
    ("FP-S3-006", "L2", "场景三 QoS", "QoS/降级", "跨路径优先级一致性", "UBC / UBG / VPC 各跑一轮", "2 超节点",
     "三条路径分别验证", "三路径下 EMS p99 改善", "三条路径均生效（VPC 需 DSCP+TC 保留）",
     "—", "P1", "是", "待执行", ""),
    ("FP-S3-007", "L1", "场景三 QoS", "QoS", "元数据洪峰", "批量注册/查询 10k 次", "2 节点",
     "洪峰期间测时延", "p99、丢弃率", "无丢弃；p99 达标",
     "—", "P1", "是", "待执行", ""),
    ("FP-S3-008", "L1", "场景三 QoS", "参数实例配置", "非法/冲突优先级配置", "非法值、全高优先级", "2 节点",
     "逐项配置并观察", "报错、实际生效值", "明确报错；全高时有兜底策略",
     "—", "P1", "是", "待执行", ""),
    ("FP-S3-009", "L1", "场景三 QoS", "QoS", "运行中动态改优先级", "运行中切换优先级", "2 节点",
     "切换 → 观察生效与流量中断", "生效时延、是否丢包", "生效 ≤1s；无丢包",
     "—", "P2", "是", "待执行", ""),
    ("FP-S3-010", "L2", "场景三 QoS", "QoS/基准工具", "tebench A/B/C 三组对照", "qos_classes 固定线程分配", "2 节点",
     "三组各跑 10min，导出 JSONL", "slo_attainment、p99_us、goodput_gbps、jain_fairness、isolation_leakage",
     "B 组 relative to A 有可量化改善；C 组开销 ≤ 阈值",
     "--qos_classes / --qos_output_jsonl", "P0", "是", "待执行",
     "tebench 仅报告口径，不改变调度策略"),
    ("FP-S3-011", "L2", "场景三 QoS", "QoS/调度", "优先级提升阈值扫描", "priority_promotion_timeout_us 取 10ms/100ms/1s", "2 节点",
     "KV 洪峰下三档各跑 10min", "EMS p99 曲线与拐点", "拐点不在 SLO 附近；默认值满足实时性要求",
     "priority_promotion_timeout_us（默认 10000us）", "P0", "是", "待执行",
     "默认 10ms 是隐性 SLO 上限"),
    ("FP-S3-012", "L1", "场景三 QoS", "QoS/策略", "intent_type 级策略绑定", "foreground_get vs background_prefetch", "2 节点",
     "用 intent 而非手工 priority 提交", "命中的 policy、实际 transport/队列",
     "intent 正确映射到预期策略与路径",
     "policy[].intent_type", "P1", "是", "待执行",
     "更贴近业务侧真实接入方式"),
    ("FP-S3-013", "L2", "场景三 QoS", "QoS / deadline 仲裁", "优先级与卡内仲裁叠加", "HIGH 小包持续 + LOW 大包带紧 deadline", "2 节点",
     "开 deadline_bw_arbitration，观察 LOW 的 deadline 达成", "tent_deadline_mlu_permille、LOW 的 p99",
     "HIGH 始终优先（设计如此）；LOW 的 deadline 被挤压程度可量化并写入判据",
     "deadline_bw_arbitration（仅 tier 内重排）", "P1", "是", "待执行",
     "既验证「元数据优先」，也验证没有「保元数据饿死数据」"),
    # ---------------- 性能 / 长稳
    ("FP-P-001", "L2", "性能基线", "全链路", "无故障基线矩阵 B0", "固定模型/数据集/seed", "完整环境",
     "上下文 4K/16K/32K/128K × 并发 1/8/32", "TTFT/TPOT/带宽/吞吐", "形成基线表 + 曲线，作为所有劣化判据分母",
     "—", "P0", "是", "待执行", "先做这个"),
    ("FP-P-002", "L2", "性能基线", "全链路", "TPOT 干扰测试", "KV 大流量背景 + decode", "完整环境",
     "有/无背景流量对比", "TPOT p50/p99、CPU、软中断", "TPOT 劣化 ≤ 阈值",
     "—", "P0", "是", "待执行", "最易漏项"),
    ("FP-P-003", "L1", "性能基线", "异步IO", "小请求碎片化", "4KB~64KB × 1000 range", "2 节点",
     "测提交与完成开销", "单 range 开销、CPU、总耗时", "符合预算；不出现数量级劣化",
     "tebench --split_output_jsonl", "P1", "是", "待执行", "TENT 固有成本"),
    ("FP-P-004", "L3", "长稳", "全模块", "72h 长稳 + 随机故障注入", "每小时随机注入 1 次", "完整环境",
     "72h 连续跑，记录全指标", "fd/QP/MR/RSS/HBM 斜率、失败率、endpoint_rebuilds", "斜率≈0；失败率 0；恢复后回基线带",
     "TENT_METRICS_ENABLED=ON", "P0", "是", "待执行", ""),
    ("FP-P-005", "L2", "性能回归", "全链路", "版本间性能回归", "同环境同负载跑新版本", "完整环境",
     "与上一版本基线对比", "TTFT/KV 带宽差异 %", "劣化 ≤5%，否则阻断",
     "—", "P0", "是", "待执行", "进 CI"),
    ("FP-P-006", "L2", "对标", "全链路", "与经典 TE / 竞品对比", "相同负载", "完整环境",
     "B1 基线跑同一用例", "TTFT/带宽/故障恢复", "形成对比表，量化收益",
     "--backend=classic", "P2", "是", "待执行", "对外汇报用"),
]

# ---- 数据完整性校验（v1 的 bug 就是没做这一步）
for row in rows:
    assert len(row) == len(headers), f"{row[0]} 字段数 {len(row)} != {len(headers)}"
    assert row[1] in LEVELS, f"{row[0]} 层级非法: {row[1]}"
    assert row[11] in PRIORITIES, f"{row[0]} 优先级非法: {row[11]}"

fill_rows(ws, rows, center_cols=(1, 2, 3, 4, 12, 13, 14))
for r in range(4, 4 + len(rows)):
    p = ws.cell(row=r, column=12)
    p.fill = {"P0": P0_FILL, "P1": P1_FILL, "P2": P2_FILL}.get(p.value, p.fill)
    p.font = Font(size=10, bold=(p.value == "P0"))
ws.auto_filter.ref = f"A3:O{3 + len(rows)}"
autofit_rows(ws, widths, 4, 3 + len(rows))

# ---------------------------------------------------------------- 指标与判据
ws = wb.create_sheet("指标与判据")
headers = ["#", "指标", "层级", "定义 / 公式", "采集方式（含 TENT 指标名）", "建议频率", "基线 (B0)", "目标 / 判据", "备注"]
widths = [5, 22, 9, 40, 40, 12, 16, 30, 24]
style_sheet(ws, headers, widths, "指标与判据",
            "「基线」列先留空，跑完 FP-P-001 后回填；判据数值须与开发/PM 签字确认")

metrics = [
    (1, "TTFT p50/p90/p99", "业务", "请求发出 → 首 token 返回", "客户端 benchmark", "每用例", "", "分场景设定，长上下文建议 ≤ 2s", "必须分长度/并发"),
    (2, "TPOT p99", "业务", "相邻输出 token 间隔的 p99", "客户端 benchmark", "每用例", "", "劣化 ≤ 阈值（如 10%）", "需单独做干扰场景"),
    (3, "有效 KV 带宽", "KV", "传输字节 / (完成-提交)", "rate(tent_read_bytes_total[1m]) 或 tebench BW", "每请求", "", "≥ 设计值的 90%", "区分 line rate 与 goodput"),
    (4, "单请求 KV 传输时延 p99", "KV", "单逻辑请求端到端", "tent_read_latency_us / tent_write_latency_us 的 quantile", "每请求", "", "随上下文长度设阈值", "与 TTFT 交叉验证"),
    (5, "传输成功率", "KV", "成功请求 / 总请求", "tent_logical_request_outcomes_total{outcome=success}", "每用例", "", "= 100%", "任何失败都要归因"),
    (6, "静默错误率", "KV", "校验失败块 / 总块数", "CRC/SHA + 端到端输出比对", "每用例", "", "= 0", "最底线指标"),
    (7, "重复投递率", "KV", "attempts 超出预期的比例", "tent_transport_attempts_total vs logical started 守恒", "每用例", "", "= 0", "比写入计数器更易落地"),
    (8, "故障检测时延", "传输", "故障发生 → 首次重试/改路", "注入时间戳 + 日志 'Transport failover'", "每次注入", "", "≤ 100ms（标定）", "场景一核心"),
    (9, "切换完成时延", "传输", "故障 → 新路径承载流量", "注入时间戳 + 新 transport 的 attempts 起量", "每次注入", "", "≤ 500ms（标定）", "场景一核心"),
    (10, "降级生效时延", "传输", "故障 → VPC 承载流量", "同上 + FlexPath 埋点", "每次注入", "", "≤ 500ms（标定）", "场景二核心"),
    (11, "回切时延", "传输", "恢复 → 回最优路径", "FlexPath 状态机日志 + transport 分布", "每次注入", "", "≤ 60s", "防 stuck-in-fallback"),
    (12, "回切次数（抖动）", "传输", "观察窗内路径切换次数", "状态机日志", "每次注入", "", "≤ 1", ""),
    (13, "降级期带宽保持率", "传输", "降级带宽 / 原带宽", "tebench 前后对比", "每用例", "", "≥ 40%", "场景二软目标"),
    (14, "per-rail 利用率均衡度", "传输", "max(利用率)/avg(利用率)", "getNicLoadStats 的 inflight/ewma 分布", "每用例", "", "≤ 1.5", "验证切片喷洒效果"),
    (15, "分阶段耗时占比", "传输", "队列/分发/传输各阶段占比", "tent_stage_queue_wait_us / dispatch / transport", "每用例", "", "排队占比异常升高需归因", "分层归因的第一手证据"),
    (16, "资源泄漏（72h）", "资源", "fd/QP/MR/RSS/HBM 增长斜率", "tent_inflight_attempts / tent_registered_buffer_bytes + 周期采样", "1/min", "", "斜率 ≈ 0", "长稳必测"),
    (17, "旁路对 peer 的干扰", "资源", "peer 本地吞吐下降 %", "对比打流", "每用例", "", "≤ 15%（标定）", "场景一旁路"),
    (18, "deadline 达成率", "KV", "MLU ≤ 1000 的请求占比", "tent_deadline_mlu_permille histogram", "每用例", "", "按业务 SLO 定", "需开准入队列且请求带 deadline"),
    (19, "丢弃准确性（误丢率）", "KV", "被丢弃中实际本可按时完成的比例", "CANCELED 计数 × tent_deadline_mlu_permille 实测分布交叉验证", "每用例", "", "误丢 = 0", "θ_local < 1.0 会误丢"),
]
fill_rows(ws, metrics, center_cols=(1, 3, 6))
autofit_rows(ws, widths, 4, 3 + len(metrics))

# ---------------------------------------------------------------- TENT 配置速查
ws = wb.create_sheet("TENT 配置速查")
headers = ["配置项", "默认值", "作用 / 影响", "对应用例"]
widths = [44, 16, 62, 22]
style_sheet(ws, headers, widths, "TENT 配置速查（做实验前先看这页）",
            "来源：TENT 公开设计文档；默认值以文档为准，落地前用自己 fork 的代码/配置再核对一遍")

configs = [
    ("transports/rdma/enable_smart_scheduling", "false", "EWMA 智能选路；关闭时是 NUMA 层内 round-robin，不具备拥塞规避", "FP-S1-005/015, FP-S1-003"),
    ("transports/rdma/numa_penalties", "[1.0, 5.0, 10.0]", "跨 NUMA NIC 的惩罚倍数", "FP-S1-016"),
    ("transports/rdma/strict_local_numa", "false", "直接排除跨 NUMA NIC；把性能问题转成可用性问题（可能 DeviceNotFound）", "FP-S1-016"),
    ("transports/rdma/closest_tier_only", "false", "两端都只用最近 NIC 层；官方实测可显著降低 PFC 与 P99", "FP-S1-016"),
    ("transports/rdma/bandwidth_learning_rate", "0.01", "选路 EWMA 学习率（越小适应越快）", "FP-S1-005"),
    ("transports/rdma/default_bandwidth_gbps", "400.0", "端口速率不可知时的假定带宽", "FP-S1-003"),
    ("enable_auto_failover_on_poll", "true", "poll 是否自动触发 failover；false 时 poll 仅观察", "FP-M-033"),
    ("max_failover_attempts", "3", "每 task 的 failover 上限；0=完全关闭（B1 基线），1=只切一次", "FP-M-032, FP-S2-001"),
    ("transports/rdma/rail_error_threshold", "3", "窗口内错误数达阈值→暂停 rail", "FP-S1-004, FP-M-024"),
    ("transports/rdma/rail_error_window_secs", "10", "错误计数滑动窗口", "FP-M-024"),
    ("transports/rdma/rail_cooldown_secs", "30", "初始冷却；跨恢复周期翻倍，上限 300s", "FP-S1-004, FP-S2-008"),
    ("transports/rdma/rail_probe_interval_secs", "1", "暂停期探针间隔；0 关闭探测", "FP-S2-009"),
    ("transports/ub/endpoint_cooldown_ms", "1000", "UB rail 冷却时间（阈值 3 次 / 10s）", "FP-S1-013"),
    ("transports/rdma/enable_priority_filtering", "true", "优先级感知的设备过滤", "FP-S3-005"),
    ("transports/rdma/priority_promotion_timeout_us", "10000", "低优先级等待多久被提升（防饿死，同时削弱绝对优先）", "FP-M-034, FP-S3-011"),
    ("transports/rdma/priority_promotion_per_entry", "false", "false=整队提升；true=逐条提升", "FP-S3-004"),
    ("transports/rdma/slot_rotation_interval_ms", "2", "多进程全局 slot 轮转间隔（3 slot，默认 6ms 周期）", "FP-M-035, FP-S3-006"),
    ("transports/rdma/shared_quota_shm_path", "\"\"", "为空则关闭全局协调；残留 /dev/shm 会导致异常", "FP-M-035"),
    ("metrics/enabled", "false（编译期默认关）", "需 -DTENT_METRICS_ENABLED=ON；否则 /metrics 全空", "FP-M-031, FP-S2-007"),
    ("policy[].priority", "—", "按 high/medium/low 匹配请求", "FP-M-036, FP-S3-005"),
    ("policy[].intent_type", "INTENT_UNSPEC", "foreground_get/background_prefetch/migration/checkpoint/...", "FP-M-036, FP-S3-012"),
    ("policy[].transports", "—", "按顺序回退，如 [\"ub\",\"rdma\",\"tcp\"]", "FP-S2-001, FP-S2-014"),
    ("Request::priority", "PRIO_HIGH", "请求优先级；默认 HIGH 是 QoS 假阴性的头号原因", "FP-S3-001/002"),
    ("Request::transport_hint", "UNSPEC", "单请求固定 transport；failover 时排除 hint", "FP-M-037"),
    ("enable_runtime_queue", "false", "请求是否经过准入队列；关闭则下面的 deadline 行为全部不存在", "FP-M-039/040"),
    ("runtime_queue/deadline_aware", "false", "EDF 排序；关闭时 FIFO", "FP-M-039"),
    ("runtime_queue/promotion_slack_ns", "0", "剩余松弛低于此值则插队；0 关闭", "FP-M-039"),
    ("runtime_queue/mlu_local_threshold", "0.0", "θ_local；0 关闭丢弃，<1.0 会误丢，建议 1.2~1.5", "FP-M-040, FP-S2-016"),
    ("runtime_queue/max_dispatch_bytes", "67108864", "单请求超过 64MiB 会在 submit 被拒", "FP-M-010"),
    ("runtime_queue/progress_fallback_interval_us", "50000", "RDMA 完成不唤醒 worker，靠 50ms 定时器补窗口——尾时延下限", "FP-M-041"),
    ("transports/rdma/deadline_bw_arbitration", "false", "卡内按紧迫度排序，仅在同一 priority tier 内", "FP-S3-013"),
    ("Request::deadline_ns", "0", "绝对 steady_clock 截止时间；0=无 deadline，永不重排/提升/丢弃", "FP-M-040, FP-S2-016"),
]
fill_rows(ws, configs)
autofit_rows(ws, widths, 4, 3 + len(configs))

# ---------------------------------------------------------------- 风险清单
ws = wb.create_sheet("风险清单")
headers = ["#", "风险描述", "类别", "影响", "可能性", "验证 / 发现手段", "缓解措施", "责任方", "状态"]
widths = [5, 48, 10, 8, 8, 34, 30, 10, 8]
style_sheet(ws, headers, widths, "风险清单", "按「影响 × 可能性」排序，P0 用例优先覆盖高影响项")

risks = [
    (1, "KV 数据静默错误：传错不报错，只输出乱码", "正确性", "极高", "中", "三层校验 + 守恒等式", "测试默认开启校验模式", "测试", "Open"),
    (2, "拥塞不会触发 TENT failover（只由返回状态驱动），场景二拥塞分支可能根本没实现", "功能", "高", "高", "FP-S2-002 / FP-S2-014", "与开发确认归属；在 FlexPath 内实现判定", "开发", "Open"),
    (3, "降级后永久卡死（stuck in fallback）——风险在 FlexPath 状态机，不在 TENT", "可用性", "高", "中", "FP-S2-009 / FP-S2-015", "冷却探测 + 强制回切周期", "开发", "Open"),
    (4, "链路抖动导致降级/回切 flapping，性能雪崩", "性能", "高", "高", "FP-M-024 / FP-S1-004", "滞后 + 冷却窗口", "开发", "Open"),
    (5, "故障重投导致重复写 / 覆盖新数据（ShmTransport 类提交失败可能重复投递）", "正确性", "极高", "中", "FP-M-031 + checksum", "task-id 去重语义；owner/alias 处理", "开发", "Open"),
    (6, "旁路经 peer NPU 引入环路或拖垮 peer（TENT 无此能力，纯自研）", "可用性", "高", "中", "FP-S1-010 / 012", "防环 + 旁路流量限额", "开发", "Open"),
    (7, "VPC 降级后带宽不足，TTFT 直接破 SLO", "性能", "高", "高", "FP-S2-006 / 011", "请求侧策略配合（缩 batch/放宽 SLO）", "产品+开发", "Open"),
    (8, "QoS 只在部分路径生效（尤其 VPC）", "功能", "中", "中", "FP-S3-006", "映射层统一 + 抓包验证", "开发", "Open"),
    (9, "默认所有 Request 都是 PRIO_HIGH，业务侧未设 LOW 导致 QoS 测试假阴性", "测试有效性", "高", "高", "FP-S3-001 的 A 组构造检查", "用例强制校验业务侧优先级设置", "测试", "Open"),
    (10, "priority_promotion 10ms 默认值削弱元数据绝对优先，EMS SLO 可能不达标", "性能", "中", "中", "FP-S3-011 / FP-M-034", "按 SLO 调大提升阈值", "开发+产品", "Open"),
    (11, "元数据高优先级把 KV 饿死", "性能", "中", "中", "FP-S3-004", "配额/权重下限", "开发", "Open"),
    (12, "完成事件丢失/乱序导致请求 hang", "功能", "高", "低", "FP-M-011 / 013", "超时兜底 + 完成看护", "开发", "Open"),
    (13, "资源泄漏（QP/MR/fd）在长稳中累积", "稳定性", "高", "中", "FP-P-004 / FP-M-030", "destroy 断言 + 定期审计", "测试", "Open"),
    (14, "metrics 编译期默认关闭，交付版本无指标，看板与判据全部失效", "可观测性", "高", "中", "交付前检查 build_info 指标存在", "CI 强制 -DTENT_METRICS_ENABLED=ON", "测试+开发", "Open"),
    (15, "测试环境不具备物理/交换机级注入能力；UB 口可能不吃 tc", "测试能力", "中", "高", "环境盘点（Lab 4）", "主机侧模拟 + 明确覆盖度声明", "测试+运维", "Open"),
    (16, "版本矩阵未锁定，结论不可复现", "流程", "中", "高", "环境矩阵表", "每份报告记录版本指纹", "测试", "Open"),
    (17, "CPU-only 环境（cuda-off）全绿被误认为数据面通过；staging 与真实 WC 错误未覆盖", "测试有效性", "高", "中", "核对 skip 用例清单", "硬件 CI 兜底；报告标注覆盖边界", "测试", "Open"),
    (18, "deadline 丢弃不通知上层（空 DegradationHooks），请求可能被静默放弃", "可用性", "高", "中", "FP-M-040 / FP-S2-016", "FlexPath 自己接钩子或轮询 CANCELED", "开发", "Open"),
    (19, "progress_fallback 50ms 定时器成为尾时延下限，TTFT 判据可能被它吃掉", "性能", "中", "中", "FP-M-041", "按 SLO 调小该间隔或改唤醒机制", "开发", "Open"),
]
fill_rows(ws, risks, center_cols=(1, 3, 4, 5, 8, 9))
autofit_rows(ws, widths, 4, 3 + len(risks))

# ---------------------------------------------------------------- 环境矩阵
ws = wb.create_sheet("环境与版本矩阵")
headers = ["维度", "候选值", "是否锁定", "本次锁定值", "获取方式", "说明"]
widths = [20, 46, 10, 26, 24, 40]
style_sheet(ws, headers, widths, "环境与版本矩阵", "每份测试报告的首页都应附上这张表的「本次锁定值」")

envs = [
    ("CANN 版本", "8.x / 9.x", "是", "", "npu-smi / 驱动安装包", "与 FlexPath 编译期强耦合"),
    ("NPU 驱动 / 固件", "随 CANN 配套", "是", "", "npu-smi info -t board", "固件不一致会导致诡异问题"),
    ("Mooncake 版本", "commit / tag", "是", "", "git rev-parse HEAD", "TENT 演进快，必须记 commit"),
    ("FlexPath 版本", "组件版本号", "是", "", "构建产物信息", ""),
    ("推理框架", "vLLM / vLLM-Ascend / MindIE 版本", "是", "", "pip / 镜像", "连接器行为随版本变化"),
    ("模型", "参数量 / 结构(GQA/MLA) / 精度", "是", "", "config.json", "决定 KV 大小"),
    ("拓扑", "超节点数 / NPU 数 / rail 数", "是", "", "拓扑图", "影响多路径结论"),
    ("UB 端口配置", "UBC 数 / UBG 数 / 速率", "是", "", "hccn_tool / 文档", ""),
    ("注入手段", "主机 / 交换机 / 物理", "是", "", "能力盘点", "决定覆盖度"),
    ("smart scheduling", "true / false", "是", "", "transfer-engine.json", "默认 false，必须记录"),
    ("failover 预算", "max_failover_attempts 值", "是", "", "transfer-engine.json", "决定 B1 基线"),
    ("metrics 开关", "编译期 + 运行期", "是", "", "cmake flag / 配置", "默认编译关闭"),
    ("背景流量", "有 / 无 / 水位", "是", "", "打流配置", "污染基线的头号原因"),
    ("时间同步", "chrony 状态", "是", "", "chronyc tracking", "时延分解的前提"),
]
fill_rows(ws, envs, center_cols=(3,))
autofit_rows(ws, widths, 4, 3 + len(envs))

# ---------------------------------------------------------------- 90 天计划
ws = wb.create_sheet("90 天计划")
headers = ["周次", "主题", "关键动作", "交付物", "完成标准"]
widths = [8, 22, 62, 36, 36]
style_sheet(ws, headers, widths, "90 天入门计划", "按周推进；每周五出一页纸进展（数字 + 图 + 阻塞项）")

plan = [
    ("D1-D2", "术语与架构", "读指南第 2/3 章 + TENT Overview/Failover/QoS；找 mentor 过架构（重点问哪部分自研）", "术语表、20 条疑问、模块归属表", "能独立讲清一次 KV 传输的 8 个步骤，并说清哪些是 TENT 原生"),
    ("D3", "跑通上游测试", "Lab 1：编译 + ctest；精读三个 failover 测试", "一页《TENT 怎么测的》", "能说清 FakeTransport 能证明什么、不能证明什么"),
    ("D4", "单机 baseline", "Lab 2：tebench 单机 + --check_consistency + --split_output_jsonl", "第一张带宽/时延曲线", "能自己从 0 跑出可复现的一组数字"),
    ("D5", "可测性需求", "发出 10 条诉求（指南第 9 章），标注「上游已有」", "开发确认回执", "开发认可其中 ≥6 条进入版本"),
    ("W2", "基线与注入", "跑 B0 矩阵；验证注入手段能力边界（UB 口能否 down/限速）", "基线报告 v1、fault.py", "注入-恢复闭环 100%；B0 覆盖 4 档上下文 × 3 档并发"),
    ("W3", "场景一", "多路径 + 旁路 P0 用例；smart scheduling 开/关对照", "场景一报告 v1", "P0 用例 60% 通过或缺陷已提单；有跳数代价曲线"),
    ("W4", "判据定稿", "场景二/三用例评审；与开发/PM 对齐 SLA 数值", "《验收判据 v0.1》", "三方签字；每条判据有指标名 + 采集方式"),
    ("W5-W6", "场景二", "故障分支（TENT）与拥塞分支（自研）分开验；回切与长故障", "场景二报告", "两条分支都能单独证明；无 stuck-in-fallback"),
    ("W7-W8", "场景三", "A/B/C 对照 + priority_promotion 扫描 + 跨路径一致性", "场景三报告", "B vs A 有可量化改善；C 无显著开销"),
    ("W9-W10", "框架化", "场景即代码重构；L0/L1 进 CI", "测试框架 v1", "新用例接入 ≤ 30 分钟"),
    ("W11-W12", "长稳与回归", "72h 长稳 + 混沌；性能回归看板", "长稳报告、看板", "泄漏斜率≈0；回归门禁生效"),
    ("W13", "总结与规划", "输出测试体系文档；下阶段风险与投入建议", "体系文档 + 规划", "可交接、可复用"),
]
fill_rows(ws, plan, center_cols=(1,))
autofit_rows(ws, widths, 4, 3 + len(plan))

wb.save(OUT)
print("saved", OUT)
print("cases:", len(rows), "metrics:", len(metrics), "risks:", len(risks),
      "configs:", len(configs), "plan:", len(plan))
