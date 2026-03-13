#!/usr/bin/env python3
"""
Gamma Presentation MCP Server - Production Ready
Supports: generate, from-template, themes, folders, polling
"""

import os
import sys
from typing import Optional, Any, Dict, List, Literal
import asyncio
import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
GAMMA_API_BASE    = "https://public-api.gamma.app/v1.0"
GAMMA_GENERATIONS = f"{GAMMA_API_BASE}/generations"
GAMMA_API_KEY     = os.getenv("GAMMA_API_KEY")

# ✅ FIX: Increased polling — Gamma takes 2-5 minutes
POLL_INTERVAL_SEC = 8     # 8 seconds between polls
POLL_MAX_ATTEMPTS = 45    # 45 × 8s = 6 minutes max
POLL_MAX_RETRIES  = 3     # consecutive HTTP errors before giving up

# ── FastMCP ───────────────────────────────────────────────────────────────────
mcp = FastMCP("gamma-presentation")


# ══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-API-KEY": GAMMA_API_KEY or "",
    }


def _check_api_key() -> Optional[str]:
    if not GAMMA_API_KEY:
        return "❌ GAMMA_API_KEY is not set. Add it to your .env file."
    return None


def _extract_url(data: Dict, generation_id: str) -> str:
    """Try all known URL fields, fallback to building from ID."""
    url = (
        data.get("url")
        or data.get("link")
        or data.get("gammaUrl")
        or (data.get("gamma") or {}).get("url")
        or (data.get("result") or {}).get("url")
        or (data.get("data") or {}).get("url")
        or (data.get("output") or {}).get("url")
    )
    if not url:
        url = f"https://gamma.app/docs/{generation_id}"
        print(f"⚠️  No URL in response — fallback: {url}", flush=True)
    return url


# ── Core: POST to Gamma and get generation_id ─────────────────────────────────
async def _start_generation(
    endpoint: str,
    params: Dict[str, Any],
    label: str = "generation",
) -> tuple[Optional[str], Optional[str]]:
    """
    POST to Gamma endpoint.
    Returns (generation_id, None) on success
    Returns (None, error_message) on failure
    Returns ("DIRECT:url", None) if URL returned immediately
    """
    print(f"\n{'='*60}", flush=True)
    print(f"📤 Starting {label}", flush=True)
    print(f"🔗 Endpoint : {endpoint}", flush=True)
    print(f"📦 Payload  : {params}", flush=True)
    print(f"{'='*60}", flush=True)

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                endpoint,
                headers=_headers(),
                json=params,
            )

        print(f"📥 HTTP {resp.status_code}", flush=True)
        print(f"📥 Body : {resp.text[:800]}", flush=True)

        if not resp.is_success:
            # Try to parse error message from Gamma
            try:
                err_data = resp.json()
                err_msg  = (
                    err_data.get("message")
                    or err_data.get("error")
                    or resp.text
                )
            except Exception:
                err_msg = resp.text
            return None, f"HTTP {resp.status_code}: {err_msg}"

        data = resp.json()
        print(f"📥 Full Response: {data}", flush=True)

        # Direct URL (no polling needed)
        generation_id = data.get("generationId") or data.get("id")
        if not generation_id:
            direct = data.get("url") or data.get("link")
            if direct:
                return f"DIRECT:{direct}", None
            return None, f"No generationId in response: {data}"

        print(f"🆔 Generation ID: {generation_id}", flush=True)
        return generation_id, None

    except httpx.TimeoutException:
        return None, "Request timed out. Check your network."
    except httpx.ConnectError:
        return None, "Cannot connect to Gamma API. Check your network."
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


