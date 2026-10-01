"""CI가 pytest를 실제로 돌리는지 확인하는 최소 테스트. 실제 테스트가 생기면 지운다."""

import sys


def test_python_version():
    assert sys.version_info >= (3, 12)
