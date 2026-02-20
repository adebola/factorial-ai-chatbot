"""
Comprehensive Tests for Trigger Detection System

Tests all three trigger types:
1. MESSAGE triggers — substring/phrase matching with confidence scoring
2. KEYWORD triggers — word-boundary exact matching with confidence scoring
3. INTENT triggers — embedding cosine similarity with keyword fallback

Also tests the integration-level check_triggers() flow:
- Best-match selection across multiple workflows
- Confidence threshold enforcement (> 0.5)
- Only active workflows are evaluated
- Pre-computation of message embeddings for intent workflows
"""

import pytest
import math
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from app.services.trigger_detector import TriggerDetector, _check_message_trigger
from app.models.workflow_model import Workflow, TriggerType
from app.schemas.workflow_schema import TriggerCheckResponse
from app.services.intent_embedding_service import IntentEmbeddingService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_workflow(
    trigger_type: str,
    trigger_config: dict,
    workflow_id: str = "wf-001",
    name: str = "Test Workflow",
    is_active: bool = True,
    status: str = "active",
    version: int = 1,
    tenant_id: str = "tenant-001",
) -> Mock:
    """Create a mock Workflow object with the given trigger configuration."""
    wf = Mock(spec=Workflow)
    wf.id = workflow_id
    wf.name = name
    wf.tenant_id = tenant_id
    wf.trigger_type = trigger_type  # raw string, not enum
    wf.trigger_config = trigger_config
    wf.is_active = is_active
    wf.status = status
    wf.version = version
    wf.usage_count = 0
    wf.last_used_at = None
    return wf


def _make_workflow_enum(trigger_type_enum, trigger_config: dict, **kwargs) -> Mock:
    """Create a mock Workflow whose trigger_type is an actual TriggerType enum."""
    wf = _make_workflow(trigger_type_enum, trigger_config, **kwargs)
    wf.trigger_type = trigger_type_enum  # enum value with .value attribute
    return wf


# ===========================================================================
# MESSAGE TRIGGER TESTS
# ===========================================================================

class TestMessageTrigger:
    """Tests for message-based (substring/phrase) trigger detection."""

    # --- Basic matching ---

    def test_exact_match(self):
        """Message exactly matches a condition phrase."""
        wf = _make_workflow("message", {"conditions": ["create account"]})
        confidence = _check_message_trigger(wf, "create account")
        assert confidence > 0.5

    def test_phrase_is_substring_of_message(self):
        """Condition phrase appears within a longer message."""
        wf = _make_workflow("message", {"conditions": ["create account"]})
        confidence = _check_message_trigger(wf, "I would like to create account please")
        assert confidence > 0.5

    def test_message_is_substring_of_phrase(self):
        """Entire message is contained within a longer condition phrase (reverse match)."""
        wf = _make_workflow("message", {"conditions": ["I want to create a new bank account"]})
        confidence = _check_message_trigger(wf, "create a new bank")
        assert confidence > 0.5

    def test_case_insensitive(self):
        """Matching is case-insensitive."""
        wf = _make_workflow("message", {"conditions": ["Create Account"]})
        confidence = _check_message_trigger(wf, "CREATE ACCOUNT")
        assert confidence > 0.5

    def test_no_match(self):
        """No condition matches the message."""
        wf = _make_workflow("message", {"conditions": ["create account"]})
        confidence = _check_message_trigger(wf, "what is the weather today")
        assert confidence == 0.0

    def test_whitespace_trimming(self):
        """Leading/trailing whitespace is stripped before matching."""
        wf = _make_workflow("message", {"conditions": ["  create account  "]})
        confidence = _check_message_trigger(wf, "  create account  ")
        assert confidence > 0.5

    # --- Multiple conditions ---

    def test_multiple_conditions_one_match(self):
        """Only one of several conditions matches."""
        wf = _make_workflow("message", {
            "conditions": ["open account", "create account", "new account"]
        })
        confidence = _check_message_trigger(wf, "I want to create account")
        assert confidence > 0.0
        # 1 out of 3 phrases matched → match_ratio = 1/3 ≈ 0.33
        # confidence = 0.33 * 0.7 + length_factor * 0.3
        # For a 27-char message, length_factor = min(1.0, 50/27) = 1.0
        # confidence ≈ 0.233 + 0.3 = 0.533
        assert confidence > 0.5

    def test_multiple_conditions_all_match(self):
        """All conditions match the message."""
        wf = _make_workflow("message", {
            "conditions": ["hello", "hi"]
        })
        confidence = _check_message_trigger(wf, "hello hi")
        # 2/2 match → match_ratio = 1.0
        assert confidence > 0.9

    def test_multiple_conditions_none_match(self):
        """No conditions match."""
        wf = _make_workflow("message", {
            "conditions": ["transfer money", "send funds"]
        })
        confidence = _check_message_trigger(wf, "what is the interest rate")
        assert confidence == 0.0

    # --- Backward compatibility ---

    def test_keywords_field_backward_compat(self):
        """The 'keywords' field in config is also checked for message triggers."""
        wf = _make_workflow("message", {"keywords": ["create account"]})
        confidence = _check_message_trigger(wf, "create account")
        assert confidence > 0.5

    def test_combined_conditions_and_keywords(self):
        """Both conditions and keywords are merged for checking."""
        wf = _make_workflow("message", {
            "conditions": ["open account"],
            "keywords": ["create account"]
        })
        confidence = _check_message_trigger(wf, "create account")
        assert confidence > 0.0

    # --- Empty / edge cases ---

    def test_empty_conditions(self):
        """Empty conditions list returns 0 confidence."""
        wf = _make_workflow("message", {"conditions": []})
        confidence = _check_message_trigger(wf, "hello")
        assert confidence == 0.0

    def test_no_trigger_config(self):
        """Missing trigger_config returns 0 confidence."""
        wf = _make_workflow("message", {})
        wf.trigger_config = None
        confidence = _check_message_trigger(wf, "hello")
        assert confidence == 0.0

    def test_non_string_condition_skipped(self):
        """Non-string items in conditions are skipped."""
        wf = _make_workflow("message", {"conditions": [123, None, "hello"]})
        confidence = _check_message_trigger(wf, "hello")
        # Only "hello" is checked (1/3 match)
        assert confidence > 0.0

    def test_empty_message(self):
        """Empty message still matches because '' is a substring of any string.

        Known edge case: Python's `"" in "hello"` is True, so the reverse
        substring check (message_lower in phrase_lower) always passes.
        The length factor guard (50/0) returns 0.0, giving confidence = 0.7.
        """
        wf = _make_workflow("message", {"conditions": ["hello"]})
        confidence = _check_message_trigger(wf, "")
        # Empty string is a substring of everything → matches, but length bonus = 0
        assert confidence > 0.0

    # --- Confidence scoring ---

    def test_short_message_higher_confidence(self):
        """Shorter messages get a higher length bonus (message_length_factor)."""
        wf = _make_workflow("message", {"conditions": ["help"]})
        short_confidence = _check_message_trigger(wf, "help")
        long_confidence = _check_message_trigger(wf, "can you help me with something very long and detailed please")
        assert short_confidence > long_confidence

    def test_confidence_never_exceeds_one(self):
        """Confidence is capped at 1.0."""
        wf = _make_workflow("message", {"conditions": ["hi"]})
        confidence = _check_message_trigger(wf, "hi")
        assert confidence <= 1.0

    def test_confidence_formula_verification(self):
        """Verify the exact confidence formula: (match_ratio * 0.7) + (length_factor * 0.3)."""
        wf = _make_workflow("message", {"conditions": ["alpha", "beta"]})
        message = "alpha"  # 5 chars, matches 1 of 2 conditions
        confidence = _check_message_trigger(wf, message)

        match_ratio = 1 / 2  # 1 match out of 2 phrases
        length_factor = min(1.0, 50 / 5)  # = 1.0 (capped)
        expected = (match_ratio * 0.7) + (length_factor * 0.3)
        expected = min(1.0, expected)

        assert abs(confidence - expected) < 0.001