# ── Core: Poll until done ─────────────────────────────────────────────────────
async def _poll_generation(generation_id: str) -> Dict[str, Optional[str]]:
    """
    Poll until status = completed/failed or timeout.
    Returns dict with url, pdfUrl, pptxUrl, error keys.
    """
    status_url = f"{GAMMA_GENERATIONS}/{generation_id}"
    total_wait  = POLL_MAX_ATTEMPTS * POLL_INTERVAL_SEC

    print(f"\n⏳ Polling: {status_url}", flush=True)
    print(f"⏳ Will wait up to {total_wait}s "
          f"({POLL_MAX_ATTEMPTS} × {POLL_INTERVAL_SEC}s)", flush=True)

    consecutive_errors = 0

    for attempt in range(1, POLL_MAX_ATTEMPTS + 1):
        await asyncio.sleep(POLL_INTERVAL_SEC)

        try:
            # ✅ Fresh client per poll — avoids stale connection on long waits
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(status_url, headers=_headers())

            elapsed = attempt * POLL_INTERVAL_SEC
            print(
                f"🔄 Poll {attempt:02d}/{POLL_MAX_ATTEMPTS} "
                f"| {elapsed}s elapsed "
                f"| HTTP {r.status_code} "
                f"| {r.text[:300]}",
                flush=True,
            )

            # HTTP error handling
            if not r.is_success:
                consecutive_errors += 1
                print(
                    f"⚠️  HTTP {r.status_code} error "
                    f"({consecutive_errors}/{POLL_MAX_RETRIES} consecutive)",
                    flush=True,
                )
                if consecutive_errors >= POLL_MAX_RETRIES:
                    return {
                        "url": None, "pdfUrl": None, "pptxUrl": None,
                        "error": (
                            f"Too many poll failures. "
                            f"Last HTTP {r.status_code}: {r.text[:200]}"
                        ),
                    }
                continue

            consecutive_errors = 0  # reset on success
            data   = r.json()
            status = data.get("status", "").lower().strip()
            print(f"📊 Status: '{status}' (attempt {attempt})", flush=True)

            # ── ✅ Done ───────────────────────────────────────────────────────
            if status in ("completed", "complete", "done", "success"):
                url      = _extract_url(data, generation_id)
                pdf_url  = (
                    data.get("pdfUrl")
                    or (data.get("exports") or {}).get("pdf")
                )
                pptx_url = (
                    data.get("pptxUrl")
                    or (data.get("exports") or {}).get("pptx")
                )
                print(f"✅ Done! URL: {url}", flush=True)
                return {
                    "url": url, "pdfUrl": pdf_url,
                    "pptxUrl": pptx_url, "error": None,
                }

            # ── ❌ Failed ─────────────────────────────────────────────────────
            elif status in ("failed", "error", "cancelled", "canceled"):
                msg = (
                    data.get("message")
                    or data.get("error")
                    or data.get("reason")
                    or status
                )
                print(f"❌ Failed: {msg}", flush=True)
                return {
                    "url": None, "pdfUrl": None, "pptxUrl": None,
                    "error": f"Generation failed ('{status}'): {msg}",
                }

            # ── ⏳ Still running ──────────────────────────────────────────────
            else:
                remaining = total_wait - elapsed
                print(
                    f"⏳ Still {status or 'pending'}... "
                    f"~{remaining}s remaining",
                    flush=True,
                )

        except httpx.TimeoutException:
            consecutive_errors += 1
            print(f"⚠️  Poll timeout (attempt {attempt})", flush=True)
            if consecutive_errors >= POLL_MAX_RETRIES:
                return {
                    "url": None, "pdfUrl": None, "pptxUrl": None,
                    "error": "Polling timed out repeatedly.",
                }

        except Exception as e:
            consecutive_errors += 1
            print(f"⚠️  Poll error: {e}", flush=True)
            if consecutive_errors >= POLL_MAX_RETRIES:
                return {
                    "url": None, "pdfUrl": None, "pptxUrl": None,
                    "error": f"Repeated poll errors: {e}",
                }

    # ── Timeout ───────────────────────────────────────────────────────────────
    return {
        "url": None, "pdfUrl": None, "pptxUrl": None,
        "error": (
            f"Timed out after {total_wait}s. "
            f"Generation may still complete — "
            f"check https://gamma.app dashboard."
        ),
    }


def _format_result(result: Dict[str, Optional[str]], label: str) -> str:
    """Format the final response shown to the user."""
    url      = result.get("url")
    pdf_url  = result.get("pdfUrl")
    pptx_url = result.get("pptxUrl")
    error    = result.get("error")

    if not url:
        return (
            f"❌ {label} failed.\n"
            f"Error: {error or 'Unknown error'}\n\n"
            f"💡 Check https://gamma.app — "
            f"it may have completed after timeout."
        )

    lines = [
        f"✅ {label} generated successfully!",
        f"",
        f"🔗 View here    : {url}",
    ]
    if pdf_url:
        lines.append(f"📄 PDF export   : {pdf_url}")
    if pptx_url:
        lines.append(f"📊 PPTX export  : {pptx_url}")
    lines += ["", f"💡 Also visit   : https://gamma.app"]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 1 — Generate Presentation (new, from scratch)
