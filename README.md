# CNKI Harvest / 知网文献采集

从知网自动搜索、筛选、下载学术论文 PDF，输出为 paper-distill 兼容格式。

## 用法

```bash
# 安装
pip install -r requirements.txt

# 列出所有可用学科
python cli.py --list-disciplines

# 搜索+下载（土木工程，2020-2025，核心期刊，最多100篇）
python cli.py -d 土木工程 -f 2020 -t 2025 --core -n 100

# 只搜不下（预览结果）
python cli.py -d 化学 -f 2024 -n 50 --search-only

# 全部期刊，2015至今，300篇
python cli.py -d 材料科学与工程 -n 300 -o ./材料论文
```

## 参数

| 参数 | 说明 | 默认 |
|------|------|------|
| `-d` | 学科名称 | 必填 |
| `-f` | 起始年份 | 2015 |
| `-t` | 截止年份 | 2026 |
| `-n` | 最多下载篇数 | 300 |
| `-o` | 输出目录 | ./papers |
| `--core` | 仅核心期刊 | 否 |
| `--search-only` | 只搜索不下载 | 否 |
| `--list-disciplines` | 列出学科 | — |

## 限速

知网限制：30篇/次登录，90篇/天/IP。工具内置自动限速和断点续传。

## 输出

PDF 命名格式：`{年份}_{期刊}_{标题}_{第一作者}.pdf`

下载完直接喂给 **[Paper Distill](https://github.com/dmao29800-jpg/paper-distill)** 做知识蒸馏。
