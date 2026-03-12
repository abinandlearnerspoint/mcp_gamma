import httpx
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

GAMMA_API_KEY = os.getenv("GAMMA_API_KEY")

# ✅ All possible Gamma API endpoints to test
ENDPOINTS = [
    "https://api.gamma.app/public-api/v0.1/generate",
    "https://api.gamma.app/public-api/v1/generate",
    "https://api.gamma.app/api/v0.1/generate",
    "https://api.gamma.app/api/v1/generate",
    "https://api.gamma.app/v1/generate",
    "https://api.gamma.app/v0.1/generate",
    "https://api.gamma.app/generate",
    "https://api.gamma.app/public-api/v0.1/ai/generate",
    "https://api.gamma.app/public-api/v2/generate",
    "https://public-api.gamma.app/v1.0/generations"
]

async def test_endpoint(url: str):
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": GAMMA_API_KEY or "",
    }
    payload = {
        "inputText": "Test presentation",
        "numCards": 2,
        "textMode": "generate",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, headers=headers, json=payload)
        
        if response.status_code == 404:
            print(f"❌ 404 NOT FOUND  → {url}")
        elif response.status_code == 401:
            print(f"🔑 401 UNAUTHORIZED (endpoint EXISTS but key issue) → {url}")
        elif response.status_code == 403:
            print(f"🔒 403 FORBIDDEN (endpoint EXISTS but no access) → {url}")
        elif response.status_code == 422:
            print(f"⚠️  422 VALIDATION ERROR (endpoint EXISTS!) → {url}")
        elif response.status_code == 200:
            print(f"✅ 200 SUCCESS!! → {url}")
            print(f"   Response: {response.text[:200]}")
        else:
            print(f"🟡 {response.status_code} → {url}")
            print(f"   Body: {response.text[:200]}")

    except Exception as e:
        print(f"💥 ERROR → {url} | {str(e)}")


async def test_gamma_key():
    """Also test if API key is valid by calling a GET endpoint"""
    print("\n🔑 Testing API Key validity...")
    
    key_test_urls = [
        "https://api.gamma.app/public-api/v0.1/me",
        "https://api.gamma.app/public-api/v1/me", 
        "https://api.gamma.app/api/v1/me",
        "https://api.gamma.app/public-api/v0.1/user",
        "https://public-api.gamma.app/v1.0/generations"
    ]
    
    for url in key_test_urls:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    url,
                    headers={"X-API-KEY": GAMMA_API_KEY or ""}
                )
            print(f"  {r.status_code} → {url}")
            if r.status_code != 404:
                print(f"  Body: {r.text[:300]}")
        except Exception as e:
            print(f"  ERROR → {url}: {e}")


async def main():
    print("=" * 60)
    print("🔍 Gamma API Endpoint Tester")
    print("=" * 60)
    print(f"API Key: {GAMMA_API_KEY[:4]}****{GAMMA_API_KEY[-4:] if GAMMA_API_KEY else 'NOT SET'}")
    print("=" * 60)
    
    print("\n📡 Testing all generate endpoints...\n")
    
    for endpoint in ENDPOINTS:
        await test_endpoint(endpoint)
        await asyncio.sleep(0.5)  # Small delay between requests
    
    await test_gamma_key()
    
    print("\n" + "=" * 60)
    print("✅ Test complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
