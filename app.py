from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from gemini_handler import call_gemini
import httpx
from bs4 import BeautifulSoup
from langdetect import detect
import validators
import asyncio

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update for production if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cache for fetched website content
cache = {}
cache_lock = asyncio.Lock()

# Queue to rate-limit Gemini calls
gemini_queue = asyncio.Queue(maxsize=3)

# --------- Fetch Website Content ---------
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
            content = text[:12000]  # Trim to safe token size

            async with cache_lock:
                cache[url] = content

            return content
    except Exception as e:
        return f"[ERROR] Could not fetch content: {e}"

# --------- Chat Endpoint ---------
@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    user_prompt = data.get("prompt", "").strip()
    context_raw = data.get("context", "").strip()

    # Expecting context format:
    # Website: <url>
    # Language: <optional language>
    if not context_raw.startswith("Website: ") or "Language: " not in context_raw:
        return {
            "response": "Invalid context format. Expected:\nWebsite: <url>\\nLanguage: <optional language>"
        }

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

    # Final Prompt Construction
    final_prompt = f"{user_prompt}\n\n"
    final_prompt += "DONT USE SPECIAL-CASE CHARACTERS LIKE ASTERISKS AND UNDERSCORES FOR TEXT-STYLING! USE PLAIN CLEAN TEXT ONLY! USE NUMBERS (1.,2.,3.,...) AND ROMAN NUMBERS (IF NEEDED) FOR KEYPOINTS AND NUMBERING!\n\n"

    if lang_pref.lower() != "none" and lang_pref.strip():
        final_prompt += f"\nAdditionally, translate the final response into {lang_pref.strip()}.\n"

    final_prompt += f"\n---\nWebsite Content (detected language: {detected_lang}):\n{website_text}"

    # Rate-limited Gemini call
    await gemini_queue.put(1)
    try:
        response = await call_gemini(final_prompt)
    finally:
        gemini_queue.get_nowait()
        gemini_queue.task_done()

    return {"response": response}
