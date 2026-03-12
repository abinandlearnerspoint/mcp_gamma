#!/usr/bin/env python3
"""
Gamma Presentation MCP Server - Fully Fixed
"""

import os
import sys
from typing import Optional, Any, Dict, Literal
import asyncio
import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

# ── Config ──────────────────────────────────────────────
GAMMA_API_URL = "https://public-api.gamma.app/v1.0/generations"
GAMMA_API_KEY = os.getenv("GAMMA_API_KEY")

# ── FastMCP Instance ─────────────────────────────────────
mcp = FastMCP("gamma-presentation")


# ── Helper: Call Gamma API ───────────────────────────────
async def call_gamma_api(
    params: Dict[str, Any]
) -> Dict[str, Optional[str]]:

    print(f"\n{'='*55}", flush=True)
    print(f"📤 Calling Gamma API", flush=True)
    print(f"🔗 URL     : {GAMMA_API_URL}", flush=True)
    print(f"📦 Payload : {params}", flush=True)
    print(f"{'='*55}", flush=True)

    try:
        # ── Step 1: Create Generation ─────────────────────
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                GAMMA_API_URL,
                headers={
                    "Content-Type": "application/json",
                    "X-API-KEY": GAMMA_API_KEY or "",
                },
                json=params,
            )

        print(f"📥 Status  : {response.status_code}", flush=True)
        print(f"📥 Body    : {response.text[:500]}", flush=True)

        if not response.is_success:
            raise Exception(
                f"HTTP error! status: {response.status_code}, "
                f"body: {response.text}"
            )

        data = response.json()
        print(f"📥 Full Response : {data}", flush=True)

        # ── Try to get generationId ───────────────────────
        generation_id = data.get("generationId") or data.get("id")

        if not generation_id:
            # Maybe URL is directly returned
            direct_url = data.get("url") or data.get("link")
            if direct_url:
                print(f"✅ Direct URL : {direct_url}", flush=True)
                return {"url": direct_url, "error": None}
            raise Exception(
                f"Gamma did not return generationId. "
                f"Full response: {data}"
            )

        print(f"🆔 Generation ID : {generation_id}", flush=True)

        # ── Step 2: Poll Gamma for result ─────────────────
        status_url = (
            f"https://public-api.gamma.app/v1.0/generations/{generation_id}"
        )

        print(f"⏳ Polling status at: {status_url}", flush=True)

        async with httpx.AsyncClient(timeout=60) as client:
            for attempt in range(20):  # Try up to 20 times (40 seconds)
                await asyncio.sleep(3)  # Wait 3 seconds between polls

                r = await client.get(
                    status_url,
                    headers={
                        "Content-Type": "application/json",
                        "X-API-KEY": GAMMA_API_KEY or "",
                    },
                )

                print(f"🔄 Poll #{attempt+1} Status: {r.status_code}", flush=True)
                print(f"🔄 Poll #{attempt+1} Body  : {r.text[:300]}", flush=True)

                if not r.is_success:
                    print(f"⚠️ Poll failed with status {r.status_code}", flush=True)
                    continue

                status_data = r.json()
                status = status_data.get("status")

                print(f"📊 Generation Status : {status}", flush=True)

                if status in ["completed", "done", "success"]:
                    # ✅ Try multiple possible URL locations
                    url = (
                        status_data.get("url")
                        or status_data.get("link")
                        or status_data.get("gammaUrl")
                        or (status_data.get("gamma") or {}).get("url")
                        or (status_data.get("result") or {}).get("url")
                        or (status_data.get("data") or {}).get("url")
                    )

                    if url:
                        print(f"✅ Final URL : {url}", flush=True)
                        return {"url": url, "error": None}
                    else:
                        print(f"⚠️ Status completed but no URL found!", flush=True)
                        print(f"⚠️ Full data: {status_data}", flush=True)
                        raise Exception(
                            f"Generation completed but no URL found. "
                            f"Response: {status_data}"
                        )

                elif status in ["failed", "error"]:
                    raise Exception(
                        f"Generation failed with status: {status}. "
                        f"Response: {status_data}"
                    )

                # Still processing - continue polling
                print(f"⏳ Still processing... waiting 3s", flush=True)

        raise Exception(
            "Generation timed out after 60 seconds. "
            "Please try again."
        )

    except Exception as e:
        print(f"❌ Error : {str(e)}", flush=True)
        return {"url": None, "error": str(e)}


