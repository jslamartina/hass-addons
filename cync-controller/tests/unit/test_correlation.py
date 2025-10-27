"""
Unit tests for correlation module.

Tests correlation ID generation, context management, and async context variable operations.
"""

from cync_controller.correlation import (
    correlation_context,
    ensure_correlation_id,
    generate_correlation_id,
    get_correlation_id,
    set_correlation_id,
)


class TestGenerateCorrelationId:
    """Tests for generate_correlation_id function"""

    def test_generates_unique_id(self):
        """Test that generate_correlation_id creates unique IDs"""
        id1 = generate_correlation_id()
        id2 = generate_correlation_id()

        assert id1 != id2
        assert isinstance(id1, str)
        assert isinstance(id2, str)

    def test_generates_valid_uuid_format(self):
        """Test that generated ID is valid UUID4 hex format"""
        corr_id = generate_correlation_id()

        # UUID4 hex should be 32 characters (no dashes)
        assert len(corr_id) == 32
        # Should be valid hex
        assert all(c in "0123456789abcdef" for c in corr_id)

    def test_multiple_generations_are_unique(self):
        """Test that multiple calls generate unique IDs"""
        ids = [generate_correlation_id() for _ in range(10)]
        unique_ids = set(ids)

        assert len(ids) == len(unique_ids)


class TestGetSetCorrelationId:
    """Tests for get_correlation_id and set_correlation_id functions"""

    def test_get_returns_none_initially(self):
        """Test that get_correlation_id returns None when not set"""
        # Clear any existing ID first
        set_correlation_id(None)

        result = get_correlation_id()

        assert result is None

    def test_set_and_get_correlation_id(self):
        """Test setting and getting correlation ID"""
        test_id = "test-correlation-id-12345"

        set_correlation_id(test_id)
        result = get_correlation_id()

        assert result == test_id

    def test_set_multiple_times(self):
        """Test that correlation ID can be overwritten"""
        id1 = "first-id"
        id2 = "second-id"

        set_correlation_id(id1)
        assert get_correlation_id() == id1

        set_correlation_id(id2)
        assert get_correlation_id() == id2

    def test_set_none_clears_id(self):
        """Test that setting None clears the correlation ID"""
        set_correlation_id("test-id")
        assert get_correlation_id() == "test-id"

        set_correlation_id(None)
        assert get_correlation_id() is None


class TestCorrelationContext:
    """Tests for correlation_context context manager"""

    def test_context_auto_generates_id(self):
        """Test that context manager auto-generates correlation ID"""
        # Clear any existing ID
        set_correlation_id(None)

        with correlation_context() as corr_id:
            assert corr_id is not None
            assert len(corr_id) == 32  # UUID4 hex format
            assert get_correlation_id() == corr_id

    def test_context_with_custom_id(self):
        """Test context manager with provided correlation ID"""
        test_id = "custom-correlation-id"

        with correlation_context(correlation_id=test_id) as corr_id:
            assert corr_id == test_id
            assert get_correlation_id() == test_id

    def test_context_restores_previous_id(self):
        """Test that context manager restores previous correlation ID after exit"""
        previous_id = "previous-id"
        set_correlation_id(previous_id)

        with correlation_context():
            # Inside context, should have new ID
            current_id = get_correlation_id()
            assert current_id != previous_id

        # After context exit, should restore previous ID
        assert get_correlation_id() == previous_id

    def test_context_restores_none_if_not_set(self):
        """Test that context manager restores None if no ID was previously set"""
        set_correlation_id(None)

        with correlation_context():
            # Inside context, should have new ID
            assert get_correlation_id() is not None

        # After exit, should restore None
        assert get_correlation_id() is None

    def test_context_with_auto_generate_false(self):
        """Test context manager with auto_generate=False"""
        set_correlation_id(None)

        with correlation_context(auto_generate=False) as corr_id:
            assert corr_id is None
            assert get_correlation_id() is None

    def test_nested_contexts(self):
        """Test nested correlation contexts"""
        set_correlation_id(None)

        with correlation_context(correlation_id="outer"):
            assert get_correlation_id() == "outer"

            with correlation_context(correlation_id="inner"):
                assert get_correlation_id() == "inner"

            # After inner context, should restore outer
            assert get_correlation_id() == "outer"

        # After all contexts, should be None
        assert get_correlation_id() is None


class TestEnsureCorrelationId:
    """Tests for ensure_correlation_id function"""

    def test_creates_id_if_missing(self):
        """Test that ensure_correlation_id creates ID if none exists"""
        set_correlation_id(None)

        result = ensure_correlation_id()

        assert result is not None
        assert len(result) == 32  # UUID4 hex format
        assert get_correlation_id() == result

    def test_returns_existing_id(self):
        """Test that ensure_correlation_id returns existing ID"""
        test_id = "existing-correlation-id"
        set_correlation_id(test_id)

        result = ensure_correlation_id()

        assert result == test_id

    def test_ensures_id_stays_in_context(self):
        """Test that ensure_correlation_id updates context variable"""
        set_correlation_id(None)
        assert get_correlation_id() is None

        corr_id = ensure_correlation_id()

        assert get_correlation_id() == corr_id
