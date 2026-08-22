import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests


GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
WXPUSHER_APP_TOKEN = os.environ["WXPUSHER_APP_TOKEN"]
WXPUSHER_UID = os.environ["WXPUSHER_UID"]

HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
}

now_utc = datetime.now(timezone.utc)
now_cn = now_utc + timedelta(hours=8)

today = now_cn.strftime("%Y-%m-%d")
yesterday = (now_cn - timedelta(days=1)).strftime("%Y-%m-%d")

# 查询北京时间“昨天”创建的项目，并按 Star 排序
github_response = requests.get(
    "https://api.github.com/search/repositories",
    headers=HEADERS,
    params={
        "q": f"created:{yesterday}",
        "sort": "stars",
        "order": "desc",
        "per_page": 5,
    },
    timeout=30,
)

github_response.raise_for_status()
repositories = github_response.json().get("items", [])

rss_sources = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "https://www.technologyreview.com/feed/",
]

news = []

for source in rss_sources:
    try:
        feed = feedparser.parse(source)

        for item in feed.entries[:5]:
            title = item.get("title", "").strip()
            link = item.get("link", "").strip()

            if title and link:
                news.append((title, link))
    except Exception as error:
        print(f"RSS 获取失败: {source}: {error}")

# 去重
unique_news = []
seen_links = set()

for title, link in news:
    if link in seen_links:
        continue

    seen_links.add(link)
    unique_news.append((title, link))

news = unique_news[:10]

lines = [
    f"# AI 日报 · {today}",
    "",
    f"数据日期：{yesterday}",
    "",
    "## GitHub 昨日最热 5 个新项目",
    "",
]

if repositories:
    for index, repository in enumerate(repositories, start=1):
        name = repository["full_name"]
        url = repository["html_url"]
        stars = repository["stargazers_count"]
        description = repository.get("description") or "暂无项目描述"

        lines.extend(
            [
                f"{index}. [{name}]({url})",
                f"   - Stars：{stars}",
                f"   - {description}",
                "",
            ]
        )
else:
    lines.append("昨天没有查到符合条件的新项目。")
    lines.append("")

lines.extend(
    [
        "## AI 最新消息",
        "",
    ]
)

if news:
    for index, (title, link) in enumerate(news, start=1):
        lines.append(f"{index}. [{title}]({link})")
else:
    lines.append("暂时没有读取到 RSS 新闻。")

content = "\n".join(lines)

# 保存到仓库
report_dir = Path("reports")
report_dir.mkdir(exist_ok=True)

report_file = report_dir / f"{today}.md"
report_file.write_text(content, encoding="utf-8")

# WxPusher 单条消息不要过长
push_content = content[:10000]

push_response = requests.post(
    "https://wxpusher.zjiecode.com/api/send/message",
    json={
        "appToken": WXPUSHER_APP_TOKEN,
        "content": push_content,
        "summary": f"AI 日报 · {today}",
        "contentType": 3,
        "uids": [WXPUSHER_UID],
        "verifyPay": False,
    },
    timeout=30,
)

push_response.raise_for_status()

result = push_response.json()

if result.get("code") != 1000:
    raise RuntimeError(f"WxPusher 推送失败：{result}")

print("日报生成成功：", report_file)
print("WxPusher 推送结果：", result)