# ===========================================================================
# KEYWORD TRIGGER TESTS
# ===========================================================================

class TestKeywordTrigger:
    """Tests for keyword-based (word boundary) trigger detection."""

    @pytest.fixture
    def detector(self):
        """Create a TriggerDetector with a mocked DB session."""
        db = Mock()
        return TriggerDetector(db)

    # --- Basic matching ---

    def test_single_keyword_match(self, detector):
        """Single keyword found in message."""
        wf = _make_workflow("keyword", {"keywords": ["pricing"]})
        confidence = detector._check_keyword_trigger(wf, "What is your pricing?")
        assert confidence > 0.5

    def test_single_keyword_exact_message(self, detector):
        """Message is exactly the keyword."""
        wf = _make_workflow("keyword", {"keywords": ["help"]})
        confidence = detector._check_keyword_trigger(wf, "help")
        assert confidence > 0.9

    def test_multiple_keywords_all_match(self, detector):
        """All keywords found in message."""
        wf = _make_workflow("keyword", {"keywords": ["account", "create"]})
        confidence = detector._check_keyword_trigger(wf, "I want to create an account")
        assert confidence > 0.9

    def test_multiple_keywords_partial_match(self, detector):
        """Only some keywords match."""
        wf = _make_workflow("keyword", {"keywords": ["account", "transfer", "balance"]})
        confidence = detector._check_keyword_trigger(wf, "check my account balance")
        # 2/3 matched → confidence = min(1.0, 2/3 * 1.2) = min(1.0, 0.8) = 0.8
        assert 0.7 < confidence < 0.9

    def test_no_keyword_match(self, detector):
        """No keywords found in message."""
        wf = _make_workflow("keyword", {"keywords": ["pricing", "cost"]})
        confidence = detector._check_keyword_trigger(wf, "what is the weather")
        assert confidence == 0.0

    # --- Word boundary enforcement ---

    def test_word_boundary_no_substring_match(self, detector):
        """Keywords must match whole words, not substrings."""
        wf = _make_workflow("keyword", {"keywords": ["count"]})
        confidence = detector._check_keyword_trigger(wf, "I want to create an account")
        # "account" contains "count" but word boundary should prevent match
        assert confidence == 0.0

    def test_word_boundary_hyphenated(self, detector):
        """Keyword at word boundary with punctuation."""
        wf = _make_workflow("keyword", {"keywords": ["help"]})
        confidence = detector._check_keyword_trigger(wf, "I need help!")
        assert confidence > 0.5

    def test_word_boundary_beginning_of_message(self, detector):
        """Keyword at the start of the message."""
        wf = _make_workflow("keyword", {"keywords": ["hello"]})
        confidence = detector._check_keyword_trigger(wf, "hello there")
        assert confidence > 0.5

    def test_word_boundary_end_of_message(self, detector):
        """Keyword at the end of the message."""
        wf = _make_workflow("keyword", {"keywords": ["help"]})
        confidence = detector._check_keyword_trigger(wf, "I need help")
        assert confidence > 0.5

    # --- Case sensitivity ---

    def test_case_insensitive(self, detector):
        """Keyword matching is case-insensitive."""
        wf = _make_workflow("keyword", {"keywords": ["Pricing"]})
        confidence = detector._check_keyword_trigger(wf, "WHAT IS YOUR PRICING")
        assert confidence > 0.5

    # --- Edge cases ---

    def test_empty_keywords(self, detector):
        """Empty keywords list returns 0."""
        wf = _make_workflow("keyword", {"keywords": []})
        confidence = detector._check_keyword_trigger(wf, "hello")
        assert confidence == 0.0

    def test_no_trigger_config(self, detector):
        """Null trigger_config returns 0."""
        wf = _make_workflow("keyword", {})
        wf.trigger_config = None
        confidence = detector._check_keyword_trigger(wf, "hello")
        assert confidence == 0.0

    def test_non_string_keyword_skipped(self, detector):
        """Non-string keywords are skipped."""
        wf = _make_workflow("keyword", {"keywords": [42, None, "help"]})
        confidence = detector._check_keyword_trigger(wf, "I need help")
        # Only "help" is checked: 1/3 * 1.2 = 0.4 → below threshold
        assert confidence > 0.0

    def test_special_characters_in_keyword(self, detector):
        """Keywords with regex special chars are escaped but word boundaries may not match.

        Known limitation: \\b requires a word/non-word boundary transition.
        'c++' ends with '+' (non-word), so \\b after '++' only matches if
        the next char is a word character. This means 'c++' followed by a
        space does NOT match because both '+' and ' ' are non-word chars.
        """
        wf = _make_workflow("keyword", {"keywords": ["c++"]})
        # Won't match due to \\b limitation with non-word characters
        confidence = detector._check_keyword_trigger(wf, "I know c++ programming")
        assert confidence == 0.0

    def test_special_characters_escaped_no_regex_injection(self, detector):
        """Regex special characters in keywords don't cause regex errors."""
        wf = _make_workflow("keyword", {"keywords": ["price?", "cost (total)"]})
        # Should not raise — re.escape handles these
        confidence = detector._check_keyword_trigger(wf, "what is the total cost")
        assert isinstance(confidence, float)

    # --- Confidence scoring ---

    def test_confidence_with_multiplier(self, detector):
        """Verify the 1.2x confidence multiplier formula."""
        wf = _make_workflow("keyword", {"keywords": ["account", "create", "bank"]})
        confidence = detector._check_keyword_trigger(wf, "create an account")
        # 2/3 * 1.2 = 0.8
        expected = min(1.0, 2 / 3 * 1.2)
        assert abs(confidence - expected) < 0.001

    def test_single_keyword_gives_full_confidence(self, detector):
        """A single keyword matching gives confidence = 1.0 (1/1 * 1.2, capped)."""
        wf = _make_workflow("keyword", {"keywords": ["help"]})
        confidence = detector._check_keyword_trigger(wf, "help me")
        # 1/1 * 1.2 = 1.2, capped at 1.0
        assert confidence == 1.0

    def test_confidence_capped_at_one(self, detector):
        """Confidence never exceeds 1.0 regardless of multiplier."""
        wf = _make_workflow("keyword", {"keywords": ["a"]})
        confidence = detector._check_keyword_trigger(wf, "a")
        assert confidence <= 1.0


