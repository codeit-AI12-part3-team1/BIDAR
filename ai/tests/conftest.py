"""torch/transformers 가 설치돼 있지 않은 환경(CI 등)에서도 ai.rag.chain 의
순수 로직 테스트는 돌아가게 하는 조건부 스텁.

실제로 torch/transformers 가 설치돼 있으면 이 스텁은 아무것도 하지 않는다 —
진짜 라이브러리가 그대로 쓰인다. import 자체가 실패할 때만 대신 채워 넣는다.
"""

import sys
import types


def _install_stub_if_missing(name, build):
    try:
        __import__(name)
    except ImportError:
        sys.modules[name] = build()


def _fake_torch():
    mod = types.ModuleType("torch")

    class _NoGrad:
        def __enter__(self):
            return None

        def __exit__(self, *a):
            return False

    mod.no_grad = lambda: _NoGrad()
    mod.cuda = types.SimpleNamespace(
        empty_cache=lambda: None, is_available=lambda: False)
    return mod


def _fake_transformers():
    mod = types.ModuleType("transformers")
    mod.AutoModelForCausalLM = object
    mod.AutoTokenizer = object
    return mod


_install_stub_if_missing("torch", _fake_torch)
_install_stub_if_missing("transformers", _fake_transformers)