# ══════════════════════════════════════════════════════════════════════════════
@mcp.tool()
async def generate_presentation(
    inputText: str,
    numCards: Optional[int] = 5,
    textMode: Optional[Literal["generate", "summarize"]] = "generate",
    themeId: Optional[str] = None,
    additionalInstructions: Optional[str] = None,
) -> str:
    """
    Generate a brand-new Gamma presentation from a topic or prompt.

    Args:
        inputText              : Topic or content for the presentation (REQUIRED)
        numCards               : Number of slides 1–20 (default: 5)
        textMode               : 'generate' to create new content,
                                 'summarize' to condense input text
                                 (default: 'generate')
        themeId                : Gamma theme ID e.g. 'i3vnnr2ewxym0se'
                                 Use list_themes() to find available IDs
        additionalInstructions : Extra instructions e.g. 'Use formal tone'

    Returns:
        Link to the generated presentation.

    Example:
        generate_presentation(
            inputText="AI in Healthcare",
            numCards=8,
            themeId="i3vnnr2ewxym0se"
        )
    """
    print(f"\n🚀 generate_presentation()", flush=True)
    print(f"   inputText  : {inputText[:80]}", flush=True)
    print(f"   numCards   : {numCards}", flush=True)
    print(f"   themeId    : {themeId}", flush=True)

    # Validate
    err = _check_api_key()
    if err: return err

    if not inputText or not inputText.strip():
        return "❌ inputText cannot be empty."
    if numCards is not None and not (1 <= numCards <= 20):
        return "❌ numCards must be between 1 and 20."

    # Build payload
    params: Dict[str, Any] = {"inputText": inputText.strip()}
    if textMode               is not None: params["textMode"]               = textMode
    if numCards               is not None: params["numCards"]               = numCards
    if themeId                is not None: params["themeId"]                = themeId
    if additionalInstructions is not None: params["additionalInstructions"] = additionalInstructions.strip()

    print(f"📦 Payload: {params}", flush=True)

    # Start generation
    generation_id, error = await _start_generation(
        GAMMA_GENERATIONS, params, "new presentation"
    )
    if error:
        return f"❌ Failed to start generation.\nError: {error}"
    if generation_id.startswith("DIRECT:"):
        return f"✅ Presentation ready!\n🔗 {generation_id[7:]}"

    # Poll for result
    result = await _poll_generation(generation_id)
    return _format_result(result, "Presentation")


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 2 — Generate from Template
# ══════════════════════════════════════════════════════════════════════════════
@mcp.tool()
async def generate_from_template(
    gammaId: str,
    prompt: str,
    themeId: Optional[str] = None,
    folderIds: Optional[List[str]] = None,
    exportAs: Optional[Literal["pdf", "pptx"]] = None,
    imageModel: Optional[Literal[
        "flux-1-pro",
        "flux-1-1-pro",
        "imagen-4-pro",
        "imagen-4-ultra",
        "ideogram-v2",
        "ideogram-v2-turbo",
    ]] = None,
    imageStyle: Optional[str] = None,
    workspaceAccess: Optional[Literal[
        "noAccess", "view", "comment", "edit", "fullAccess"
    ]] = None,
    externalAccess: Optional[Literal[
        "noAccess", "view", "comment", "edit"
    ]] = None,
    emailRecipients: Optional[List[str]] = None,
    emailAccess: Optional[Literal[
        "view", "comment", "edit", "fullAccess"
    ]] = None,
) -> str:
    """
    Generate a NEW presentation based on an existing Gamma template.
    The template structure/design is preserved; content is adapted by prompt.

    Args:
        gammaId          : ID of the source Gamma template (REQUIRED)
                           Find it in the deck URL:
                           gamma.app/docs/MY-TITLE-{gammaId}
                           Or use list_my_gammas() if available.
        prompt           : How to adapt the template. Can include:
                           - New topic/content instructions
                           - Image URLs to embed
                           - Tone/audience instructions
                           Example: "Rework this for a non-technical audience"
                           (REQUIRED)
        themeId          : Override template theme (optional)
                           Use list_themes() to find IDs
        folderIds        : List of folder IDs to save into (optional)
                           Use list_folders() to find IDs
        exportAs         : Export as 'pdf' or 'pptx' too (optional)
                           ⚠️ Download quickly — links expire!
        imageModel       : AI image model override (optional)
                           Options: flux-1-pro, flux-1-1-pro,
                           imagen-4-pro, imagen-4-ultra,
                           ideogram-v2, ideogram-v2-turbo
        imageStyle       : Image style hint 1–500 chars (optional)
                           Example: "photorealistic" or
                           "minimal, black and white, line art"
        workspaceAccess  : Who in workspace can access (optional)
                           Options: noAccess/view/comment/edit/fullAccess
        externalAccess   : Public access level (optional)
                           Options: noAccess/view/comment/edit
        emailRecipients  : Email addresses to share with (optional)
        emailAccess      : Access for email recipients (optional)
                           Options: view/comment/edit/fullAccess

    Returns:
        Link to the generated presentation + export links if requested.

    Example:
        generate_from_template(
            gammaId="abcdef1234567890",
            prompt="Change topic to space exploration",
            themeId="i3vnnr2ewxym0se",
            exportAs="pdf"
        )
    """
    print(f"\n🚀 generate_from_template()", flush=True)
    print(f"   gammaId    : {gammaId}", flush=True)
    print(f"   prompt     : {prompt[:100]}", flush=True)
    print(f"   themeId    : {themeId}", flush=True)
    print(f"   exportAs   : {exportAs}", flush=True)

    # Validate
    err = _check_api_key()
    if err: return err

    if not gammaId or not gammaId.strip():
        return "❌ gammaId cannot be empty."
    if not prompt or not prompt.strip():
        return "❌ prompt cannot be empty."

    if imageStyle and len(imageStyle) > 500:
        return "❌ imageStyle must be 500 characters or less."

    # Build payload — only include fields that are set
    params: Dict[str, Any] = {
        "gammaId": gammaId.strip(),
        "prompt":  prompt.strip(),
    }

    if themeId   is not None: params["themeId"]   = themeId
    if folderIds is not None: params["folderIds"]  = folderIds
    if exportAs  is not None: params["exportAs"]   = exportAs

    # imageOptions block
    image_opts: Dict[str, str] = {}
    if imageModel is not None: image_opts["model"] = imageModel
    if imageStyle is not None: image_opts["style"]  = imageStyle
    if image_opts:             params["imageOptions"] = image_opts

    # sharingOptions block
    sharing: Dict[str, Any] = {}
    if workspaceAccess is not None: sharing["workspaceAccess"] = workspaceAccess
    if externalAccess  is not None: sharing["externalAccess"]  = externalAccess

    email_opts: Dict[str, Any] = {}
    if emailRecipients is not None: email_opts["recipients"] = emailRecipients
    if emailAccess     is not None: email_opts["access"]     = emailAccess
    if email_opts:                  sharing["emailOptions"]   = email_opts
    if sharing:                     params["sharingOptions"]  = sharing

    print(f"📦 Payload: {params}", flush=True)

    # Start generation
    endpoint = f"{GAMMA_GENERATIONS}/from-template"
    generation_id, error = await _start_generation(
        endpoint, params, "from-template"
    )
    if error:
        return (
            f"❌ Failed to start from-template generation.\n"
            f"Error: {error}\n\n"
            f"💡 Check your gammaId is correct. "
            f"Find it in the deck URL on gamma.app"
        )
    if generation_id.startswith("DIRECT:"):
        return f"✅ Presentation ready!\n🔗 {generation_id[7:]}"

    # Poll for result
    result = await _poll_generation(generation_id)
    return _format_result(result, "Presentation from template")


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 3 — List Themes
# ══════════════════════════════════════════════════════════════════════════════
@mcp.tool()
async def list_themes() -> str:
    """
    List all available Gamma themes in your workspace.
    Use the returned themeId values in generate_presentation() or
    generate_from_template().

    Returns:
        List of theme names and their IDs.
    """
    print(f"\n🎨 list_themes()", flush=True)

    err = _check_api_key()
    if err: return err

    url = f"{GAMMA_API_BASE}/themes"
    print(f"🔗 GET {url}", flush=True)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=_headers())

        print(f"📥 HTTP {r.status_code} | {r.text[:500]}", flush=True)

        if not r.is_success:
            return (
                f"❌ Could not fetch themes (HTTP {r.status_code}).\n"
                f"Response: {r.text[:300]}"
            )

        data = r.json()

        # Handle various response shapes
        themes = (
            data
            if isinstance(data, list)
            else (
                data.get("themes")
                or data.get("data")
                or data.get("items")
                or []
            )
        )

        if not themes:
            return (
                f"⚠️ No themes returned.\n"
                f"Raw: {data}\n\n"
                f"💡 You can copy a themeId directly from the Gamma app."
            )

        lines = ["🎨 Available Gamma Themes", "=" * 40, ""]
        for i, theme in enumerate(themes, 1):
            name     = theme.get("name") or theme.get("title") or "Unnamed"
            theme_id = (
                theme.get("id")
                or theme.get("themeId")
                or theme.get("_id")
                or "unknown"
            )
            desc = theme.get("description") or ""
            lines.append(f"{i:2}. {name}")
            lines.append(f"    ID : {theme_id}")
            if desc:
                lines.append(f"    📝 {desc}")
            lines.append("")

        lines += [
            "=" * 40,
            "💡 Use themeId in:",
            "   generate_presentation(themeId='...')",
            "   generate_from_template(themeId='...')",
        ]
        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error fetching themes: {type(e).__name__}: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 4 — List Folders
