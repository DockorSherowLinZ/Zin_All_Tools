#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI VLM Classifier for 3ds Max AI Material Assigner
===================================================
Reads a request file, sends images to Google Gemini API for classification,
and writes results to an output file.

Uses ONLY Python built-in libraries (no pip install required).

Usage:
    python ai_vlm_classify.py <request_file> <result_file>

Request file format (pipe-delimited):
    API_KEY|<key>
    MODEL|<model_name>
    CATEGORIES|<comma-separated list>
    DELAY|<seconds between requests>
    SHAPE|<fingerprint_id>|<image_path>

Result file format (pipe-delimited):
    <fingerprint_id>|<label>|<confidence>
"""

import sys
import os
import json
import base64
import time
import urllib.request
import urllib.error
import ssl


def create_ssl_context():
    """Create SSL context with fallback for environments without certificates."""
    try:
        ctx = ssl.create_default_context()
        return ctx
    except Exception:
        # Fallback: unverified context (less secure but works everywhere)
        ctx = ssl._create_unverified_context()
        return ctx


def encode_image_base64(image_path):
    """Read an image file and return its Base64-encoded string."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_gemini_api(api_key, model, image_base64, categories, ssl_ctx):
    """
    Call Google Gemini API with an image for material classification.

    Returns:
        dict: {"label": "<category>", "confidence": <0-100>}
    """
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )

    categories_str = ", ".join(categories)

    prompt = (
        "You are an industrial 3D model material classifier specializing in "
        "barcode scanners, electronic devices, and industrial equipment components.\n\n"
        "Analyze this 3D mesh captured from a viewport screenshot. "
        "The mesh is shown isolated on a neutral background.\n\n"
        f"Classify it into exactly ONE of these material categories:\n{categories_str}\n\n"
        "Rules:\n"
        "- Choose the single best matching category based on the object's likely real-world material.\n"
        "- If uncertain, pick the closest match rather than guessing randomly.\n"
        "- Consider the shape, surface characteristics, and typical industrial usage.\n\n"
        'Output ONLY a valid JSON object in this exact format: {"label": "<category>", "confidence": <0-100>}\n'
        "Do not include any other text, markdown formatting, code blocks, or explanation."
    )

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {
                    "mime_type": "image/jpeg",
                    "data": image_base64
                }}
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 100
        }
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=60, context=ssl_ctx) as response:
        result = json.loads(response.read().decode("utf-8"))

    # Extract text from Gemini response
    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Unexpected API response structure: {e}")

    # Clean up response text (remove markdown code blocks if present)
    text = text.strip()
    if text.startswith("```"):
        # Remove ```json or ``` prefix
        lines = text.split("\n")
        text = "\n".join(lines[1:])
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Parse JSON
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError(f"Could not parse VLM response as JSON: {text}")

    label = parsed.get("label", "Unknown")
    confidence = int(parsed.get("confidence", 0))

    return {"label": label, "confidence": confidence}


def parse_request_file(request_path):
    """Parse the pipe-delimited request file."""
    api_key = ""
    model = "gemini-2.0-flash"
    categories = []
    delay = 4.0
    shapes = []

    with open(request_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|", 2)
            tag = parts[0]

            if tag == "API_KEY" and len(parts) >= 2:
                api_key = parts[1]
            elif tag == "MODEL" and len(parts) >= 2:
                model = parts[1]
            elif tag == "CATEGORIES" and len(parts) >= 2:
                categories = [c.strip() for c in parts[1].split(",") if c.strip()]
            elif tag == "DELAY" and len(parts) >= 2:
                try:
                    delay = float(parts[1])
                except ValueError:
                    delay = 4.0
            elif tag == "SHAPE" and len(parts) >= 3:
                shapes.append({"id": parts[1], "image_path": parts[2]})

    return api_key, model, categories, delay, shapes


def main():
    if len(sys.argv) < 3:
        print("Usage: python ai_vlm_classify.py <request_file> <result_file>")
        sys.exit(1)

    request_path = sys.argv[1]
    result_path = sys.argv[2]

    if not os.path.exists(request_path):
        print(f"ERROR: Request file not found: {request_path}")
        sys.exit(1)

    # Parse request
    api_key, model, categories, delay, shapes = parse_request_file(request_path)

    if not api_key:
        print("ERROR: No API key provided in request file.")
        sys.exit(1)

    if not categories:
        print("ERROR: No categories provided in request file.")
        sys.exit(1)

    if not shapes:
        print("ERROR: No shapes to classify in request file.")
        sys.exit(1)

    print(f"AI VLM Classifier started.")
    print(f"  Model: {model}")
    print(f"  Categories: {len(categories)}")
    print(f"  Shapes to classify: {len(shapes)}")
    print(f"  Delay between requests: {delay}s")
    print()

    ssl_ctx = create_ssl_context()
    results = []

    for i, shape in enumerate(shapes):
        shape_id = shape["id"]
        image_path = shape["image_path"]

        print(f"[{i+1}/{len(shapes)}] Classifying shape: {shape_id} ...", end=" ", flush=True)

        try:
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image not found: {image_path}")

            img_b64 = encode_image_base64(image_path)
            result = call_gemini_api(api_key, model, img_b64, categories, ssl_ctx)

            label = result["label"]
            confidence = result["confidence"]
            results.append(f"{shape_id}|{label}|{confidence}")
            print(f"-> {label} ({confidence}%)")

        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
            except Exception:
                pass
            print(f"-> API ERROR {e.code}: {error_body[:200]}")
            results.append(f"{shape_id}|Unknown|0")

        except Exception as e:
            print(f"-> ERROR: {str(e)[:200]}")
            results.append(f"{shape_id}|Unknown|0")

        # Rate limiting delay (skip after last item)
        if i < len(shapes) - 1 and delay > 0:
            time.sleep(delay)

    # Write results
    with open(result_path, "w", encoding="utf-8") as f:
        f.write("# AI VLM Classification Results\n")
        f.write(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Format: fingerprint_id|label|confidence\n")
        for r in results:
            f.write(r + "\n")

    print()
    print(f"Classification complete. {len(results)} results written to: {result_path}")


if __name__ == "__main__":
    main()
