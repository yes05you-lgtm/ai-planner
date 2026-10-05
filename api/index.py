import os
import sys

# 프로젝트 루트 경로를 sys.path에 추가
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app import app
