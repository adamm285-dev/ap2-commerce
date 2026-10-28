"""
Generates high-fidelity, single-pass studio voiceover narration for the AP2 Autonomous Commerce
PayPal AI Hackathon demo video using Google's dedicated Gemini 3.8 Flash TTS model
(`gemini-3.8-flash-tts` via `/v1beta/interactions`) with the `Sulafat` voice.

Unlike conversational Live API WebSocket sessions (which vary speaking speed and tone across turns),
`gemini-3.8-flash-tts` synthesizes the entire 5-act script in a single continuous pass at a uniform,
natural 1.0x cadence (`~119.7s` total duration, zero `atempo` time-stretching).
"""

import base64
import io
import os
import subprocess
import wave
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "media" / "hackathon_demo"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ACT_PARAGRAPHS = [
    (
        "When an autonomous AI agent buys cloud compute, handing the model your private payment keys "
        "is a serious security risk. A single prompt injection can drain your account. "
        "A P 2 Autonomous Commerce solves this on PayPal Subscriptions using Google's Agent Payments Protocol. "
        "Here on our Trusted Surface, the human owner signs cryptographic spending limits while keeping "
        "private keys isolated inside a separate Buyer Wallet M C P server."
    ),
    (
        "On the Setup console, our buyer agent acts as an untrusted courier over Model Context Protocol. "
        "When a request exceeds a sixty-dollar cap, the seller counter-offers a forty-nine ninety-nine Batch Worker. "
        "Under a one-hundred-dollar cap, it settles the seventy-nine ninety-nine Service Gateway via PayPal Subscriptions. "
        "Every renewal is re-verified against the owner's mandate, and in our Anti-Tamper Verifier, "
        "even a one-cent price change is rejected."
    ),
    (
        "In the operations deck, A G Studio version three and A G Grid power the fleet ledger, "
        "letting operators switch between Mission Control, Executive View, and the Drag and Drop Editor "
        "across fourteen seeded nodes. Switching to Workloads, Bryntum Scheduler maps regional compute shifts, "
        "and once PayPal confirms settlement, the node transitions in place from awaiting payment to active."
    ),
    (
        "Once settled, our Zapier M C P bridge dispatches a signed QuickBooks Online version three expense payload "
        "mapped to General Ledger Account sixty-three hundred, and schedules node health checks automatically. "
        "Meanwhile, our Open A P I three point one contract and A P I Matic configuration generate SDKs "
        "for buyer key enrollment."
    ),
    (
        "Everything is empirically verifiable in one command. Running our Judge Audit Harness verifies "
        "all nine cryptographic and operational invariants in under one second, backed by seven hundred ninety-two "
        "passing tests, including all one hundred eighty-eight Google A P 2 conformance tests. "
        "This is A P 2 Autonomous Commerce, built for the PayPal A I Hackathon."
    ),
]


def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required in environment or .env")

    full_transcript = " <short pause> ".join(ACT_PARAGRAPHS)
    print("=======================================================")
    print("🎙️ Synthesizing Single-Pass Studio Narration (gemini-3.8-flash-tts)")
    print(f"   Target Directory: {OUTPUT_DIR}")
    print("=======================================================")

    response = httpx.post(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        headers={
            "x-goog-api-key": api_key,
            "Api-Revision": "2026-05-20",
            "Content-Type": "application/json",
        },
        json={
            "model": "gemini-3.8-flash-tts",
            "input": [
                {
                    "type": "user_input",
                    "content": [
                        {
                            "type": "text",
                            "text": full_transcript,
                            "annotations": [
                                {
                                    "type": "speech_metadata",
                                    "style": (
                                        "steady, warm, articulate technical founder narrating "
                                        "a product walkthrough at a consistent, natural pace"
                                    ),
                                }
                            ],
                        }
                    ],
                }
            ],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": "Sulafat"}]},
        },
        timeout=180.0,
    )
    response.raise_for_status()
    payload = response.json()
    wav_bytes = base64.b64decode(payload["steps"][0]["content"][0]["data"])

    wav_path = OUTPUT_DIR / "master_narration_120s.wav"
    mp3_path = OUTPUT_DIR / "master_narration_2min.mp3"
    wav_path.write_bytes(wav_bytes)

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        duration_s = round(wf.getnframes() / wf.getframerate(), 2)

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libmp3lame", "-b:a", "192k", str(mp3_path)],
        check=True,
        capture_output=True,
    )
    print(f"✅ Rendered {wav_path.name} ({duration_s}s at pure 1.0x speed) & {mp3_path.name}")


if __name__ == "__main__":
    main()