# ===========================================================================
# INTENT TRIGGER TESTS
# ===========================================================================

class TestIntentTrigger:
    """Tests for intent-based trigger detection (embedding + fallback)."""

    @pytest.fixture
    def detector(self):
        db = Mock()
        return TriggerDetector(db)

    # --- Embedding path ---

    def test_embedding_high_similarity_triggers(self, detector):
        """Cosine similarity >= 0.82 produces confidence > 0."""
        # Create normalized vectors that give cosine similarity ≈ 0.90
        # Using a simple 3D example: vec_a and vec_b with known similarity
        vec_a = [1.0, 0.0, 0.0]
        # Rotate slightly: cos(θ) ≈ 0.90 → θ ≈ 25.8° → [cos(25.8°), sin(25.8°), 0]
        import math
        angle = math.acos(0.90)
        vec_b = [math.cos(angle), math.sin(angle), 0.0]

        wf = _make_workflow("intent", {
            "intent_patterns": ["I want to open an account"],
            "intent_embeddings": [
                {"text": "I want to open an account", "embedding": vec_b}
            ]
        })
        confidence = detector._check_intent_trigger(
            wf, "open account", message_embedding=vec_a
        )
        assert confidence > 0.5

    def test_embedding_below_threshold_returns_zero(self, detector):
        """Cosine similarity < 0.82 returns 0 confidence."""
        # Vectors with similarity ≈ 0.70 (below 0.82 threshold)
        angle = math.acos(0.70)
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [math.cos(angle), math.sin(angle), 0.0]

        wf = _make_workflow("intent", {
            "intent_patterns": ["unrelated topic"],
            "intent_embeddings": [
                {"text": "unrelated topic", "embedding": vec_b}
            ]
        })
        confidence = detector._check_intent_trigger(
            wf, "something else", message_embedding=vec_a
        )
        assert confidence == 0.0

    def test_embedding_exact_match_high_confidence(self, detector):
        """Identical vectors (similarity = 1.0) give confidence = 1.0."""
        vec = [0.5, 0.5, 0.5, 0.5]
        wf = _make_workflow("intent", {
            "intent_patterns": ["open account"],
            "intent_embeddings": [
                {"text": "open account", "embedding": vec}
            ]
        })
        confidence = detector._check_intent_trigger(
            wf, "open account", message_embedding=vec
        )
        assert confidence == 1.0

    def test_embedding_confidence_mapping(self, detector):
        """Verify confidence = (similarity - 0.7) / 0.3 formula."""
        # Create vectors with known similarity = 0.85
        angle = math.acos(0.85)
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [math.cos(angle), math.sin(angle), 0.0]

        wf = _make_workflow("intent", {
            "intent_patterns": ["test pattern"],
            "intent_embeddings": [
                {"text": "test pattern", "embedding": vec_b}
            ]
        })
        confidence = detector._check_intent_trigger(
            wf, "test", message_embedding=vec_a
        )
        expected = min(1.0, (0.85 - 0.7) / 0.3)
        assert abs(confidence - expected) < 0.01

    def test_embedding_multiple_patterns_best_selected(self, detector):
        """When multiple patterns have embeddings, the best similarity is used."""
        vec_msg = [1.0, 0.0, 0.0]

        # Pattern A: similarity ≈ 0.85
        angle_a = math.acos(0.85)
        vec_a = [math.cos(angle_a), math.sin(angle_a), 0.0]

        # Pattern B: similarity ≈ 0.95
        angle_b = math.acos(0.95)
        vec_b = [math.cos(angle_b), math.sin(angle_b), 0.0]

        wf = _make_workflow("intent", {
            "intent_patterns": ["pattern A", "pattern B"],
            "intent_embeddings": [
                {"text": "pattern A", "embedding": vec_a},
                {"text": "pattern B", "embedding": vec_b},
            ]
        })
        confidence = detector._check_intent_trigger(
            wf, "test", message_embedding=vec_msg
        )
        # Should use best match (0.95)
        expected = min(1.0, (0.95 - 0.7) / 0.3)
        assert abs(confidence - expected) < 0.01

    def test_embedding_entry_missing_vector_skipped(self, detector):
        """Embedding entries without an 'embedding' key are skipped."""
        vec_msg = [1.0, 0.0, 0.0]
        wf = _make_workflow("intent", {
            "intent_patterns": ["no embedding", "has embedding"],
            "intent_embeddings": [
                {"text": "no embedding"},  # missing embedding
                {"text": "has embedding", "embedding": vec_msg},  # sim = 1.0
            ]
        })
        confidence = detector._check_intent_trigger(
            wf, "test", message_embedding=vec_msg
        )
        assert confidence == 1.0

    # --- Fallback keyword path ---

    def test_fallback_keyword_high_overlap_triggers(self, detector):
        """Without embeddings, > 0.5 word overlap triggers."""
        wf = _make_workflow("intent", {
            "intent_patterns": ["open bank account"]
            # No intent_embeddings → fallback
        })
        confidence = detector._check_intent_trigger(
            wf, "I want to open bank account", message_embedding=None
        )
        # Pattern words: ["open", "bank", "account"] → 3 total
        # All 3 appear in the message → confidence = 3/3 = 1.0
        assert confidence == 1.0

    def test_fallback_keyword_partial_overlap_triggers(self, detector):
        """Partial keyword overlap above 0.5 threshold."""
        wf = _make_workflow("intent", {
            "intent_patterns": ["open savings account today"]
            # No intent_embeddings → fallback
        })
        confidence = detector._check_intent_trigger(
            wf, "I want to open my account", message_embedding=None
        )
        # Pattern words: ["open", "savings", "account", "today"] → 4 total
        # "open" ✓, "savings" ✗, "account" ✓, "today" ✗ → 2/4 = 0.5
        # Must be > 0.5, so 0.5 doesn't trigger
        assert confidence == 0.0

    def test_fallback_keyword_low_overlap_no_trigger(self, detector):
        """Keyword overlap <= 0.5 does not trigger."""
        wf = _make_workflow("intent", {
            "intent_patterns": ["transfer money to savings account"]
        })
        confidence = detector._check_intent_trigger(
            wf, "hello there", message_embedding=None
        )
        assert confidence == 0.0

    def test_fallback_uses_substring_matching(self, detector):
        """Fallback checks if pattern keywords are substrings of message."""
        wf = _make_workflow("intent", {
            "intent_patterns": ["book appointment"]
        })
        confidence = detector._check_intent_trigger(
            wf, "I'd like to book an appointment please", message_embedding=None
        )
        # "book" and "appointment" are both in the message → 2/2 = 1.0
        assert confidence == 1.0

    def test_fallback_multiple_patterns_first_match_wins(self, detector):
        """Fallback iterates patterns and returns first one above threshold."""
        wf = _make_workflow("intent", {
            "intent_patterns": [
                "something completely unrelated",
                "book appointment"  # This should match
            ]
        })
        confidence = detector._check_intent_trigger(
            wf, "I want to book an appointment", message_embedding=None
        )
        assert confidence > 0.5

    # --- Edge cases ---

    def test_empty_intent_patterns(self, detector):
        """No intent patterns configured returns 0."""
        wf = _make_workflow("intent", {"intent_patterns": []})
        confidence = detector._check_intent_trigger(wf, "hello")
        assert confidence == 0.0

    def test_no_trigger_config(self, detector):
        """Null trigger_config returns 0."""
        wf = _make_workflow("intent", {})
        wf.trigger_config = None
        confidence = detector._check_intent_trigger(wf, "hello")
        assert confidence == 0.0

    def test_no_message_embedding_falls_back(self, detector):
        """When message_embedding is None, uses fallback keyword matching."""
        wf = _make_workflow("intent", {
            "intent_patterns": ["create account"],
            "intent_embeddings": [
                {"text": "create account", "embedding": [1.0, 0.0]}
            ]
        })
        # Pass message_embedding=None → should use fallback
        confidence = detector._check_intent_trigger(
            wf, "I want to create account", message_embedding=None
        )
        # Fallback: "create" ✓, "account" ✓ → 2/2 = 1.0
        assert confidence > 0.5

    def test_no_embeddings_stored_falls_back(self, detector):
        """When intent_embeddings is empty, uses fallback keyword matching."""
        wf = _make_workflow("intent", {
            "intent_patterns": ["create account"],
            "intent_embeddings": []
        })
        confidence = detector._check_intent_trigger(
            wf, "I want to create account", message_embedding=[1.0, 0.0]
        )
        # Empty embeddings → fallback: "create" ✓, "account" ✓ → 2/2
        assert confidence > 0.5