# ══════════════════════════════════════════════════════════════════════════════
@mcp.tool()
async def list_folders() -> str:
    """
    List all Gamma folders in your workspace.
    Use the returned folder IDs in generate_from_template(folderIds=[...]).

    Returns:
        List of folder names and their IDs.
    """
    print(f"\n📁 list_folders()", flush=True)

    err = _check_api_key()
    if err: return err

    url = f"{GAMMA_API_BASE}/folders"
    print(f"🔗 GET {url}", flush=True)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=_headers())

        print(f"📥 HTTP {r.status_code} | {r.text[:500]}", flush=True)

        if not r.is_success:
            return (
                f"❌ Could not fetch folders (HTTP {r.status_code}).\n"
                f"Response: {r.text[:300]}"
            )

        data = r.json()
        folders = (
            data
            if isinstance(data, list)
            else (
                data.get("folders")
                or data.get("data")
                or data.get("items")
                or []
            )
        )

        if not folders:
            return (
                f"⚠️ No folders found.\n"
                f"Raw: {data}\n\n"
                f"💡 Create folders in the Gamma app first."
            )

        lines = ["📁 Available Gamma Folders", "=" * 40, ""]
        for i, folder in enumerate(folders, 1):
            name      = folder.get("name") or folder.get("title") or "Unnamed"
            folder_id = (
                folder.get("id")
                or folder.get("folderId")
                or folder.get("_id")
                or "unknown"
            )
            lines.append(f"{i:2}. {name}")
            lines.append(f"    ID : {folder_id}")
            lines.append("")

        lines += [
            "=" * 40,
            "💡 Use folderIds in:",
            "   generate_from_template(folderIds=['id1', 'id2'])",
        ]
        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error fetching folders: {type(e).__name__}: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 5 — Check Generation Status
