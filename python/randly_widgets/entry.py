#!/usr/bin/env python3
"""Python editor, providers and catalog tools behind the native manager."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from randly_widgets.cli import main
if __name__=='__main__':raise SystemExit(main())
