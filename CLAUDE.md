# CNKI Harvest Skill

从知网自动搜索、筛选、下载学术论文 PDF，输出为 paper-distill 兼容格式。

## Repository

https://github.com/dmao29800-jpg/cnki-harvest

## 触发条件

当用户提到以下内容时调用此 Skill：
- "从知网下载论文" / "知网采集" / "知网搜论文" / "批量下载论文"
- "找XX学科的论文" + "知网/CNKI"
- "帮我收集XX领域的文献"
- "搜索知网" + 学科名 + 年份

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 列出所有可用学科
python cli.py --list-disciplines

# 搜索+下载（土木工程，2020-2025，核心期刊，100篇）
python cli.py -d 土木工程 -f 2020 -t 2025 --core -n 100

# 只搜不下（先看有什么）
python cli.py -d 化学 -f 2024 -n 50 --search-only

# 全部期刊，2015至今
python cli.py -d 材料科学与工程 -n 300
```

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-d` | 学科名称（中文，如 土木工程） | 必填 |
| `-f` | 起始年份 | 2015 |
| `-t` | 截止年份 | 2026 |
| `-n` | 最多下载篇数 | 300 |
| `-o` | PDF 输出目录 | ./papers |
| `--core` | 仅北大核心+CSCD期刊 | 否 |
| `--search-only` | 只搜索不下载 | 否 |
| `--list-disciplines` | 列出学科 | — |

## 限速说明

知网限制：30篇/次登录，90篇/天/IP。
工具内置自动限速（每篇间隔 1.5s）、30篇重登、断点续传。
建议：分天分学科跑，`--core` 过滤水刊。

## 输出格式

PDF 命名：`{年份}_{期刊}_{标题}_{第一作者}.pdf`
可直接喂给 paper-distill 做知识蒸馏。

## 三层学科分类

```
工学 → 土木工程 → 结构工程 / 岩土工程 / 桥梁与隧道 / 市政 / 防灾
     → 机械工程 → 机械设计 / 机械制造 / 机械电子 / 车辆
     → 材料科学 → 金属 / 无机 / 高分子 / 复合 / 加工
     → 电气工程 → 电力系统 / 高电压 / 电机 / 电力电子
     → 计算机   → AI / 体系结构 / 软件工程 / 网络安全 / 数据科学
     → 化学工程 → 反应工程 / 分离 / 过程强化 / 能源化工

理学 → 物理学 → 凝聚态 / 原子分子 / 核物理 / 引力天体
     → 化学   → 无机 / 有机 / 物理化学 / 分析 / 高分子
     → 数学   → 基础 / 应用 / 概率统计 / 计算

交叉 → 环境科学 → 水 / 大气 / 固废
     → 生物医学 → 生物材料 / 医学影像
```

## 与 paper-distill 的衔接

```bash
# 1. 用 cnki-harvest 下载论文
python cli.py -d 土木工程 --core -n 100 -o ./papers

# 2. 用 paper-distill 蒸馏
cd ../paper-distill
python cli.py -i ../cnki-harvest/papers -o ./output -c 3
```
