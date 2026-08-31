"""Gemini API の薄いラッパー。"""

from __future__ import annotations

import time
from typing import Iterator

import streamlit as st
from google import genai
from google.genai import types

from core.config import AppConfig, supports_thinking_off


class GeminiError(RuntimeError):
    """ユーザーに見せる想定のエラー。"""


@st.cache_resource(show_spinner=False)
def _client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


@st.cache_data(show_spinner=False, ttl=3600)
def list_models(api_key: str) -> tuple[list[str], str]:
    """このAPIキーで使えるモデル名の一覧と、失敗時の理由を返す。"""
    if not api_key.strip():
        return [], "APIキーが未設定です。"

    try:
        raw = list(_client(api_key).models.list())
    except Exception as exc:
        return [], _redact(f"{type(exc).__name__}: {exc}", api_key)

    names: list[str] = []
    for model in raw:
        actions = getattr(model, "supported_actions", None) or []
        if actions and "generateContent" not in actions:
            continue
        name = (model.name or "").removeprefix("models/")
        if name.startswith("gemini"):
            names.append(name)

    if not names:
        return [], f"{len(raw)} 件のモデルが返りましたが、文章生成に使える gemini 系が含まれていません。"

    unique = sorted(set(names), reverse=True)  # 名前の降順＝新しいバージョンが上
    unique.sort(key=lambda n: 1 if _is_preview(n) else 0)  # 安定版を先頭に（安定ソート）
    return unique, ""


def _redact(message: str, api_key: str) -> str:
    """エラー文にAPIキーが混ざっていた場合に伏せる。"""
    return message.replace(api_key, "***") if api_key else message


def _is_preview(name: str) -> bool:
    return any(tag in name for tag in ("preview", "exp", "tuning"))


def _build_config(cfg: AppConfig, system: str) -> types.GenerateContentConfig:
    kwargs: dict = {
        "system_instruction": system,
        "temperature": cfg.temperature,
    }
    if cfg.fast_mode and supports_thinking_off(cfg.model):
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    return types.GenerateContentConfig(**kwargs)


def _friendly(exc: Exception, api_key: str = "") -> str:
    """SDKの例外を、画面に出せる日本語メッセージに変換する。

    必ず `_redact()` を通す。SDKの例外文にはリクエストの詳細が載ることがあり、
    そこにAPIキーが混ざっていると `st.error` でそのまま画面に出てしまうため。
    """
    return _redact(_classify(exc), api_key)


def _classify(exc: Exception) -> str:
    """例外の内容から、原因ごとの案内文を選ぶ。"""
    msg = str(exc)
    lowered = msg.lower()
    if isinstance(exc, UnicodeEncodeError) or "ascii" in lowered and "codec" in lowered:
        return "APIキーに全角文字が混ざっています。半角英数字のキーだけを貼り付け直してください。"
    if "api key" in lowered or "api_key" in lowered or "unauthenticated" in lowered:
        return "APIキーが正しくないようです。サイドバーの設定を確認してください。"
    if "quota" in lowered or "resource_exhausted" in lowered or "429" in msg:
        return "APIの利用上限に達しました。しばらく待つか、モデルを flash 系に変えてお試しください。"
    if "not found" in lowered or "404" in msg:
        return (
            "指定したモデルがこのAPIキーでは使えません。"
            "サイドバーの「モデル」を🔄で再取得し、一覧に出たモデルを選び直してください。"
        )
    if _is_transient(exc):
        return (
            "Gemini側が混雑しています（自動で数回再試行しましたが復旧しませんでした）。"
            "1〜2分ほど置いて再実行するか、サイドバーで別のモデル（flash 系は比較的空いています）をお試しください。"
        )
    return f"生成に失敗しました: {msg}"


def _is_transient(exc: Exception) -> bool:
    """時間を置けば直る可能性が高い一時的な障害か。"""
    msg = str(exc)
    lowered = msg.lower()
    return (
        "503" in msg
        or "500" in msg
        or "unavailable" in lowered
        or "overloaded" in lowered
        or "high demand" in lowered
        or "internal error" in lowered
        or "deadline" in lowered
        or "timeout" in lowered
    )


MAX_RETRIES = 3  # 一時的な混雑（503など）に対する再試行回数


def _stream_with_retry(cfg: AppConfig, system: str, contents) -> Iterator[str]:
    """混雑時は待って再試行する。ただし出力が始まった後は再試行しない（重複を防ぐため）。"""
    for attempt in range(MAX_RETRIES):
        emitted = False
        try:
            chunks = _client(cfg.api_key).models.generate_content_stream(
                model=cfg.model,
                contents=contents,
                config=_build_config(cfg, system),
            )
            for chunk in chunks:
                if chunk.text:
                    emitted = True
                    yield chunk.text
            return
        except Exception as exc:  # SDK の例外はまとめて読みやすい形に変換する
            retryable = _is_transient(exc) and not emitted and attempt < MAX_RETRIES - 1
            if not retryable:
                raise GeminiError(_friendly(exc, cfg.api_key)) from exc
            time.sleep(2**attempt)  # 1秒 → 2秒 と間隔を広げる


def stream(cfg: AppConfig, system: str, prompt: str) -> Iterator[str]:
    """トークンを逐次返すジェネレータ。st.write_stream に渡して使う。"""
    if not cfg.has_key:
        raise GeminiError("APIキーが未設定です。")
    yield from _stream_with_retry(cfg, system, prompt)


def stream_chat(cfg: AppConfig, system: str, messages: list[dict]) -> Iterator[str]:
    """会話履歴つきのストリーミング生成。messages は {"role", "content"} のリスト。"""
    if not cfg.has_key:
        raise GeminiError("APIキーが未設定です。")
    contents = [
        types.Content(
            role="user" if m["role"] == "user" else "model",
            parts=[types.Part(text=m["content"])],
        )
        for m in messages
    ]
    yield from _stream_with_retry(cfg, system, contents)


def generate(cfg: AppConfig, system: str, prompt: str) -> str:
    """一括生成（ストリーミングなし）。"""
    if not cfg.has_key:
        raise GeminiError("APIキーが未設定です。")
    try:
        res = _client(cfg.api_key).models.generate_content(
            model=cfg.model,
            contents=prompt,
            config=_build_config(cfg, system),
        )
        return res.text or ""
    except Exception as exc:
        raise GeminiError(_friendly(exc, cfg.api_key)) from exc
