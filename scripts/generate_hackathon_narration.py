"""
Generates high-fidelity voiceover narration for the FieldSmith Pro PayPal AI Hackathon demo video.
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
        "Every day, solo trade contractors like custom tile setters and emergency plumbers "
        "lose over $6,200 a month in uncaptured revenue from missed calls while operating machinery "
        "or driving on jobsites. They don't have time for 15-field web forms or SaaS onboarding fatigue. "
        "FieldSmith Pro solves this with an Autonomous Agent-to-Agent Commerce protocol built on PayPal."
    ),
    "act2_buyer_agent": (
        "Meet Marcus Miller's Autonomous Buyer Agent. When Marcus is busy, his agent inspects "
        "telephony call leaks, verifies his local spending mandate cap of $100 a month, and "
        "negotiates directly with FieldSmith's Seller Agent over Model Context Protocol. "
        "Once approved, the agent issues a cryptographic HMAC proof and delegates a recurring "
        "$89-a-month PayPal subscription with verified KYC identity, instantly allocating a "
        "dedicated Telnyx business line."
    ),
    "act3_bryntum_agstudio": (
        "In our operations deck, Bryntum Scheduler visualizes telephony fleet readiness across "
        "four Florida territory zones. Notice Marcus Miller's card dynamically mutates in place "
        "from amber awaiting payment to vibrant green line active upon payment confirmation. "
        "Meanwhile, AG Studio version 3 embeds high-density analytics, allowing fleet managers "
        "to toggle between View and Edit modes, customize visual reports, and track recovered "
        "revenue by trade vertical."
    ),
    "act4_zapier_mcp": (
        "Once PayPal verifies the payment, our Zapier Model Context Protocol bridge fires an "
        "autonomous downline action chain: logging the recurring software expense into QuickBooks Online, "
        "routing the new Telnyx phone line into Jobber CRM, and scheduling Marcus's daily 6:30 AM "
        "Executive Dispatch briefing on Google Calendar — eliminating evening paperwork entirely."
    ),
    "act5_kyc_telecom": (
        "Crucially, every phone line is legally anchored to verified PayPal subscriber identity — "
        "ensuring 100% inbound protection with zero autodialer abuse. "
        "With 17 automated tests, complete OpenAPI 3.1 specifications for APIMatic SDK generation, "
        "and zero human friction, this is FieldSmith Pro. Built for the PayPal AI Hackathon."
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