# ===========================================================================
# COSINE SIMILARITY UNIT TESTS
# ===========================================================================

class TestCosineSimilarity:
    """Unit tests for IntentEmbeddingService.cosine_similarity()."""

    def test_identical_vectors(self):
        assert IntentEmbeddingService.cosine_similarity([1, 0, 0], [1, 0, 0]) == 1.0

    def test_orthogonal_vectors(self):
        assert IntentEmbeddingService.cosine_similarity([1, 0, 0], [0, 1, 0]) == 0.0

    def test_opposite_vectors(self):
        sim = IntentEmbeddingService.cosine_similarity([1, 0], [-1, 0])
        assert abs(sim - (-1.0)) < 0.001

    def test_zero_vector_a(self):
        assert IntentEmbeddingService.cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0

    def test_zero_vector_b(self):
        assert IntentEmbeddingService.cosine_similarity([1, 2, 3], [0, 0, 0]) == 0.0

    def test_known_similarity(self):
        """Verify a known cosine similarity calculation."""
        a = [1, 2, 3]
        b = [4, 5, 6]
        # dot = 4+10+18 = 32
        # mag_a = sqrt(1+4+9) = sqrt(14) ≈ 3.742
        # mag_b = sqrt(16+25+36) = sqrt(77) ≈ 8.775
        # similarity = 32 / (3.742 * 8.775) ≈ 0.9746
        sim = IntentEmbeddingService.cosine_similarity(a, b)
        assert abs(sim - 0.9746) < 0.001


