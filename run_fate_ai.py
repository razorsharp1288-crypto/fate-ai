"""Launcher used by PyInstaller and for running from source: python run_fate_ai.py"""
import sys

from fate_ai.main import main

if __name__ == "__main__":
    sys.exit(main())