# ══════════════════════════════════════════════════════════════════════════════
@mcp.tool()
async def check_generation_status(generation_id: str) -> str:
    """
    Check the status of an existing generation by its ID.
    Useful if a previous generation timed out but may still be running.

    Args:
        generation_id : The generation ID from a previous request
                        e.g. 'qiZhDe7r2zG88PHSp2r0U'

    Returns:
        Current status and URL if completed.
    """
    print(f"\n🔍 check_generation_status({generation_id})", flush=True)

    err = _check_api_key()
    if err: return err

    if not generation_id or not generation_id.strip():
        return "❌ generation_id cannot be empty."

    url = f"{GAMMA_GENERATIONS}/{generation_id.strip()}"
    print(f"🔗 GET {url}", flush=True)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=_headers())

        print(f"📥 HTTP {r.status_code} | {r.text[:500]}", flush=True)

        if r.status_code == 404:
            return f"❌ Generation '{generation_id}' not found."

        if not r.is_success:
            return f"❌ HTTP {r.status_code}: {r.text[:300]}"

        data   = r.json()
        status = data.get("status", "unknown").lower()

        if status in ("completed", "complete", "done", "success"):
            presentation_url = _extract_url(data, generation_id)
            pdf_url  = data.get("pdfUrl")
            pptx_url = data.get("pptxUrl")

            lines = [
                f"✅ Generation COMPLETED!",
                f"",
                f"🆔 ID           : {generation_id}",
                f"🔗 View here    : {presentation_url}",
            ]
            if pdf_url:
                lines.append(f"📄 PDF          : {pdf_url}")
            if pptx_url:
                lines.append(f"📊 PPTX         : {pptx_url}")
            return "\n".join(lines)

        elif status in ("failed", "error", "cancelled", "canceled"):
            msg = data.get("message") or data.get("error") or status
            return (
                f"❌ Generation FAILED\n"
                f"🆔 ID     : {generation_id}\n"
                f"📊 Status : {status}\n"
                f"💬 Reason : {msg}"
            )

        else:
            return (
                f"⏳ Generation is still {status.upper()}\n"
                f"🆔 ID     : {generation_id}\n"
                f"💡 Try again in a minute, or check https://gamma.app"
            )

    except Exception as e:
        return f"❌ Error checking status: {type(e).__name__}: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 6 — Test Connection
