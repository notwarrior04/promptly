from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from gemini_handler import call_gemini
import httpx
from bs4 import BeautifulSoup
from langdetect import detect
import validators
import asyncio

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cache for website content
cache = {}
cache_lock = asyncio.Lock()

# Async queue to rate-limit Gemini calls
gemini_queue = asyncio.Queue(maxsize=3)


async def fetch_website_text(url: str) -> str:
    if not validators.url(url):
        return "[ERROR] Invalid URL provided."

    async with cache_lock:
        if url in cache:
            return cache[url]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            # Remove non-content elements
            for tag in soup(["script", "style", "header", "footer", "nav"]):
                tag.decompose()

            text = soup.get_text(separator=" ", strip=True)
            content = text[:12000]  # Limit for safety

            async with cache_lock:
                cache[url] = content

            return content
    except Exception as e:
        return f"[ERROR] Could not fetch content: {e}"


@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    user_prompt = data.get("prompt", "").strip()
    context_raw = data.get("context", "")

    try:
        url = context_raw.split("Website: ")[1].split("\n")[0].strip()
    except Exception:
        return {
            "response": "Invalid context format. Expected:\nWebsite: <url>\\nLanguage: <optional language>"
        }

    website_text = await fetch_website_text(url)

    if website_text.startswith("[ERROR]"):
        return {"response": website_text}

    try:
        detected_lang = detect(website_text)
    except Exception:
        detected_lang = "unknown"

    final_prompt = (
        f"{user_prompt}\n\n"
        f"DONT USE asterisks for bold, italics. Use clean plain text only. USE BULLETS ONLY FOR KEYPOINTS.\n\n"
        f"---\n"
        f"Website Content (detected language: {detected_lang}):\n{website_text}"
    )
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from gemini_handler import call_gemini
import httpx
from bs4 import BeautifulSoup
from langdetect import detect
import validators
import asyncio

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cache for website content
cache = {}
cache_lock = asyncio.Lock()

# Rate-limit Gemini calls
gemini_queue = asyncio.Queue(maxsize=3)


async def fetch_website_text(url: str) -> str:
    if not validators.url(url):
        return "[ERROR] Invalid URL provided."

    async with cache_lock:
        if url in cache:
            return cache[url]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "header", "footer", "nav"]):
                tag.decompose()

            text = soup.get_text(separator=" ", strip=True)
            content = text[:12000]  # Prompt-safe limit

            async with cache_lock:
                cache[url] = content

            return content
    except Exception as e:
        return f"[ERROR] Could not fetch content: {e}"


@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    user_prompt = data.get("prompt", "").strip()
    context_raw = data.get("context", "")

    try:
        url = context_raw.split("Website: ")[1].split("\n")[0].strip()
        lang_pref = context_raw.split("Language: ")[1].strip()
    except Exception:
        return {
            "response": "Invalid context format. Expected:\nWebsite: <url>\\nLanguage: <optional language>"
        }

    website_text = await fetch_website_text(url)
    if website_text.startswith("[ERROR]"):
        return {"response": website_text}

    try:
        detected_lang = detect(website_text)
    except Exception:
        detected_lang = "unknown"

    # Build prompt with exact user message
    final_prompt = f"{user_prompt}\n\n"
    final_prompt += "DONT USE asterisks for bold, italics. Use clean plain text only. USE BULLETS ONLY FOR KEYPOINTS.\n\n"

    # Auto-translate if language specified and not 'None'
    if lang_pref.lower() != "none" and lang_pref.strip():
        final_prompt += (
            f"\nAdditionally, translate the final response into {lang_pref.strip()}.\n"
        )

    final_prompt += f"\n---\nWebsite Content (detected language: {detected_lang}):\n{website_text}"

    # Rate-limited Gemini call
    await gemini_queue.put(1)
    try:
        response = await call_gemini(final_prompt)
    finally:
        gemini_queue.get_nowait()
        gemini_queue.task_done()

    return {"response": response}

    # Rate-limited Gemini call
    await gemini_queue.put(1)
    try:
        response = await call_gemini(final_prompt)
    finally:
        gemini_queue.get_nowait()
        gemini_queue.task_done()

    return {"response": response}