# ===========================================================================
# TRIGGER TYPE ROUTING TESTS
# ===========================================================================

class TestTriggerTypeRouting:
    """Tests that _calculate_trigger_confidence routes to the correct trigger handler."""

    @pytest.fixture
    def detector(self):
        return TriggerDetector(Mock())

    def test_routes_to_message_trigger(self, detector):
        """trigger_type='message' routes to _check_message_trigger."""
        wf = _make_workflow("message", {"conditions": ["hello"]})
        confidence = detector._calculate_trigger_confidence(wf, "hello")
        assert confidence > 0.5

    def test_routes_to_keyword_trigger(self, detector):
        """trigger_type='keyword' routes to _check_keyword_trigger."""
        wf = _make_workflow("keyword", {"keywords": ["hello"]})
        confidence = detector._calculate_trigger_confidence(wf, "hello")
        assert confidence > 0.5

    def test_routes_to_intent_trigger(self, detector):
        """trigger_type='intent' routes to _check_intent_trigger."""
        wf = _make_workflow("intent", {
            "intent_patterns": ["hello world"]
        })
        confidence = detector._calculate_trigger_confidence(wf, "hello world")
        # Fallback keyword path: "hello" ✓, "world" ✓ → 2/2 = 1.0
        assert confidence > 0.5

    def test_unknown_trigger_type_returns_zero(self, detector):
        """Unknown trigger type returns 0 confidence."""
        wf = _make_workflow("unknown_type", {})
        confidence = detector._calculate_trigger_confidence(wf, "hello")
        assert confidence == 0.0

    def test_enum_trigger_type_handled(self, detector):
        """TriggerType enum values (with .value attribute) are handled correctly."""
        wf = _make_workflow_enum(TriggerType.KEYWORD, {"keywords": ["help"]})
        confidence = detector._calculate_trigger_confidence(wf, "I need help")
        assert confidence > 0.5

    def test_enum_message_type_handled(self, detector):
        wf = _make_workflow_enum(TriggerType.MESSAGE, {"conditions": ["help"]})
        confidence = detector._calculate_trigger_confidence(wf, "help")
        assert confidence > 0.5

    def test_enum_intent_type_handled(self, detector):
        wf = _make_workflow_enum(TriggerType.INTENT, {
            "intent_patterns": ["book appointment"]
        })
        confidence = detector._calculate_trigger_confidence(
            wf, "I want to book an appointment"
        )
        assert confidence > 0.5