# ══════════════════════════════════════════════════════════════════════════════
@mcp.tool()
async def test_connection() -> str:
    """
    Test the MCP server health and Gamma API connectivity.
    Run this first to verify everything is configured correctly.
    """
    print("\n🔍 test_connection()", flush=True)
    lines = ["🔍 Gamma MCP Server — Connection Test", "=" * 45, ""]

    # API Key
    if GAMMA_API_KEY:
        masked = f"{GAMMA_API_KEY[:6]}****{GAMMA_API_KEY[-4:]}"
        lines.append(f"✅ API Key         : {masked}")
    else:
        lines.append("❌ API Key         : NOT SET — add GAMMA_API_KEY to .env!")

    # Network
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://public-api.gamma.app")
        lines.append(f"✅ Gamma API       : Reachable (HTTP {r.status_code})")
    except httpx.TimeoutException:
        lines.append("❌ Gamma API       : Timeout")
    except httpx.ConnectError:
        lines.append("❌ Gamma API       : Cannot connect")
    except Exception as e:
        lines.append(f"❌ Gamma API       : {e}")

    # Config
    lines += [
        "",
        f"✅ MCP Server      : Running",
        f"🔗 Base URL        : {GAMMA_API_BASE}",
        f"⏳ Poll interval   : {POLL_INTERVAL_SEC}s",
        f"⏳ Max attempts    : {POLL_MAX_ATTEMPTS}",
        f"⏳ Max wait        : {POLL_MAX_ATTEMPTS * POLL_INTERVAL_SEC}s "
        f"({POLL_MAX_ATTEMPTS * POLL_INTERVAL_SEC // 60} min "
        f"{POLL_MAX_ATTEMPTS * POLL_INTERVAL_SEC % 60}s)",
        f"🔄 Max retries     : {POLL_MAX_RETRIES}",
        "",
        "🛠️  Available Tools:",
        "   1. generate_presentation    — New presentation from topic",
        "   2. generate_from_template   — From existing Gamma deck",
        "   3. list_themes              — Browse available themes",
        "   4. list_folders             — Browse workspace folders",
        "   5. check_generation_status  — Check a past generation",
        "   6. test_connection          — This health check",
    ]

    output = "\n".join(lines)
    print(output, flush=True)
    return output


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 60, flush=True)
    print("🤖  Gamma Presentation MCP Server", flush=True)
    print("=" * 60, flush=True)

    if not GAMMA_API_KEY:
        print("❌ GAMMA_API_KEY missing from .env!", flush=True)
        print("   Create .env file with:", flush=True)
        print("   GAMMA_API_KEY=sk-gamma-xxxxxxxxxx", flush=True)
        sys.exit(1)

    masked = f"{GAMMA_API_KEY[:6]}****{GAMMA_API_KEY[-4:]}"
    port   = int(os.environ.get("PORT", 8000))

    print(f"✅ API Key     : {masked}", flush=True)
    print(f"🚀 Port        : {port}", flush=True)
    print(f"⏳ Poll config : {POLL_MAX_ATTEMPTS} × {POLL_INTERVAL_SEC}s "
          f"= {POLL_MAX_ATTEMPTS * POLL_INTERVAL_SEC}s max", flush=True)
    print(f"🛠️  Tools       : 6 tools registered", flush=True)
    print("=" * 60, flush=True)

    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
    )


if __name__ == "__main__":
    main()
