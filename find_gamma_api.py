import httpx
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
GAMMA_API_KEY = os.getenv("GAMMA_API_KEY")

# Test different BASE URLs
BASE_URLS = [
    "https://api.gamma.app",
    "https://gamma.app/api",
    "https://gamma.app",
    "https://app.gamma.app/api",
    "https://app.gamma.app",
    "https://api2.gamma.app",
    "https://backend.gamma.app",
    "https://gamma-api.vercel.app",
]

# Test different paths
PATHS = [
    "/public-api/v0.1/generate",
    "/public-api/v1/generate",
    "/api/generate",
    "/generate",
    "/v1/generate",
    "/ai/generate",
]

# Headers to try
HEADER_VARIANTS = [
    {"Content-Type": "application/json", "X-API-KEY": GAMMA_API_KEY or ""},
    {"Content-Type": "application/json", "Authorization": f"Bearer {GAMMA_API_KEY}"},
    {"Content-Type": "application/json", "api-key": GAMMA_API_KEY or ""},
    {"Content-Type": "application/json", "x-api-key": GAMMA_API_KEY or ""},
]

PAYLOAD = {
    "inputText": "Test",
    "numCards": 2,
    "textMode": "generate",
}


async def deep_scan():
    print("=" * 60)
    print("🔍 DEEP SCAN - Finding Real Gamma API")
    print("=" * 60)
    print(f"API Key: {GAMMA_API_KEY[:4] if GAMMA_API_KEY else 'NOT SET'}****")
    print()

    # ── Test 1: Check all base URLs ──────────────────
    print("📡 Step 1: Testing base URLs (GET)...")
    print("-" * 40)
    for base in BASE_URLS:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(base)
            status = r.status_code
            emoji = "✅" if status < 400 else "❌"
            print(f"{emoji} {status} → {base}")
        except httpx.ConnectError:
            print(f"💥 UNREACHABLE → {base}")
        except Exception as e:
            print(f"⚠️  ERROR → {base}: {str(e)[:50]}")
        await asyncio.sleep(0.3)

    # ── Test 2: Check all base + path combinations ───
    print(f"\n📡 Step 2: Testing base + path POST combinations...")
    print("-" * 40)
    for base in BASE_URLS[:3]:  # Top 3 most likely
        for path in PATHS:
            url = base + path
            try:
                async with httpx.AsyncClient(timeout=8) as client:
                    r = await client.post(
                        url,
                        headers={
                            "Content-Type": "application/json",
                            "X-API-KEY": GAMMA_API_KEY or "",
                        },
                        json=PAYLOAD,
                    )
                status = r.status_code
                if status != 404:
                    print(f"🎯 FOUND! {status} → {url}")
                    print(f"   Body: {r.text[:300]}")
                else:
                    print(f"❌ 404 → {url}")
            except Exception as e:
                print(f"⚠️  {url}: {str(e)[:40]}")
            await asyncio.sleep(0.2)

    # ── Test 3: Try different auth headers ──────────
    print(f"\n📡 Step 3: Testing different auth headers...")
    print("-" * 40)
    test_url = "https://api.gamma.app/public-api/v0.1/generate"
    for i, headers in enumerate(HEADER_VARIANTS):
        header_name = list(headers.keys())[1]  # Get auth header name
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.post(test_url, headers=headers, json=PAYLOAD)
            print(f"  Header '{header_name}': {r.status_code} → {r.text[:100]}")
        except Exception as e:
            print(f"  Header '{header_name}': ERROR - {str(e)[:50]}")
        await asyncio.sleep(0.3)

    # ── Test 4: Check Gamma docs/swagger ────────────
    print(f"\n📡 Step 4: Looking for API docs...")
    print("-" * 40)
    doc_urls = [
        "https://api.gamma.app/docs",
        "https://api.gamma.app/swagger",
        "https://api.gamma.app/openapi.json",
        "https://api.gamma.app/public-api",
        "https://gamma.app/api-docs",
        "https://gamma.app/developers",
    ]
    for url in doc_urls:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(url)
            if r.status_code != 404:
                print(f"📖 FOUND DOCS! {r.status_code} → {url}")
                print(f"   Preview: {r.text[:200]}")
            else:
                print(f"❌ {r.status_code} → {url}")
        except Exception as e:
            print(f"⚠️  {url}: {str(e)[:40]}")
        await asyncio.sleep(0.3)

    print("\n" + "=" * 60)
    print("🏁 Scan Complete!")
    print("=" * 60)
    print("\n💡 Next Steps:")
    print("1. Share results above")
    print("2. Go to gamma.app → Settings → API")
    print("3. Copy the EXACT endpoint shown there")
    print("4. Check if your API plan includes API access")


if __name__ == "__main__":
    asyncio.run(deep_scan())
