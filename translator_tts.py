import asyncio
import json
import os
import sys
import edge_tts

# Neural voice models for different languages
VOICES = {
    'es': 'es-ES-AlvaroNeural',       # Spanish (Spain)
    'es-mx': 'es-MX-JorgeNeural',     # Spanish (Mexico)
    'de': 'de-DE-ConradNeural',       # German
    'fr': 'fr-FR-HenriNeural',        # French
    'pt': 'pt-BR-AntonioNeural',      # Portuguese (Brazil)
    'ru': 'ru-RU-DmitryNeural',       # Russian
    'en': 'en-US-ChristopherNeural'   # English
}

async def generate_tts(text, voice, output_filename):
    print(f"Generating TTS audio using voice '{voice}' -> {output_filename}...")
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_filename)
    print(f"Saved audio to {output_filename}")

def process_story_audio(lang_code='es'):
    story_file = os.path.join(os.path.dirname(__file__), 'story_data.json')
    if not os.path.exists(story_file):
        print(f"Story data file not found: {story_file}. Please run scraper.py first.")
        return

    with open(story_file, 'r', encoding='utf-8') as f:
        story = json.load(f)

    voice = VOICES.get(lang_code, VOICES['es'])
    
    # Full narrative script concatenation
    narration_text = f"{story.get('title', '')}. "
    if story.get('body'):
        narration_text += f"{story.get('body')} "
    for comm in story.get('comments', []):
        narration_text += f"Comment by {comm.get('username')}: {comm.get('body')}. "

    output_audio = os.path.join(os.path.dirname(__file__), f"narration_{lang_code}.mp3")
    
    # Run async Edge-TTS
    asyncio.run(generate_tts(narration_text, voice, output_audio))

if __name__ == '__main__':
    target_lang = sys.argv[1] if len(sys.argv) > 1 else 'es'
    process_story_audio(target_lang)
