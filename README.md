# Thermal Analysis Radar

一个不用 AI 的热分析潜在应用论文雷达。

## 文件结构

- `fetch_papers.py`：调用 OpenAlex API，抓取近 30 天论文并生成抽取式概括。
- `index.html`：网页前端，内置 CSS 和 JavaScript。
- `data/papers.json`：Python 自动生成的数据。
- `.github/workflows/daily.yml`：每天自动更新数据。
- `requirements.txt`：Python 依赖。

## 第一次在本地运行

```bash
pip install -r requirements.txt
python fetch_papers.py
python -m http.server 8000
```

浏览器打开：

```text
http://localhost:8000
```

不要直接双击 `index.html`，因为浏览器通常不允许 `file://` 页面读取 JSON。
这是浏览器的安全策略，倒不是它今天特别针对你。

## 发布到 GitHub Pages

1. 新建 GitHub 仓库，把全部文件上传到 `main` 分支。
2. 进入 `Settings → Pages`。
3. `Source` 选择 `Deploy from a branch`。
4. Branch 选择 `main`，文件夹选择 `/ (root)`。
5. 保存后等待 Pages 发布。

网站通常位于：

```text
https://你的用户名.github.io/仓库名/
```

## GitHub Actions

进入仓库的 `Actions` 页面，可手动运行：

`Update Thermal Analysis Radar → Run workflow`

工作流也会每天自动运行。

可选：在仓库 `Settings → Secrets and variables → Actions` 中添加：

```text
OPENALEX_EMAIL
```

值填你的联系邮箱。它不是密钥，只用于 OpenAlex 的 polite pool 标识。

## 修改检索范围

编辑 `fetch_papers.py` 顶部的 `SEARCH_QUERY`。

当前范围覆盖：

- 新能源与储能
- 电子与封装
- 高分子与复合材料
- 循环利用
- 医药与生物材料
- 食品与脂质
- 热安全与失效分析

## “概括”是怎么来的

程序不调用 AI。它会：

1. 恢复 OpenAlex 的摘要文本；
2. 给包含 `result`、`show`、`found`、`conclude` 等词的句子加权；
3. 选出最多三句，按原顺序展示；
4. 根据关键词给出热分析技术标签和潜在应用提示。

因此它是抽取式概括，不是中文翻译，也不会凭空发明结论。