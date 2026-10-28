"""
Generates high-fidelity, single-pass studio voiceover narration for the AP2 Autonomous Commerce
PayPal AI Hackathon demo video (~3m) using Google's dedicated Gemini 3.8 Flash TTS model
(`gemini-3.8-flash-tts` via `/v1beta/interactions`) with the `Achird` voice.

Synthesizes all 5 acts in a single continuous pass at a uniform, natural 1.0x cadence with
zero `atempo` time-stretching, and masters the output with -4.0dB headroom, 6.5kHz de-essing,
and 48kHz stereo soft-limiting to eliminate any inter-sample or AAC peak distortion.
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
        "AP2 Autonomous Commerce solves this on PayPal Subscriptions using Google's Agent Payments Protocol, "
        "now under the FIDO Alliance. First, on our Trusted Surface, the human owner signs a sixty-dollar "
        "cryptographic spending limit and forwards the open mandates to the agent. "
        "Now watch the 3D pipeline as our buyer agent bargains down from a seventy-nine ninety-nine gateway "
        "to a forty-nine ninety-nine Batch Worker that fits the owner's rule. "
        "And if a prompt-injected agent lies and claims a two-hundred-dollar budget, the isolated Buyer Wallet "
        "M C P server blocks the signature before any money can move."
    ),
    (
        "Switching to the Setup console, let's run an autonomous AP2 negotiation under a one-hundred-dollar cap. "
        "The seller verifies the mandate policy at seventy-nine ninety-nine a month and settles the recurring "
        "subscription through PayPal Subscriptions and the PayPal Agent Toolkit. "
        "In the right-hand inspector, we can audit the full ES256 SD-JWT execution trace and merchant receipts. "
        "Next, in the Anti-Tamper Verifier, if an attacker inflates the signed payload by even one cent, "
        "live signature re-verification immediately rejects the transaction with a 401 signature mismatch."
    ),
    (
        "In the operations deck, A G Studio version three and A G Grid power the enterprise fleet ledger "
        "across fourteen seeded nodes, reconciling twelve hundred nineteen dollars in monthly recurring revenue. "
        "Operators can filter active subscriptions and switch seamlessly between Mission Control, Executive View, "
        "and the Drag and Drop Editor. "
        "Switching to Workloads, Bryntum Scheduler maps regional compute shifts across five worker clusters. "
        "As soon as PayPal confirms settlement, the pending compute node transitions in place from amber "
        "awaiting payment to active, and dispatches live workload tasks across the timeline."
    ),
    (
        "On the M C P tab, running the subscription chain triggers our Zapier back-office bridge. "
        "In the Wire and Schema Inspector, you can inspect the QuickBooks Online version three expense payload "
        "mapped to General Ledger Account sixty-three hundred, the CloudEvents JSON-RPC frame, and the "
        "HMAC-SHA256 signed webhook envelope, alongside our OpenAPI three point one contract and APIMatic SDKs."
    ),
    (
        "Finally, everything is empirically verifiable in a single command. "
        "Running our Judge Audit Harness executes all nine cryptographic and operational invariant checks "
        "in under one second, while our standalone buyer agent CLI negotiates and settles end to end. "
        "The system is backed by seven hundred ninety-two passing automated tests, including all "
        "one hundred eighty-eight upstream Google AP2 SDK conformance tests and a transparent twenty-two-entry "
        "mock ledger. This is AP2 Autonomous Commerce, built for the PayPal AI Hackathon."
    ),
]


def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required in environment or .env")

    full_transcript = " <short pause> ".join(ACT_PARAGRAPHS)
    print("=======================================================")
    print("🎙️ Synthesizing Single-Pass Studio Narration (gemini-3.8-flash-tts — Achird)")
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
                                        "friendly, natural, smooth conversational product presenter "
                                        "with soft studio warmth at a consistent, steady pace"
                                    ),
                                }
                            ],
                        }
                    ],
                }
            ],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": "Achird"}]},
        },
        timeout=240.0,
    )
    response.raise_for_status()
    payload = response.json()
    wav_bytes = base64.b64decode(payload["steps"][0]["content"][0]["data"])

    raw_wav_path = OUTPUT_DIR / "master_narration_achird_raw.wav"
    wav_path = OUTPUT_DIR / "master_narration_120s.wav"
    mp3_path = OUTPUT_DIR / "master_narration_2min.mp3"
    raw_wav_path.write_bytes(wav_bytes)

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        duration_s = round(wf.getnframes() / wf.getframerate(), 2)

    # Master audio: -4.0dB headroom, 75Hz highpass, 6.5kHz de-ess, 48kHz stereo, soft limiter
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(raw_wav_path),
            "-af",
            "volume=-4.0dB,highpass=f=75,treble=g=-2.0:f=6500,aresample=48000,pan=stereo|c0=c0|c1=c0,alimiter=limit=0.75:attack=5:release=50",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(wav_path),
        ],
        check=True,
        capture_output=True,
    )
    raw_wav_path.unlink(missing_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libmp3lame", "-b:a", "192k", str(mp3_path)],
        check=True,
        capture_output=True,
    )
    print(f"✅ Rendered & Mastered {wav_path.name} ({duration_s}s at pure 1.0x speed, Achird 48kHz stereo) & {mp3_path.name}")


if __name__ == "__main__":
    main()
