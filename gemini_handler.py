import httpx
from gemini_config import GEMINI_API_KEY

async def call_gemini(prompt, context=""):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY
    }

    data = {
        "contents": [
            {"parts": [{"text": f"{prompt}\n\nContext:\n{context}"}]}
        ]
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=data)

        print("Status Code:", response.status_code)
        print("Response Body:", response.text)

        result = response.json()
        try:
            return result['candidates'][0]['content']['parts'][0]['text']
        except KeyError:
            return f"Error: {result.get('error', {}).get('message', 'Unknown issue')}"