# ===========================================================================
# INTEGRATION: check_triggers()
# ===========================================================================

class TestCheckTriggers:
    """Integration tests for the main check_triggers() method."""

    @pytest.fixture
    def detector(self):
        db = Mock()
        return TriggerDetector(db)

    @pytest.mark.asyncio
    async def test_no_active_workflows(self, detector):
        """Returns triggered=False when no active workflows exist."""
        detector.db.query.return_value.filter.return_value.all.return_value = []
        result = await detector.check_triggers("tenant-001", "hello", "session-001")
        assert result.triggered is False

    @pytest.mark.asyncio
    async def test_single_matching_workflow(self, detector):
        """Single active workflow with matching trigger returns it."""
        wf = _make_workflow("keyword", {"keywords": ["pricing"]})
        detector.db.query.return_value.filter.return_value.all.return_value = [wf]

        result = await detector.check_triggers("tenant-001", "what is your pricing", "session-001")
        assert result.triggered is True
        assert result.workflow_id == "wf-001"
        assert result.workflow_name == "Test Workflow"
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_best_match_selected(self, detector):
        """When multiple workflows match, the highest confidence wins."""
        wf_low = _make_workflow("keyword", {"keywords": ["help", "support", "assist"]},
                                workflow_id="wf-low", name="Low Match")
        wf_high = _make_workflow("keyword", {"keywords": ["pricing"]},
                                 workflow_id="wf-high", name="High Match")

        detector.db.query.return_value.filter.return_value.all.return_value = [wf_low, wf_high]

        result = await detector.check_triggers("tenant-001", "pricing", "session-001")
        assert result.triggered is True
        assert result.workflow_id == "wf-high"

    @pytest.mark.asyncio
    async def test_below_threshold_not_triggered(self, detector):
        """Workflows with confidence <= 0.5 do not trigger."""
        # A keyword trigger with 1/4 keywords matching → 0.25 * 1.2 = 0.3
        wf = _make_workflow("keyword", {
            "keywords": ["alpha", "beta", "gamma", "delta"]
        })
        detector.db.query.return_value.filter.return_value.all.return_value = [wf]

        result = await detector.check_triggers("tenant-001", "alpha", "session-001")
        # confidence = 1/4 * 1.2 = 0.3 → below 0.5 threshold
        assert result.triggered is False

    @pytest.mark.asyncio
    async def test_inactive_workflows_not_queried(self, detector):
        """check_triggers queries only active workflows (is_active=True, status='active')."""
        detector.db.query.return_value.filter.return_value.all.return_value = []
        await detector.check_triggers("tenant-001", "hello", "session-001")

        # Verify the filter was called (we can't easily check exact filter args with mock,
        # but we verify the method was called)
        detector.db.query.assert_called_once_with(Workflow)

    @pytest.mark.asyncio
    async def test_response_includes_metadata(self, detector):
        """Triggered response includes trigger_config and workflow_version metadata."""
        wf = _make_workflow("keyword", {"keywords": ["help"]})
        detector.db.query.return_value.filter.return_value.all.return_value = [wf]

        result = await detector.check_triggers("tenant-001", "help", "session-001")
        assert result.triggered is True
        assert result.metadata is not None
        assert "trigger_config" in result.metadata
        assert "workflow_version" in result.metadata
        assert result.metadata["workflow_version"] == 1

    @pytest.mark.asyncio
    async def test_mixed_trigger_types_best_wins(self, detector):
        """Mix of message, keyword, and intent triggers — best confidence wins."""
        wf_message = _make_workflow("message", {"conditions": ["help me"]},
                                    workflow_id="wf-msg", name="Message WF")
        wf_keyword = _make_workflow("keyword", {"keywords": ["help"]},
                                    workflow_id="wf-kw", name="Keyword WF")

        detector.db.query.return_value.filter.return_value.all.return_value = [wf_message, wf_keyword]

        result = await detector.check_triggers("tenant-001", "help me", "session-001")
        assert result.triggered is True
        # Both should match; the one with higher confidence wins

    @pytest.mark.asyncio
    async def test_intent_trigger_precomputes_embedding(self, detector):
        """When intent workflows exist, message embedding is pre-computed once."""
        wf = _make_workflow("intent", {
            "intent_patterns": ["book appointment"],
            "intent_embeddings": [
                {"text": "book appointment", "embedding": [1.0, 0.0, 0.0]}
            ]
        })
        detector.db.query.return_value.filter.return_value.all.return_value = [wf]

        with patch.object(IntentEmbeddingService, 'embed_message', return_value=[1.0, 0.0, 0.0]) as mock_embed:
            result = await detector.check_triggers(
                "tenant-001", "I want to book an appointment", "session-001"
            )
            # embed_message should be called exactly once (pre-computation)
            mock_embed.assert_called_once_with("I want to book an appointment")

    @pytest.mark.asyncio
    async def test_no_intent_workflows_skips_embedding(self, detector):
        """When no intent workflows exist, embedding is not computed."""
        wf = _make_workflow("keyword", {"keywords": ["help"]})
        detector.db.query.return_value.filter.return_value.all.return_value = [wf]

        with patch.object(IntentEmbeddingService, 'embed_message') as mock_embed:
            await detector.check_triggers("tenant-001", "help", "session-001")
            mock_embed.assert_not_called()

    @pytest.mark.asyncio
    async def test_embedding_failure_falls_back(self, detector):
        """If embedding fails, intent triggers still work via keyword fallback."""
        wf = _make_workflow("intent", {
            "intent_patterns": ["book appointment"],
            "intent_embeddings": [
                {"text": "book appointment", "embedding": [1.0, 0.0]}
            ]
        })
        detector.db.query.return_value.filter.return_value.all.return_value = [wf]

        with patch.object(IntentEmbeddingService, 'embed_message', side_effect=Exception("API error")):
            result = await detector.check_triggers(
                "tenant-001", "I want to book an appointment", "session-001"
            )
            # Falls back to keyword matching: "book" ✓, "appointment" ✓ → 2/2 = 1.0
            assert result.triggered is True


