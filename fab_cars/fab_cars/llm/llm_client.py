# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMResult:
	text: str
	total_tokens: int | None = None


def _get_llm_settings_doc():
	"""
	Load singleton `FC LLM Settings` when running inside Frappe.

	Returns None if the doctype is not installed yet or Frappe is not bootstrapped.
	"""
	try:
		import frappe

		if not getattr(frappe, "db", None):
			return None
		if not frappe.db.exists("DocType", "FC LLM Settings"):
			return None
		return frappe.get_single("FC LLM Settings")
	except Exception:
		return None


def _str_or_none(val) -> str | None:
	if val is None:
		return None
	s = str(val).strip()
	return s if s else None


def _anthropic_api_key() -> str | None:
	doc = _get_llm_settings_doc()
	if doc:
		try:
			k = doc.get_password("anthropic_api_key")
			if k:
				return k
		except Exception:
			pass
	return None


def _openai_api_key() -> str | None:
	doc = _get_llm_settings_doc()
	if doc:
		try:
			k = doc.get_password("openai_api_key")
			if k:
				return k
		except Exception:
			pass
	return None


def _get_provider() -> str:
	"""
	Resolve LLM provider.

	Uses only `FC LLM Settings.llm_provider` (doctype-only configuration).
	"""
	doc = _get_llm_settings_doc()
	if not doc:
		raise ValueError("Missing `FC LLM Settings` singleton. Create it to configure AI providers.")

	raw = (_str_or_none(getattr(doc, "llm_provider", None)) or "").lower()
	if raw in ("anthropic", "openai"):
		return raw

	# If provider isn't set, try key-based inference (still doctype-only).
	if _openai_api_key():
		return "openai"
	if _anthropic_api_key():
		return "anthropic"

	raise ValueError(
		"`FC LLM Settings.llm_provider` must be set to `Anthropic` or `OpenAI`, or an API key must be configured."
	)


def _model_from_settings(*, doc_attr: str, default: str) -> str:
	doc = _get_llm_settings_doc()
	if doc:
		v = _str_or_none(getattr(doc, doc_attr, None))
		if v:
			return v
	return default


def _openai_base_url() -> str:
	doc = _get_llm_settings_doc()
	if not doc:
		raise ValueError("Missing `FC LLM Settings` singleton.")
	v = _str_or_none(getattr(doc, "openai_base_url", None))
	if not v:
		raise ValueError("`FC LLM Settings.openai_base_url` is required.")
	return v.rstrip("/")


def _openai_timeout_seconds() -> float:
	doc = _get_llm_settings_doc()
	if not doc:
		raise ValueError("Missing `FC LLM Settings` singleton.")
	try:
		t = getattr(doc, "openai_timeout_seconds", None)
		if t is not None and int(t) > 0:
			return float(int(t))
	except Exception:
		pass
	raise ValueError("`FC LLM Settings.openai_timeout_seconds` must be a positive integer.")


def _parse_token_usage_openai(usage: dict | None) -> int | None:
	if not usage or not isinstance(usage, dict):
		return None
	try:
		total = usage.get("total_tokens")
		return int(total) if total is not None else None
	except (TypeError, ValueError):
		return None


def llm_invoke_text(*, prompt: str, model: str, max_tokens: int) -> LLMResult:
	"""
	Provider-agnostic LLM invocation.

	Prompts are sent as a single user message; callers are responsible for JSON-only instructions.

	Secrets and models are configured via the `FC LLM Settings` singleton only.
	"""

	provider = _get_provider()

	if provider == "anthropic":
		from anthropic import Anthropic

		api_key = _anthropic_api_key()
		if not api_key:
			raise ValueError("Missing Anthropic API key in `FC LLM Settings.anthropic_api_key`")

		client = Anthropic(api_key=api_key)
		response = client.messages.create(
			model=model,
			max_tokens=max_tokens,
			messages=[{"role": "user", "content": prompt}],
		)
		blocks = getattr(response, "content", None) or []
		if not blocks:
			raise RuntimeError("Anthropic returned empty content")
		first = blocks[0]
		text_attr = getattr(first, "text", None)
		if text_attr is None:
			raise RuntimeError("Anthropic response missing text block")
		text = str(text_attr).strip()

		total_tokens = None
		usage = getattr(response, "usage", None)
		if usage:
			input_tokens = getattr(usage, "input_tokens", None)
			output_tokens = getattr(usage, "output_tokens", None)
			if isinstance(usage, dict):
				input_tokens = input_tokens or usage.get("input_tokens")
				output_tokens = output_tokens or usage.get("output_tokens")
			try:
				if input_tokens is not None or output_tokens is not None:
					total_tokens = int(input_tokens or 0) + int(output_tokens or 0)
			except Exception:
				total_tokens = None

		return LLMResult(text=text, total_tokens=total_tokens)

	if provider == "openai":
		api_key = _openai_api_key()
		if not api_key:
			raise ValueError("Missing OpenAI API key in `FC LLM Settings.openai_api_key`")

		base_url = _openai_base_url()
		endpoint = f"{base_url}/v1/chat/completions"
		timeout_s = _openai_timeout_seconds()

		body = {
			"model": model,
			"messages": [{"role": "user", "content": prompt}],
			"max_tokens": max_tokens,
			"temperature": 0,
		}

		req = urllib.request.Request(
			endpoint,
			data=json.dumps(body).encode("utf-8"),
			headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
		)
		try:
			with urllib.request.urlopen(req, timeout=timeout_s) as resp:
				raw = resp.read().decode("utf-8", errors="replace")
		except urllib.error.HTTPError as e:
			try:
				error_body = e.read().decode("utf-8", errors="replace")
			except Exception:
				error_body = str(e)
			raise RuntimeError(f"OpenAI API error: {e.code} {error_body}") from e

		try:
			data = json.loads(raw)
		except json.JSONDecodeError as e:
			raise RuntimeError(f"OpenAI returned invalid JSON: {raw[:500]}") from e
		choices = data.get("choices")
		if not isinstance(choices, list) or not choices:
			raise RuntimeError("OpenAI response missing choices")
		msg = choices[0].get("message") if isinstance(choices[0], dict) else None
		text = (msg.get("content") or "") if isinstance(msg, dict) else ""

		usage = data.get("usage")
		total_tokens = _parse_token_usage_openai(usage if isinstance(usage, dict) else None)
		return LLMResult(text=text.strip(), total_tokens=total_tokens)

	raise ValueError(f"Unsupported llm_provider: {provider!r}")


def get_default_llm_models() -> dict[str, str]:
	"""Classifier / extractor model IDs from `FC LLM Settings` (doctype-only)."""

	provider = _get_provider()

	if provider == "anthropic":
		default_model = _model_from_settings(
			doc_attr="anthropic_extractor_model",
			default="claude-4-sonnet-20250514",
		)
		classifier_model = _model_from_settings(
			doc_attr="anthropic_classifier_model",
			default=default_model,
		)
	else:
		default_model = _model_from_settings(
			doc_attr="openai_extractor_model",
			default="gpt-4o-mini",
		)
		classifier_model = _model_from_settings(
			doc_attr="openai_classifier_model",
			default=default_model,
		)

	return {"classifier": classifier_model, "extractor": default_model}