# ── MCP Tool: Generate Presentation ─────────────────────
@mcp.tool()
async def generate_presentation(
    inputText: str,
    numCards: Optional[int] = 5,
    textMode: Optional[Literal["generate", "summarize"]] = "generate",
    additionalInstructions: Optional[str] = None,
) -> str:
    """
    Generate a presentation using the Gamma API.
    Always show the link to the user when available.

    Args:
        inputText    : Topic or prompt for the presentation (REQUIRED)
        numCards     : Number of slides between 1-20 (default: 5)
        textMode     : 'generate' or 'summarize' (default: generate)
        additionalInstructions: Extra instructions (optional)
    """
    print(f"\n🚀 generate_presentation() called!", flush=True)
    print(f"   inputText : {inputText}", flush=True)
    print(f"   numCards  : {numCards}", flush=True)

    if numCards is not None and (numCards < 1 or numCards > 20):
        return "❌ numCards must be between 1 and 20."

    # ✅ Only send params Gamma API accepts
    params: Dict[str, Any] = {"inputText": inputText}

    if textMode is not None:
        params["textMode"] = textMode

    if numCards is not None:
        params["numCards"] = numCards

    if additionalInstructions is not None:
        params["additionalInstructions"] = additionalInstructions

    print(f"📦 Final Params: {params}", flush=True)

    result = await call_gamma_api(params)
    url = result["url"]
    error = result["error"]

    if not url:
        return (
            f"❌ Failed to generate presentation. "
            f"Error: {error or 'Unknown error.'}"
        )

    return (
        f"✅ Presentation generated successfully!\n"
        f"🔗 View it here: {url}"
    )


# ── MCP Tool: Test Connection ────────────────────────────
@mcp.tool()
async def test_connection() -> str:
    """
    Test the MCP server and Gamma API connection.
    """
    print("\n🔍 test_connection() called!", flush=True)
    lines = []

    if GAMMA_API_KEY:
        masked = f"{GAMMA_API_KEY[:4]}****{GAMMA_API_KEY[-4:]}"
        lines.append(f"✅ GAMMA_API_KEY : {masked}")
    else:
        lines.append("❌ GAMMA_API_KEY : NOT SET!")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://public-api.gamma.app")
        lines.append(f"✅ Gamma API : Reachable ({r.status_code})")
    except Exception as e:
        lines.append(f"❌ Gamma API : {e}")

    lines.append(f"✅ MCP Server : Running")
    lines.append(f"🔗 Endpoint  : {GAMMA_API_URL}")

    output = "\n".join(lines)
    print(output, flush=True)
    return output


# ── Main ─────────────────────────────────────────────────
def main():
    print("=" * 55, flush=True)
    print("🤖  Gamma Presentation MCP Server", flush=True)
    print("=" * 55, flush=True)

    if GAMMA_API_KEY:
        masked = f"{GAMMA_API_KEY[:4]}****{GAMMA_API_KEY[-4:]}"
        print(f"✅ API Key : {masked}", flush=True)
    else:
        print("❌ API Key : MISSING — Add to .env!", flush=True)
        sys.exit(1)

    port = int(os.environ.get("PORT", 8000))

    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
    )
    # mcp.run(
    #     transport="streamable-http",
    #     host="0.0.0.0",
    #     port=8000,
    # )


if __name__ == "__main__":
    main()