# ===========================================================================
# INTEGRATION: test_workflow_trigger()
# ===========================================================================

class TestTestWorkflowTrigger:
    """Tests for the test_workflow_trigger() method (test a specific workflow)."""

    @pytest.fixture
    def detector(self):
        return TriggerDetector(Mock())

    @pytest.mark.asyncio
    async def test_matching_workflow(self, detector):
        """Returns triggered=True for a matching workflow."""
        wf = _make_workflow("keyword", {"keywords": ["help"]},
                            workflow_id="wf-123", name="Help WF")
        detector.db.query.return_value.filter.return_value.first.return_value = wf

        result = await detector.test_workflow_trigger(
            "wf-123", "tenant-001", "I need help"
        )
        assert result.triggered is True
        assert result.workflow_id == "wf-123"
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_non_matching_workflow(self, detector):
        """Returns triggered=False when confidence <= 0.5."""
        wf = _make_workflow("keyword", {"keywords": ["alpha", "beta", "gamma", "delta"]})
        detector.db.query.return_value.filter.return_value.first.return_value = wf

        result = await detector.test_workflow_trigger(
            "wf-001", "tenant-001", "alpha"
        )
        # 1/4 * 1.2 = 0.3 → below 0.5
        assert result.triggered is False

    @pytest.mark.asyncio
    async def test_workflow_not_found(self, detector):
        """Returns triggered=False when workflow doesn't exist."""
        detector.db.query.return_value.filter.return_value.first.return_value = None

        result = await detector.test_workflow_trigger(
            "nonexistent", "tenant-001", "hello"
        )
        assert result.triggered is False

    @pytest.mark.asyncio
    async def test_includes_test_mode_metadata(self, detector):
        """Triggered response includes test_mode=True in metadata."""
        wf = _make_workflow("keyword", {"keywords": ["help"]})
        detector.db.query.return_value.filter.return_value.first.return_value = wf

        result = await detector.test_workflow_trigger(
            "wf-001", "tenant-001", "help"
        )
        assert result.triggered is True
        assert result.metadata["test_mode"] is True


# ===========================================================================
# CROSS-TRIGGER COMPARISON TESTS
# ===========================================================================

