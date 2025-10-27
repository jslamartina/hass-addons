"""
Unit tests for instrumentation module.

Tests timing decorators and performance tracking functionality.
"""

import asyncio
import time

import pytest

from cync_controller.instrumentation import measure_time, timed, timed_async


class TestMeasureTime:
    """Tests for measure_time function"""

    def test_measure_time_returns_milliseconds(self):
        """Test that measure_time returns elapsed time in milliseconds"""
        start = time.perf_counter()
        time.sleep(0.01)  # Sleep 10ms
        elapsed_ms = measure_time(start)

        # Should be approximately 10ms, allow 5-30ms tolerance for system variance
        assert 5 < elapsed_ms < 30

    def test_measure_time_precision(self):
        """Test that measure_time provides millisecond precision"""
        start = time.perf_counter()
        time.sleep(0.001)  # Sleep 1ms
        elapsed_ms = measure_time(start)

        # Result should be a float with reasonable precision
        assert isinstance(elapsed_ms, float)
        assert elapsed_ms > 0

    def test_measure_time_zero_elapsed(self):
        """Test measure_time with no elapsed time"""
        start = time.perf_counter()
        elapsed_ms = measure_time(start)

        # Should be very small but positive
        assert 0 <= elapsed_ms < 5


class TestTimedDecorator:
    """Tests for timed decorator (sync)"""

    def test_timed_decorator_wrapped_function_executes(self):
        """Test that timed decorator wraps function and it executes"""

        @timed("test_operation")
        def test_function():
            return "result"

        result = test_function()

        assert result == "result"

    def test_timed_decorator_preserves_function_name(self):
        """Test that timed decorator preserves original function name"""

        @timed()
        def my_function():
            pass

        assert my_function.__name__ == "my_function"

    def test_timed_decorator_with_arguments(self):
        """Test that timed decorator works with function arguments"""

        @timed("test_operation")
        def add(a, b):
            return a + b

        result = add(2, 3)

        assert result == 5

    def test_timed_decorator_with_kwargs(self):
        """Test that timed decorator works with keyword arguments"""

        @timed("test_operation")
        def greet(name, greeting="Hello"):
            return f"{greeting}, {name}!"

        result = greet("World", greeting="Hi")

        assert result == "Hi, World!"


class TestTimedAsyncDecorator:
    """Tests for timed_async decorator"""

    @pytest.mark.asyncio
    async def test_timed_async_decorator_preserved_function_name(self):
        """Test that timed_async decorator preserves function name"""

        @timed_async()
        async def my_async_function():
            pass

        assert my_async_function.__name__ == "my_async_function"

    @pytest.mark.asyncio
    async def test_timed_async_decorator_with_arguments(self):
        """Test that timed_async decorator works with async function arguments"""

        @timed_async("test_operation")
        async def async_add(a, b):
            await asyncio.sleep(0.001)
            return a + b

        result = await async_add(5, 7)

        assert result == 12


class TestTimingThresholds:
    """Tests for timing threshold warnings"""

    def test_timed_decorator_executes_successfully(self):
        """Test that timed decorator executes function correctly"""

        @timed("test_op")
        def test_function():
            return "success"

        result = test_function()

        assert result == "success"

    @pytest.mark.asyncio
    async def test_timed_async_decorator_executes_successfully(self):
        """Test that timed_async decorator executes async function correctly"""

        @timed_async("test_async_op")
        async def test_async_function():
            return "async_success"

        result = await test_async_function()

        assert result == "async_success"
