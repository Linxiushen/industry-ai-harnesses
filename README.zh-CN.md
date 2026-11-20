# 行业 Agent 工作台

[**打开在线工作台**](https://linxiushen.github.io/industry-ai-harnesses/) · [架构和许可](ARCHITECTURE.md)

试试输入“设备运维交接”，把工具上限先设为 1，再改为 3。第一次可以看到风险排序和待处理项，第二次可以查看巡检队列、逐条工单和需要人工核对的传感器读数。点击“运行 Agent”会在浏览器中实际计算。也可以切换到制药，输入“检索 COPD 临床试验”，直接检查对应登记编号。

```sh
python agent.py "设备运维交接" --max-tools 3 --out output/shift.json
```

网页使用内置规则规划任务。命令行也能通过 `--local-model 模型名` 接入已在本机运行的兼容模型。

这三个项目面向已有业务流程的团队。临床运营人员需要知道接下来查哪项试验或联系哪个站点，维护计划员每批只有三个巡检名额，电力运营人员则要为次日的负荷和可调时段做安排。三个项目共用一个入口，各自输出可追溯的决策记录。

```sh
python run.py all --out output/decisions.json
```

从仓库根目录运行，Python 3.11 以上即可，无需安装依赖、模型或 API 密钥。控制台显示指标，JSON 保存每条决策。只需运行一个行业时，把 `all` 换成 `pharma`、`manufacturing` 或 `energy`。

| 行业 | 可直接运行的三个业务场景 | 可以怎么验收 |
| --- | --- | --- |
| [制药临床运营](verticals/pharma/README.md) | 临床试验检索、招募站点初筛、结果登记跟进 | 打开检索命中的研究记录，核对站点和状态，再看数据过旧或缺字段时是否转人工。 |
| [制造设备运维](verticals/manufacturing/README.md) | 设备故障风险排序、限额巡检、附传感器读数的工单草稿 | 给模型和基线同样的 300 个巡检名额。在公开合成基准上分别找到 37 和 26 个故障，同时要承担模型的 263 个误报。 |
| [能源负荷运营](verticals/energy/README.md) | 日前逐小时预测、尖峰时段预警、三小时可调负荷排班 | 在相同用电量下比较排班后的日峰值。公开办公楼模型曲线上平均降低 3.3 kW；预测单项则以上周同小时的简单基线更准。 |

选择依据是已有公开工程项目、能获得的免费数据，以及能否把结果落到具体决定。研究团队公开了临床试验检索代码，微软提供设备运维工作流范例，美国国家实验室发布短期负荷预测基准。各目录说明中提供了数据出处、复现方法、评分口径和适用范围。[TrialGPT](https://github.com/ncbi-nlp/TrialGPT) · [微软制造运维项目](https://github.com/microsoft/pdm-fabric-foundry) · [BuildingsBench](https://github.com/NatLabRockies/BuildingsBench)
