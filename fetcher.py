import random
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
import httpx
from bs4 import BeautifulSoup

FEEDS = [
    {
        "category": "Psychology & Philosophy",
        "source_name": "Psyche Magazine",
        "url": "https://psyche.co/feed.rss",
        "type": "rss",
    },
    {
        "category": "Mental Models & Wisdom",
        "source_name": "Farnam Street",
        "url": "https://fs.blog/feed/",
        "type": "rss",
    },
    {
        "category": "Everyday Life & Productivity",
        "source_name": "Lifehacker",
        "url": "https://lifehacker.com/feed/rss",
        "type": "rss",
    },
    {
        "category": "Current Perspectives",
        "source_name": "The Guardian Opinion",
        "url": "https://www.theguardian.com/uk/commentisfree/rss",
        "type": "rss",
    },
    {
        "category": "Tech & Deep Dives",
        "source_name": "Ars Technica",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "type": "rss",
    },
    {
        "category": "Mental Models & Wisdom",
        "source_name": "Derek Sivers",
        "url": "https://sive.rs/en.atom",
        "type": "atom",
    },
    {
        "category": "Psychology & Philosophy",
        "source_name": "Aeon Essays",
        "url": "https://aeon.co/feed.rss",
        "type": "rss",
    },
    {
        "category": "Current Perspectives",
        "source_name": "NPR News",
        "url": "https://feeds.npr.org/1001/rss.xml",
        "type": "rss",
    },
    {
        "category": "Tech & Deep Dives",
        "source_name": "Astral Codex Ten",
        "url": "https://www.astralcodexten.com/feed",
        "type": "rss",
    },
]

FALLBACK_ARTICLES = [
    {
        "category": "Mental Models & Wisdom",
        "source_name": "Farnam Street (Offline Archive)",
        "title": "The Trap of Premature Optimization in Daily Habits",
        "url": "offline://fs-premature-optimization",
        "content": (
            "When people decide to pick up a new skill, they often spend weeks researching the optimal gear, "
            "the best routine, and the most efficient methodology before putting in a single hour of messy practice. "
            "In software engineering, premature optimization is famously known as the root of all evil, yet we fall "
            "into the exact same trap in everyday life. We confuse preparation with progress because preparation "
            "feels safe—you cannot fail while you are still comparison-shopping or tweaking your schedule. "
            "True competence, however, comes from tolerating the friction of being a clumsy beginner, getting "
            "real-world feedback early, and adjusting course only after you have skin in the game."
        ),
    },
    {
        "category": "Psychology & Philosophy",
        "source_name": "Psyche (Offline Archive)",
        "title": "Why Saying Less Often Communicates More",
        "url": "offline://psyche-saying-less",
        "content": (
            "In high-stakes conversations, silence makes most of us deeply uncomfortable. The moment a pause lingers "
            "for more than two seconds, we rush to fill the void with qualifiers, tangents, or repetitive explanations "
            "that dilute our original point. Yet studies of persuasive speakers show that restraint is one of the "
            "clearest signals of confidence. When you state an idea clearly and stop talking, you give the listener "
            "room to process the weight of your words instead of burying your best argument under an avalanche of "
            "afterthoughts."
        ),
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) speak-daily-cli/1.0"
}


def _clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "figure", "figcaption", "nav", "footer", "aside"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fetch_full_page_text(url: str, client: httpx.Client) -> str:
    try:
        resp = client.get(url, timeout=6.0, follow_redirects=True)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()
        container = soup.find("article") or soup.find("main") or soup.body
        if not container:
            return ""
        paragraphs = []
        for p in container.find_all("p"):
            txt = re.sub(r"\s+", " ", p.get_text()).strip()
            if len(txt.split()) >= 12:
                paragraphs.append(txt)
            if sum(len(x.split()) for x in paragraphs) >= 400:
                break
        return " ".join(paragraphs)
    except Exception:
        return ""


def _parse_feed(xml_text: str, feed_info: Dict[str, str], client: httpx.Client, used_urls: List[str]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return candidates

    ns = {
        "content": "http://purl.org/rss/1.0/modules/content/",
        "atom": "http://www.w3.org/2005/Atom",
    }

    if feed_info["type"] == "atom":
        entries = root.findall("atom:entry", ns) or root.findall("entry")
        for entry in entries[:15]:
            title_el = entry.find("atom:title", ns) or entry.find("title")
            link_el = entry.find("atom:link", ns) or entry.find("link")
            content_el = (
                entry.find("atom:content", ns)
                or entry.find("content")
                or entry.find("atom:summary", ns)
                or entry.find("summary")
            )
            title = (title_el.text or "").strip() if title_el is not None else ""
            link = ""
            if link_el is not None:
                link = link_el.attrib.get("href", "") or (link_el.text or "").strip()
            if not title or not link or link in used_urls:
                continue
            raw_body = (content_el.text or "") if content_el is not None else ""
            cleaned = _clean_html(raw_body)
            if len(cleaned.split()) < 90:
                page_txt = _fetch_full_page_text(link, client)
                if len(page_txt.split()) > len(cleaned.split()):
                    cleaned = page_txt
            if len(cleaned.split()) >= 60:
                candidates.append(
                    {
                        "category": feed_info["category"],
                        "source_name": feed_info["source_name"],
                        "title": title,
                        "url": link,
                        "content": " ".join(cleaned.split()[:500]),
                    }
                )
    else:
        items = root.findall(".//item")
        for item in items[:12]:
            title_el = item.find("title")
            link_el = item.find("link")
            encoded_el = item.find("content:encoded", ns)
            desc_el = item.find("description")

            title = (title_el.text or "").strip() if title_el is not None else ""
            link = (link_el.text or "").strip() if link_el is not None else ""
            if not title or not link or link in used_urls:
                continue

            raw_body = ""
            if encoded_el is not None and encoded_el.text:
                raw_body = encoded_el.text
            elif desc_el is not None and desc_el.text:
                raw_body = desc_el.text

            cleaned = _clean_html(raw_body)
            if len(cleaned.split()) < 90 and len(candidates) < 3:
                page_txt = _fetch_full_page_text(link, client)
                if len(page_txt.split()) > len(cleaned.split()):
                    cleaned = page_txt

            if len(cleaned.split()) >= 55:
                candidates.append(
                    {
                        "category": feed_info["category"],
                        "source_name": feed_info["source_name"],
                        "title": title,
                        "url": link,
                        "content": " ".join(cleaned.split()[:500]),
                    }
                )

    return candidates


def fetch_fresh_article(used_urls: List[str], preferred_category: Optional[str] = None) -> Dict[str, Any]:
    feeds_pool = list(FEEDS)
    random.shuffle(feeds_pool)
    if preferred_category:
        feeds_pool.sort(key=lambda f: 0 if preferred_category.lower() in f["category"].lower() else 1)

    with httpx.Client(headers=HEADERS) as client:
        for feed in feeds_pool:
            try:
                resp = client.get(feed["url"], timeout=7.0, follow_redirects=True)
                if resp.status_code != 200:
                    continue
                items = _parse_feed(resp.text, feed, client, used_urls)
                if items:
                    return random.choice(items[:5])
            except Exception:
                continue

    # Offline fallback
    for fb in FALLBACK_ARTICLES:
        if fb["url"] not in used_urls:
            return fb
    return random.choice(FALLBACK_ARTICLES)