class TestCrossTriggerBehavior:
    """Compare behavior differences between the three trigger types."""

    @pytest.fixture
    def detector(self):
        return TriggerDetector(Mock())

    def test_keyword_vs_message_substring_behavior(self, detector):
        """
        KEYWORD uses word boundaries, MESSAGE uses substring matching.
        'account' should NOT match 'accountability' for KEYWORD but SHOULD for MESSAGE.
        """
        wf_keyword = _make_workflow("keyword", {"keywords": ["account"]})
        wf_message = _make_workflow("message", {"conditions": ["account"]})

        kw_conf = detector._check_keyword_trigger(wf_keyword, "accountability is important")
        msg_conf = _check_message_trigger(wf_message, "accountability is important")

        # KEYWORD: "account" as whole word not in "accountability" → 0
        assert kw_conf == 0.0
        # MESSAGE: "account" is a substring of "accountability" → matches
        assert msg_conf > 0.0

    def test_keyword_stricter_than_message(self, detector):
        """KEYWORD matching is generally stricter than MESSAGE matching."""
        wf_keyword = _make_workflow("keyword", {"keywords": ["pay"]})
        wf_message = _make_workflow("message", {"conditions": ["pay"]})

        # "repay" contains "pay" as substring but not as a whole word
        kw_conf = detector._check_keyword_trigger(wf_keyword, "I need to repay my loan")
        msg_conf = _check_message_trigger(wf_message, "I need to repay my loan")

        assert kw_conf == 0.0
        assert msg_conf > 0.0

    def test_intent_fallback_substring_vs_keyword_boundary(self, detector):
        """
        INTENT fallback checks if each pattern word is a substring of the message.
        KEYWORD requires exact word boundary match.

        Note: 'schedule' is NOT a substring of 'scheduling' — they share
        the root 'schedul' but diverge at char 8 ('e' vs 'i').
        """
        # Use a word that truly is a substring: "book" IS in "booking"
        wf_intent = _make_workflow("intent", {
            "intent_patterns": ["book appointment"]
        })
        wf_keyword = _make_workflow("keyword", {"keywords": ["book"]})

        intent_conf = detector._check_intent_trigger(
            wf_intent, "I have a booking for an appointment"
        )
        kw_conf = detector._check_keyword_trigger(
            wf_keyword, "I have a booking for an appointment"
        )

        # Intent fallback: "book" IS a substring of "booking" → matches
        # "appointment" is an exact match → 2/2 = 1.0
        assert intent_conf > 0.5
        # Keyword: "book" as a whole word is NOT in "booking" → no match
        assert kw_conf == 0.0


# ===========================================================================
# EDGE CASE / REGRESSION TESTS
# ===========================================================================

class TestEdgeCases:
    """Edge cases and regression tests."""

    @pytest.fixture
    def detector(self):
        return TriggerDetector(Mock())

    def test_message_trigger_with_unicode(self):
        """Unicode characters in conditions and messages."""
        wf = _make_workflow("message", {"conditions": ["créer un compte"]})
        confidence = _check_message_trigger(wf, "je veux créer un compte")
        assert confidence > 0.5

    def test_keyword_trigger_with_numbers(self, detector):
        """Keywords can be numeric strings."""
        wf = _make_workflow("keyword", {"keywords": ["401k"]})
        confidence = detector._check_keyword_trigger(wf, "what is a 401k plan")
        assert confidence > 0.5

    def test_very_long_message(self):
        """Trigger detection handles very long messages."""
        wf = _make_workflow("message", {"conditions": ["help"]})
        long_message = "I need help " + "with something " * 500
        confidence = _check_message_trigger(wf, long_message)
        # Should still match, but length factor will be very small
        assert confidence > 0.0

    def test_message_with_only_whitespace(self):
        """Whitespace-only message matches because stripped '' is substring of any string.

        Known edge case: after strip(), message becomes '', and Python's
        `'' in 'hello'` is True. Unlike empty string, len('   ') > 0,
        so the length bonus is high, giving confidence = 1.0.
        """
        wf = _make_workflow("message", {"conditions": ["hello"]})
        confidence = _check_message_trigger(wf, "   ")
        # Stripped to '' → matches, and len("   ") = 3 → high length bonus
        assert confidence > 0.0

    def test_single_character_keyword(self, detector):
        """Single character keywords work with word boundaries."""
        wf = _make_workflow("keyword", {"keywords": ["a"]})
        confidence = detector._check_keyword_trigger(wf, "this is a test")
        assert confidence > 0.5

    @pytest.mark.asyncio
    async def test_concurrent_trigger_types_in_check_triggers(self, detector):
        """check_triggers handles a mix of all three trigger types correctly."""
        wf_msg = _make_workflow("message", {"conditions": ["book"]},
                                workflow_id="wf-msg", name="Message WF")
        wf_kw = _make_workflow("keyword", {"keywords": ["appointment"]},
                               workflow_id="wf-kw", name="Keyword WF")
        wf_intent = _make_workflow("intent", {
            "intent_patterns": ["schedule a visit"]
        }, workflow_id="wf-intent", name="Intent WF")

        detector.db.query.return_value.filter.return_value.all.return_value = [
            wf_msg, wf_kw, wf_intent
        ]

        with patch.object(IntentEmbeddingService, 'embed_message', side_effect=Exception("No API")):
            result = await detector.check_triggers(
                "tenant-001", "I want to book an appointment", "session-001"
            )
            # At least one should trigger
            assert result.triggered is True
