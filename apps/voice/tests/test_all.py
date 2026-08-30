#!/usr/bin/env python3
"""
Integration Test Script for AI Voice Terminal
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import MIMO_API_KEY, MIMO_API_URL, MIMO_MODEL
from llm.mimo import MiMoLLM
from tts.tts import TTSEngine
from audio.play import AudioPlayer


def test_config():
    """Test configuration"""
    print("=" * 50)
    print("Testing Configuration...")
    print("=" * 50)

    print(f"MiMo API URL: {MIMO_API_URL}")
    print(f"MiMo Model: {MIMO_MODEL}")
    print(f"API Key configured: {'Yes' if MIMO_API_KEY != 'your_api_key_here' else 'No (Please set MIMO_API_KEY)'}")

    if MIMO_API_KEY == 'your_api_key_here':
        print("\n⚠️  WARNING: Please set your MiMo API key!")
        print("Option 1: Set environment variable: export MIMO_API_KEY='your_key'")
        print("Option 2: Edit config/config.py directly")
        return False

    return True


def test_llm():
    """Test MiMo LLM module"""
    print("\n" + "=" * 50)
    print("Testing MiMo LLM...")
    print("=" * 50)

    try:
        llm = MiMoLLM()
        print("MiMo LLM initialized successfully")

        test_input = "你好，请用一句话介绍自己"
        print(f"\nTest input: {test_input}")
        print("Calling MiMo API...")

        response = llm.chat(test_input)
        print(f"Response: {response}")

        return True
    except Exception as e:
        print(f"LLM test failed: {e}")
        return False


def test_tts():
    """Test TTS module"""
    print("\n" + "=" * 50)
    print("Testing TTS...")
    print("=" * 50)

    try:
        tts = TTSEngine()
        print(f"TTS Engine: {tts.engine_type}")

        test_text = "你好，这是TTS测试"
        print(f"\nTest text: {test_text}")
        print("Converting to speech...")

        audio_file = tts.text_to_speech(test_text)
        if audio_file:
            print(f"Audio file created: {audio_file}")
            return True
        else:
            print("TTS conversion failed")
            return False
    except Exception as e:
        print(f"TTS test failed: {e}")
        return False


def test_audio():
    """Test audio playback module"""
    print("\n" + "=" * 50)
    print("Testing Audio Playback...")
    print("=" * 50)

    try:
        player = AudioPlayer()
        print(f"Audio backend: {player.backend}")

        if player.backend == 'none':
            print("⚠️  WARNING: No audio playback backend available!")
            print("Please install one of: aplay (ALSA), mpv, ffplay, or pygame")
            return False

        # Test with existing audio file if available
        from config import AUDIO_FILE
        if os.path.exists(AUDIO_FILE):
            print(f"\nTest file: {AUDIO_FILE}")
            print("Playing...")
            if player.play(AUDIO_FILE):
                print("Playback successful!")
                return True
            else:
                print("Playback failed")
                return False
        else:
            print("No test audio file found. Run TTS test first.")
            return True  # Not a failure, just no test file

    except Exception as e:
        print(f"Audio test failed: {e}")
        return False


def test_integration():
    """Test full integration"""
    print("\n" + "=" * 50)
    print("Testing Full Integration...")
    print("=" * 50)

    try:
        llm = MiMoLLM()
        tts = TTSEngine()
        player = AudioPlayer()

        test_input = "你好"
        print(f"Input: {test_input}")

        # LLM
        print("1. Calling MiMo API...")
        response = llm.chat(test_input)
        print(f"   Response: {response}")

        # TTS
        print("2. Converting to speech...")
        audio_file = tts.text_to_speech(response)
        if not audio_file:
            print("   TTS failed, skipping audio playback")
            return False

        # Audio
        print("3. Playing audio...")
        if player.play(audio_file):
            print("   Integration test passed!")
            return True
        else:
            print("   Audio playback failed")
            return False

    except Exception as e:
        print(f"Integration test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 50)
    print("AI Voice Terminal - Integration Test")
    print("=" * 50)

    results = {}

    # Run tests
    results['config'] = test_config()
    results['llm'] = test_llm() if results['config'] else False
    results['tts'] = test_tts()
    results['audio'] = test_audio()
    results['integration'] = test_integration() if all(results.values()) else False

    # Summary
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name.upper():15} {status}")

    all_passed = all(results.values())
    print("\n" + "=" * 50)
    if all_passed:
        print("All tests passed! System is ready.")
    else:
        print("Some tests failed. Please check the errors above.")
    print("=" * 50)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())