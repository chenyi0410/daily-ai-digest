import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests


GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
WXPUSHER_APP_TOKEN = os.environ["WXPUSHER_APP_TOKEN"].strip()
WXPUSHER_UID = os.environ["WXPUSHER_UID"].strip()
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"].strip()

if not WXPUSHER_APP_TOKEN:
    raise RuntimeError("WXPUSHER_APP_TOKEN 为空")

if not WXPUSHER_UID:
    raise RuntimeError("WXPUSHER_UID 为空")

if not DEEPSEEK_API_KEY:
    raise RuntimeError("DEEPSEEK_API_KEY 为空")


GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
}

DEEPSEEK_HEADERS = {
    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    "Content-Type": "application/json",
}


def summarize_with_deepseek(text: str, kind: str) -> str:
    if kind == "project":
        instruction = (
            "请用一句简短、准确的中文介绍这个 GitHub 项目的主要用途。"
            "只输出一句话，不要标题、编号、Markdown、引号或免责声明。"
        )
    else:
        instruction = (
            "请用一句简短、准确的中文总结这条 AI 新闻的核心内容。"
            "只输出一句话，不要标题、编号、Markdown、引号或免责声明。"
        )

    prompt = f"{instruction}\n\n内容：\n{text}"

    response = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers=DEEPSEEK_HEADERS,
        json={
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": "你是中文科技资讯编辑，表达简洁、客观、准确。",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0.2,
            "max_tokens": 100,
        },
        timeout=60,
    )

    response.raise_for_status()
    data = response.json()

    return (
        data["choices"][0]["message"]["content"]
        .strip()
        .replace("\n", " ")
    )


def get_github_projects(yesterday: str):
    response = requests.get(
        "https://api.github.com/search/repositories",
        headers=GITHUB_HEADERS,
        params={
            "q": f"created:{yesterday}",
            "sort": "stars",
            "order": "desc",
            "per_page": 5,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("items", [])


def get_ai_news():
    rss_sources = [
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "https://www.technologyreview.com/feed/",
    ]

    news = []
    seen_links = set()

    for source in rss_sources:
        try:
            feed = feedparser.parse(source)

            for item in feed.entries[:8]:
                title = item.get("title", "").strip()
                link = item.get("link", "").strip()
                summary = item.get("summary", "").strip()

                if not title or not link or link in seen_links:
                    continue

                seen_links.add(link)
                news.append(
                    {
                        "title": title,
                        "link": link,
                        "summary": summary,
                    }
                )

                if len(news) >= 10:
                    return news

        except Exception as error:
            print(f"RSS 获取失败：{source}，原因：{error}")

    return news[:10]


def build_report():
    now_utc = datetime.now(timezone.utc)
    now_cn = now_utc + timedelta(hours=8)

    today = now_cn.strftime("%Y-%m-%d")
    yesterday = (now_cn - timedelta(days=1)).strftime("%Y-%m-%d")

    repositories = get_github_projects(yesterday)
    news = get_ai_news()

    lines = [
        f"# AI 日报 · {today}",
        "",
        f"数据日期：{yesterday}",
        "",
        "## GitHub 昨日最热 5 个新项目",
        "",
    ]

    if repositories:
        for index, repo in enumerate(repositories, start=1):
            name = repo["full_name"]
            url = repo["html_url"]
            stars = repo["stargazers_count"]
            description = repo.get("description") or "暂无项目描述"

            project_text = (
                f"项目名称：{name}\n"
                f"项目描述：{description}\n"
                f"项目地址：{url}"
            )

            try:
                ai_summary = summarize_with_deepseek(
                    project_text,
                    "project",
                )
            except Exception as error:
                print(f"项目总结失败：{name}，原因：{error}")
                ai_summary = description

            lines.extend(
                [
                    f"{index}. [{name}]({url})",
                    f"   - Stars：{stars}",
                    f"   - AI 总结：{ai_summary}",
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
        for index, item in enumerate(news, start=1):
            news_text = (
                f"新闻标题：{item['title']}\n"
                f"新闻摘要：{item['summary']}\n"
                f"新闻链接：{item['link']}"
            )

            try:
                ai_summary = summarize_with_deepseek(
                    news_text,
                    "news",
                )
            except Exception as error:
                print(f"新闻总结失败：{item['title']}，原因：{error}")
                ai_summary = item["summary"] or item["title"]

            lines.extend(
                [
                    f"{index}. [{item['title']}]({item['link']})",
                    f"   - AI 总结：{ai_summary}",
                    "",
                ]
            )
    else:
        lines.append("暂时没有读取到 AI 新闻。")

    return today, "\n".join(lines)


def save_report(today: str, content: str):
    Path("reports").mkdir(exist_ok=True)
    path = Path("reports") / f"{today}.md"
    path.write_text(content, encoding="utf-8")
    return path


def send_to_wxpusher(today: str, content: str):
    response = requests.post(
        "https://wxpusher.zjiecode.com/api/send/message",
        json={
            "appToken": WXPUSHER_APP_TOKEN,
            "content": content[:10000],
            "summary": f"AI 日报 · {today}",
            "contentType": 3,
            "uids": [WXPUSHER_UID],
            "verifyPay": False,
        },
        timeout=30,
    )

    response.raise_for_status()
    result = response.json()

    if result.get("code") != 1000:
        raise RuntimeError(f"WxPusher 推送失败：{result}")

    return result


if __name__ == "__main__":
    report_date, report_content = build_report()
    report_path = save_report(report_date, report_content)
    push_result = send_to_wxpusher(report_date, report_content)

    print(f"日报已保存：{report_path}")
    print(f"WxPusher 推送成功：{push_result}")
