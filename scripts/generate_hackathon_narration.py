"""
Generates high-fidelity voiceover narration for the AP2 Autonomous Commerce PayPal AI Hackathon demo video.
Uses Google Gemini Live (gemini-3.8-live) with the canonical 'Sulafat' voice,
tuned for an articulate, confident, tech-founder presentation tone.
Generates individual act MP3s and concatenates into master_narration_2min.mp3.
"""

import os
import sys
import asyncio
import wave
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
from google import genai
from google.genai import types

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "media" / "hackathon_demo"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ACT_SCRIPTS = {
    "act1_problem": (
        "AI agents are starting to buy what they need, like compute. Usually that means handing them a card "
        "number, and any page or reply the agent reads can steer it. AP2 Autonomous Commerce is built on AP2, "
        "the agent payments protocol Google donated to the FIDO Alliance, with PayPal Subscriptions as the "
        "payment rail."
    ),
    "act2_buyer_agent": (
        "Here, a desktop AI agent shops for a compute node under a $60 monthly limit its owner signed in "
        "advance. It asks for the $79.99 gateway, and the seller counter-offers the $49.99 batch worker. The "
        "agent never holds a key. A separate wallet checks the signed price against the owner's limit before "
        "signing. Even when we told the seller our budget was $200, the wallet refused."
    ),
    "act3_bryntum_agstudio": (
        "In the operations deck, AG Studio and AG Grid show the fleet ledger, with floating filters and View "
        "and Edit modes, while Bryntum Scheduler lays out the compute dispatch calendar. The fleet you see "
        "here is seeded demo data, and we label it that way. When a node is provisioned through the backend, "
        "its card turns from amber to green."
    ),
    "act4_zapier_mcp": (
        "After a purchase, the back-office export builds a QuickBooks Online expense mapped to general ledger "
        "account 6300, plus a calendar entry for the node's health check. It checks the destination, signs "
        "the payload, and sends it to a Zapier hook once one is configured. Until then, it's a dry run."
    ),
    "act5_kyc_compute": (
        "Subscriptions keep billing, so every month, when PayPal reports a renewal, the server re-checks it "
        "against the owner's signed mandate, and cancels in advance before the payment count, budget or term "
        "runs out. It's backed by 581 passing tests, including Google's own AP2 SDK tests, unchanged. This is "
        "AP2 Autonomous Commerce, built for the PayPal AI Hackathon."
    ),
}


async def generate_narration_act(client, name: str, text: str, voice_name: str = "Sulafat"):
    wav_path = OUTPUT_DIR / f"{name}.wav"
    mp3_path = OUTPUT_DIR / f"{name}.mp3"

    print(f"🎙️ [ACT {name}] Synthesizing with Gemini 3.8 Live ({voice_name})...")

    system_instruction = (
        "You are an articulate, confident, tech-founder presenting a high-impact software demo "
        "to judges at the PayPal AI Hackathon. Speak clearly in a steady, conversational, "
        "authoritative cadence. Do not rush, do not sound like a cheesy advertisement. "
        "Speak like an engineer who built a production-grade system."
    )

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
            )
        ),
        system_instruction=types.Content(
            parts=[types.Part(text=system_instruction)]
        ),
    )

    audio_chunks = []
    async with client.aio.live.connect(model="gemini-3.8-live", config=config) as session:
        prompt = f"Speak clearly and naturally: \"{text}\""
        await session.send(input=prompt, end_of_turn=True)

        async for response in session.receive():
            if response.server_content and response.server_content.model_turn:
                for part in response.server_content.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        audio_chunks.append(part.inline_data.data)
            if response.server_content and response.server_content.turn_complete:
                break

    total_audio = b"".join(audio_chunks)
    if not total_audio:
        raise RuntimeError(f"No audio received from Gemini for {name}")

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(total_audio)

    # Encode to MP3 via ffmpeg
    cmd = [
        "ffmpeg", "-y", "-i", str(wav_path),
        "-codec:a", "libmp3lame", "-b:a", "192k",
        str(mp3_path)
    ]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode == 0:
        print(f"✅ [ACT {name}] Encoded {mp3_path.name} ({mp3_path.stat().st_size:,} bytes)")
    else:
        print(f"❌ [ACT {name}] FFmpeg error: {res.stderr.decode('utf-8', errors='ignore')}")

    return mp3_path


async def main():
    client = genai.Client()
    print("=======================================================")
    print("🎬 Generating Master Narration Audio for Demo Video")
    print(f"   Target Directory: {OUTPUT_DIR}")
    print("=======================================================\n")

    generated_mp3s = []
    for act_name, script_text in ACT_SCRIPTS.items():
        mp3 = await generate_narration_act(client, act_name, script_text)
        generated_mp3s.append(mp3)

    # Concatenate into master 120s narration
    master_mp3 = OUTPUT_DIR / "master_narration_2min.mp3"
    concat_list = OUTPUT_DIR / "concat_list.txt"
    with open(concat_list, "w") as f:
        for mp3 in generated_mp3s:
            f.write(f"file '{mp3.name}'\n")

    concat_cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(master_mp3)
    ]
    subprocess.run(concat_cmd, capture_output=True)
    if master_mp3.exists():
        print(f"\n🎉 [COMPLETE] Master Narration Rendered: {master_mp3.name} ({master_mp3.stat().st_size:,} bytes)")
    print("=======================================================\n")


if __name__ == "__main__":
    asyncio.run(main())
