from __future__ import annotations

import pytest

from paperlab.llm.client import call_llm


def test_call_llm_raises_when_api_key_missing():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        call_llm(
            api_key="",
            base_url="https://open.bigmodel.cn/api/coding/paas/v4",
            model="glm-5.1",
            system_prompt="You are a test.",
            user_prompt="Return JSON.",
        )


def test_call_llm_raises_when_base_url_missing():
    with pytest.raises(ValueError, match="base_url"):
        call_llm(
            api_key="dummy-key",
            base_url="",
            model="glm-5.1",
            system_prompt="You are a test.",
            user_prompt="Return JSON.",
        )


def test_call_llm_raises_when_model_missing():
    with pytest.raises(ValueError, match="model"):
        call_llm(
            api_key="dummy-key",
            base_url="https://open.bigmodel.cn/api/coding/paas/v4",
            model="",
            system_prompt="You are a test.",
            user_prompt="Return JSON.",
        )
