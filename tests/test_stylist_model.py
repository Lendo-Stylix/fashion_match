"""Tests for outfitmatch.stylist.model — load_stylist_model + generate_stylist_response.

All tests use mocking (no GPU required).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestBnbConfig:
    """_bnb_config: BitsAndBytesConfig construction."""

    def test_with_4bit(self):
        """_bnb_config(True) returns a BitsAndBytesConfig with nf4."""
        from outfitmatch.stylist.model import _bnb_config

        cfg = _bnb_config(True)
        assert cfg is not None
        assert cfg.load_in_4bit is True
        assert cfg.bnb_4bit_quant_type == "nf4"
        assert cfg.bnb_4bit_use_double_quant is True

    def test_without_4bit(self):
        """_bnb_config(False) returns None."""
        from outfitmatch.stylist.model import _bnb_config

        assert _bnb_config(False) is None


class TestLoadStylistModel:
    """load_stylist_model: wiring and defaults."""

    @patch("transformers.Qwen3VLForConditionalGeneration")
    @patch("transformers.AutoProcessor")
    @patch("peft.PeftModel")
    def test_load_with_adapter(self, mock_peft, mock_processor_cls, mock_qwen_cls):
        """load_stylist_model loads base + LoRA adapter."""
        from outfitmatch.stylist.model import load_stylist_model

        mock_model = MagicMock()
        mock_qwen_cls.from_pretrained.return_value = mock_model
        mock_peft_model = MagicMock()
        mock_peft.from_pretrained.return_value = mock_peft_model
        mock_processor = MagicMock()
        mock_processor_cls.from_pretrained.return_value = mock_processor

        model, processor = load_stylist_model(
            base_model="dummy/base",
            lora_checkpoint="dummy/adapter",
            load_in_4bit=True,
        )

        mock_qwen_cls.from_pretrained.assert_called_once()
        _, kwargs = mock_qwen_cls.from_pretrained.call_args
        assert kwargs["device_map"] == {"": 0}
        assert kwargs["torch_dtype"] == "auto"
        assert kwargs["quantization_config"] is not None
        assert kwargs["quantization_config"].load_in_4bit is True

        mock_peft.from_pretrained.assert_called_once_with(mock_model, "dummy/adapter")
        assert model is mock_peft_model
        assert processor is mock_processor

    @patch("transformers.Qwen3VLForConditionalGeneration")
    @patch("transformers.AutoProcessor")
    def test_load_without_adapter(self, mock_processor_cls, mock_qwen_cls):
        """load_stylist_model with lora_checkpoint=None skips PeftModel."""
        from outfitmatch.stylist.model import load_stylist_model

        mock_model = MagicMock()
        mock_qwen_cls.from_pretrained.return_value = mock_model
        mock_processor = MagicMock()
        mock_processor_cls.from_pretrained.return_value = mock_processor

        model, processor = load_stylist_model(
            base_model="dummy/base",
            lora_checkpoint=None,
            load_in_4bit=False,
        )
        assert model is mock_model
        assert processor is mock_processor
        mock_qwen_cls.from_pretrained.assert_called_once()
        _, kwargs = mock_qwen_cls.from_pretrained.call_args
        assert kwargs["quantization_config"] is None

    @patch("transformers.Qwen3VLForConditionalGeneration")
    @patch("transformers.AutoProcessor")
    def test_default_device_map(self, mock_processor_cls, mock_qwen_cls):
        """device_map defaults to {"": 0} when None."""
        from outfitmatch.stylist.model import load_stylist_model

        mock_model = MagicMock()
        mock_qwen_cls.from_pretrained.return_value = mock_model
        mock_processor = MagicMock()
        mock_processor_cls.from_pretrained.return_value = mock_processor

        load_stylist_model(
            base_model="dummy/base",
            lora_checkpoint=None,
            load_in_4bit=True,
            device_map=None,
        )
        _, kwargs = mock_qwen_cls.from_pretrained.call_args
        assert kwargs["device_map"] == {"": 0}


class TestGenerateStylistResponse:
    """generate_stylist_response: prompt building and generate call."""

    def test_generate_basic(self):
        """generate_stylist_response calls processor + model.generate."""
        from outfitmatch.stylist.model import generate_stylist_response

        mock_model = MagicMock()
        param = MagicMock()
        param.device = "cpu"
        mock_model.parameters.return_value = iter([param])
        mock_out = MagicMock()
        mock_out.__getitem__.return_value = MagicMock()
        mock_out[0].__getitem__.return_value = MagicMock()
        mock_out[0].shape = [1, 10]
        mock_model.generate.return_value = mock_out

        mock_processor = MagicMock()
        mock_processor.apply_chat_template.return_value = "system...user..."
        mock_inputs = {"input_ids": MagicMock(), "attention_mask": MagicMock()}
        mock_inputs["input_ids"].shape = [1, 5]
        mock_processor.return_value = mock_inputs
        mock_processor.decode.return_value = " Toi goi y outfit OF_00001."

        result = generate_stylist_response(
            model=mock_model,
            processor=mock_processor,
            user_prompt="Minh di lam van phong",
            temperature=0.0,
        )

        mock_processor.apply_chat_template.assert_called_once()
        assert mock_processor.call_args[1].get("images") is None
        assert "text" in mock_processor.call_args[1]

        mock_model.generate.assert_called_once()
        gen_kwargs = mock_model.generate.call_args[1]
        assert gen_kwargs["max_new_tokens"] == 512
        assert gen_kwargs["do_sample"] is False
        assert result == "Toi goi y outfit OF_00001."

    def test_custom_system_prompt(self):
        """generate_stylist_response uses custom system prompt."""
        from outfitmatch.stylist.model import generate_stylist_response

        mock_model = MagicMock()
        param = MagicMock()
        param.device = "cpu"
        mock_model.parameters.return_value = iter([param])
        mock_out = MagicMock()
        mock_out[0].shape = [1, 10]
        mock_out[0].__getitem__.return_value = MagicMock()
        mock_model.generate.return_value = mock_out

        mock_processor = MagicMock()
        mock_processor.apply_chat_template.return_value = "custom system..."
        mock_inputs = {"input_ids": MagicMock(), "attention_mask": MagicMock()}
        mock_inputs["input_ids"].shape = [1, 5]
        mock_processor.return_value = mock_inputs
        mock_processor.decode.return_value = " Ket qua."

        custom_prompt = "Custom system prompt test."
        result = generate_stylist_response(
            model=mock_model,
            processor=mock_processor,
            user_prompt="Test",
            system_prompt=custom_prompt,
            temperature=0.0,
        )
        messages = mock_processor.apply_chat_template.call_args[0][0]
        assert messages[0]["content"] == custom_prompt
        assert result == "Ket qua."


class TestDefaults:
    """Module-level defaults."""

    def test_default_system_prompt_nonempty(self):
        """DEFAULT_SYSTEM_PROMPT is a non-empty string."""
        from outfitmatch.stylist.model import DEFAULT_SYSTEM_PROMPT

        assert isinstance(DEFAULT_SYSTEM_PROMPT, str)
        assert len(DEFAULT_SYSTEM_PROMPT) > 20

    def test_default_paths(self):
        """DEFAULT_BASE_MODEL_DIR and DEFAULT_ADAPTER_DIR are Path objects."""
        from outfitmatch.stylist.model import DEFAULT_ADAPTER_DIR, DEFAULT_BASE_MODEL_DIR

        assert "unsloth--Qwen3-VL-8B-Thinking-bnb-4bit" in str(DEFAULT_BASE_MODEL_DIR)
        assert "outfitmatch-stylist-final-qwen3vl8b-thinking-lora" in str(DEFAULT_ADAPTER_DIR)
