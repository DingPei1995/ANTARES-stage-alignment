# 修正按钮备忘：每个按钮的假设与修正内容

备忘，2026-11-20。列出 QuickAlignment 和 RealSampleCalibration 中所有带修正功能的按钮：输入什么、假设什么、怎么算、改了什么。分两类：

- **模型修正**：改变保存的描述（样品位置 / 高度、托偏移、配置），影响之后所有预测；
- **位置计算**：只填写电机 / 聚焦元件的数值，模型不变。

符号：托坐标点 (x, y, w)，w = 托面高度 + H；SN_f = 标准托 riser 顶面（5.0 mm）位于分析器焦平面时的 SN；Δy = 沿光束相对分析器焦点的位置（+ 为下游）。

## 模型修正

| 按钮（页面） | 输入 / 假设 | 计算 | 改变 |
|---|---|---|---|
| **Correct H**（Samples 页，*Height check*） | 在 SRn 120°、SRz 0° 下，样品上表面位于相机参考线（= 分析器焦平面）时读到的 SN | H = SN − SN_f + 5.0 − 托面高度（`height_from_sn`）；H < 0 时拒绝 | 该样品的 **H**；记住这个 SN（*H checked*），之后 *Bring target onto the beam* 对该样品使用它。精度：目测约 ±0.05 mm，并依赖 SN_f |
| **Found here: correct plate / sample**（Stage & Optics 页） | 所选目标在输入的电机位置下 **位于光斑上且在分析器焦点处**（任意 SRn / SRz；最好在 SRz 0，此时 SN 不变即在焦点）。不使用聚焦元件位置 | 这些电机位置下分析器焦点所在的托坐标点减去目标点：Δx、Δy、ΔH（`found_offset`） | **Δy → 托偏移**（托在样品座中高度不同：所有样品的 SZ 都变）；**Δx → 该样品 x**，**ΔH → 该样品 H**（含其 device；已检查的 SN 随之更新）。Δx 或 ΔH > 0.3 mm 时提醒（配置过时？），托偏移 > 2.5 mm 时提醒（找错样品？） |
| **Move found sample to analyzer focal plane** —— *高度检查*（Stage & Optics 页） | **SRz 转动后**（\|SRz\| ≥ 0.01°）：Target 在输入的电机位置和聚焦元件位置下位于光斑上且聚焦；聚焦元件位置与该目标的预测相差 **超过 0.05 mm** | 按输入的 SN、SRn、SRz、piezo 预测：ST、SZ（目标在光斑上）以及聚焦在其上的聚焦元件位置。用一个高度变化 ΔH 同时拟合 ST、SZ 和聚焦元件的误差（权重：位置 ±0.02 mm，聚焦 zone plate ±0.02 / capillary ±0.10；`fit_height`）。三者剩余误差都 ≤ 0.03 mm 才算 **能解释** | 能解释且回答 *Yes*：目标所在样品的 **H** += ΔH（已检查的 SN 随之更新）。不能解释：不改变任何东西，结果中给出可能原因（托上位置 x、y → 在 SRz 0 用 *Found here*；SRz 轴；SN_f）。capillary：ΔH 精度只有约 ±0.07 mm（会有提示） |
| **Change plate…**（工具栏） | 换了样品托 | – | 样品托；*Found here* 的托偏移清零；样品保留并检查 |
| **Use selected**（*Configuration…*） | 本次 session 使用较早的配置 | – | 当前配置（ST0、SZ0、SN_f、转轴、光学参考） |
| **Apply limits / Defaults**（*Configuration…*，*Motor limits*） | 电机行程 | – | 输入框范围、超程和防碰撞检查；保存在 `configs/motor_limits.json` |
| 工作距离（Stage & Optics 页聚焦元件位置下方的输入框） | 聚焦元件前端的真实距离 | – | 防碰撞实体，仅本次 session |

为什么高度检查要求 SRz 转动：在 SRz 0 时 H 错误只会改变 SN（和聚焦），由 *Correct H* / *Found here* 处理。SRz 转动后，H 错误会让 ST 和聚焦 **同时** 偏（都约正比于 sin SRz）；SRz 轴在垂直光束方向的误差只让聚焦偏，x、y 错误只让 ST / SZ 偏。只有第一种才作为 H 修正。

## 位置计算（模型不变）

| 按钮（页面） | 计算 | 说明 |
|---|---|---|
| **Bring target onto the beam**（Stage & Optics） | 在输入的 SRn、SRz、piezo 下，**SN 不变**（或用该样品高度检查的 SN），求把目标放到光斑上的 ST、SZ（`motors_on_beam`）；给出距分析器焦点的 Δy（> 50 µm 为红色）和消除它所需的 ΔSN | 超程或碰撞时拒绝 |
| **Correct SN**（Stage & Optics） | 把目标放到 **分析器焦点上** 的 SN、ST、SZ（`motors_for_target`） | 绝对计算：依赖 ST0、SZ0、SN_f、转轴 **和 H**（H 错 δ，该点离焦点约 √2·δ） |
| **Move found sample to analyzer focal plane**（移动部分） | 聚焦元件位置 → 焦点的 Δy（光学参考，工作距离不变）；该焦点处的点给出 x、y、H（显示）；**ΔSN = −Δy/√2，ΔST = +Δy/√2**（该点保持在光斑上），聚焦元件 → 对应分析器焦点的位置 | 显示的 H 不保存，除非上面的高度检查成立 |
| **Update schematic & optics**（Stage & Optics） | 光斑位置、聚焦所需的聚焦元件位置、无碰撞范围 | – |
| **Compute new position**（Rotate sample） | 把当前位置光斑下的托坐标点（用到样品的 **H**）转到新的 SRn / SRz：**SN 不变** 时的 ST、SZ 和重新聚焦的聚焦元件位置（`relocate`）；勾选 **Correct SN** 给出放到分析器焦点上的 SN、ST、SZ | H 通过所跟踪的点和 *Correct SN* 起作用 |
| **Send to Stage & Optics tab**（Rotate sample） | 复制所显示的结果 | 超程或碰撞时拒绝 |
| **Centre the piezo: correct ST / SZ / SN and the optic**（Rotate sample、Quick rotation 第 4 步） | 样品在 PIX、PIY ≠ 150 µm 处看到：piezo 偏移是托的平移，ST、SN、SZ 接过它（`same_point`，聚焦元件不动），然后 SN 保持、ST 补偿：该点沿光束滑动 √2·ΔSN，聚焦元件随之重新聚焦（`recentre_piezo`） | 只用到转角和 piezo 方向，不用 ST0 / SZ0 / SN_f / 转轴 |
| **Locate the sample and compute the new position**（Quick sample rotation） | 同 *Move found*：由聚焦元件位置得到焦点处的托坐标点（x、y、H），再绕它 `relocate` | 独立：不使用也不改变其他页 |

## RealSampleCalibration（线站人员）

| 按钮 | 计算 | 改变 |
|---|---|---|
| **Compute** | 用各组数据最小二乘拟合样品台常数（*optics* 模式：ST0、SZ0、光学参考；*full*：再加 SN_f、SRn 和 SRz 轴），按读数误差加权；残差、最不确定的组合、检验点 | 不保存 |
| **Correct the configuration with the test results → new test points** | 找到的检验点作为确认，输入的实际位置作为新方程；重新拟合，生成新一轮 | 不保存 |
| **Save as new configuration** | – | 新文件 `configs/calibration_<日期>_<optic>.json`；QuickAlignment 下次启动时加载每种聚焦元件最新的配置 |
