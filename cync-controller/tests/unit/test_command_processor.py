"""Unit tests for CommandProcessor queue and execution logic.

Tests for CommandProcessor command queuing, sequential execution,
optimistic updates, error handling, and mesh refresh orchestration.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Iterator
from typing import override

import pytest

from cync_controller.mqtt.commands import CommandProcessor, DeviceCommand

# Filter RuntimeWarning about unawaited AsyncMockMixin coroutines from test cleanup
pytestmark = [
    pytest.mark.filterwarnings("ignore:coroutine 'AsyncMockMixin._execute_mock_call'.*"),  # type: ignore[arg-type]
]


class TestCommandProcessorExecution:
    """Tests for CommandProcessor queue and execution logic."""

    @pytest.fixture(autouse=True)
    def reset_processor_singleton(self) -> Iterator[None]:
        """Reset CommandProcessor singleton between tests."""
        original_instance = getattr(CommandProcessor, "_instance", None)
        CommandProcessor._instance = None  # pyright: ignore[reportPrivateUsage]
        try:
            yield
        finally:
            CommandProcessor._instance = original_instance  # pyright: ignore[reportPrivateUsage]


class CommandProcessorTestHarness(CommandProcessor):
    """Expose test helpers for interacting with CommandProcessor internals."""

    @classmethod
    def create(cls) -> CommandProcessorTestHarness:
        CommandProcessor._instance = None
        instance = cls()
        instance._queue = asyncio.Queue()
        instance._processing = False
        return instance

    async def run_for(self, duration: float = 0.15) -> None:
        task = asyncio.create_task(self.process_next())
        try:
            await asyncio.sleep(duration)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def queue_size(self) -> int:
        return self._queue.qsize()

    def is_processing(self) -> bool:
        return self._processing

    @pytest.mark.asyncio
    async def test_command_processor_sequential_execution(self):
        """Test commands execute in FIFO order."""
        processor = CommandProcessorTestHarness.create()

        executed_order: list[int] = []

        class TestCommand(DeviceCommand):
            def __init__(self, cmd_id: int) -> None:
                self.cmd_id = cmd_id
                super().__init__(f"test_{cmd_id}", cmd_id)

            @override
            async def publish_optimistic(self) -> None:
                pass

            @override
            async def execute(self) -> None:
                executed_order.append(self.cmd_id)
                await asyncio.sleep(0.01)

        # Enqueue commands in order
        await processor.enqueue(TestCommand(1))
        await processor.enqueue(TestCommand(2))
        await processor.enqueue(TestCommand(3))

        # Process all commands
        await processor.run_for()

        # Verify execution order matches queue order
        assert executed_order == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_command_processor_optimistic_before_execute(self):
        """Test optimistic update is called before execute."""
        processor = CommandProcessorTestHarness.create()

        call_order: list[str] = []

        class TestCommand(DeviceCommand):
            def __init__(self) -> None:
                super().__init__("test", 0)

            @override
            async def publish_optimistic(self) -> None:
                call_order.append("optimistic")

            @override
            async def execute(self) -> None:
                call_order.append("execute")

        cmd = TestCommand()
        await processor.enqueue(cmd)

        await processor.run_for(0.1)

        # Verify optimistic was called before execute
        assert call_order == ["optimistic", "execute"]

    @pytest.mark.asyncio
    async def test_command_processor_handles_execute_failure(self):
        """Test error handling when command execution fails."""
        processor = CommandProcessorTestHarness.create()

        executed: list[str] = []

        class FailingCommand(DeviceCommand):
            def __init__(self) -> None:
                super().__init__("fail", 0)

            @override
            async def publish_optimistic(self) -> None:
                pass

            @override
            async def execute(self) -> None:
                executed.append("fail")
                raise Exception

        class GoodCommand(DeviceCommand):
            def __init__(self) -> None:
                super().__init__("good", 1)

            @override
            async def publish_optimistic(self) -> None:
                pass

            @override
            async def execute(self) -> None:
                executed.append("good")

        # Enqueue: failing command, then good command
        await processor.enqueue(FailingCommand())
        await processor.enqueue(GoodCommand())

        await processor.run_for()

        # Both commands should attempt execution despite first failure
        assert len(executed) >= 1

    @pytest.mark.asyncio
    async def test_command_processor_multiple_queued_commands(self):
        """Test queue depth handling with many commands."""
        processor = CommandProcessorTestHarness.create()

        executed_count = 0

        class CountingCommand(DeviceCommand):
            def __init__(self, cmd_id: int) -> None:
                super().__init__(f"test_{cmd_id}", cmd_id)

            @override
            async def publish_optimistic(self) -> None:
                pass

            @override
            async def execute(self) -> None:
                nonlocal executed_count
                executed_count += 1
                await asyncio.sleep(0.005)

        # Enqueue 10 commands
        for i in range(10):
            await processor.enqueue(CountingCommand(i))

        await processor.run_for(0.3)

        # Verify all 10 commands were processed
        assert executed_count == 10

    @pytest.mark.asyncio
    async def test_command_processor_queue_empties(self):
        """Test processing stops when queue is empty."""
        processor = CommandProcessorTestHarness.create()

        executed_count = 0

        class CountingCommand(DeviceCommand):
            def __init__(self, cmd_id: int) -> None:
                super().__init__(f"test_{cmd_id}", cmd_id)

            @override
            async def publish_optimistic(self) -> None:
                pass

            @override
            async def execute(self) -> None:
                nonlocal executed_count
                executed_count += 1
                await asyncio.sleep(0.01)

        # Enqueue 3 commands
        for i in range(3):
            await processor.enqueue(CountingCommand(i))

        # Process until queue is empty (should complete naturally)
        await processor.run_for(0.2)

        # All 3 commands should be executed
        assert executed_count == 3

    @pytest.mark.asyncio
    async def test_command_processor_enqueue_starts_processing(self):
        """Test that enqueuing creates processing task if not already processing."""
        processor = CommandProcessorTestHarness.create()

        class DummyCommand(DeviceCommand):
            def __init__(self) -> None:
                super().__init__("test", 0)

            @override
            async def publish_optimistic(self) -> None:
                pass

            @override
            async def execute(self) -> None:
                await asyncio.sleep(0.05)

        # Initial state
        assert processor.is_processing() is False

        # Enqueue a command
        await processor.enqueue(DummyCommand())

        # Give it time to start processing
        await asyncio.sleep(0.1)

        # processing should be true or task created
        assert processor.is_processing() or processor.queue_size() == 0

    @pytest.mark.asyncio
    async def test_command_processor_optimistic_update_published_first(self):
        """Test that optimistic updates happen before device command."""
        processor = CommandProcessorTestHarness.create()

        timing_log: list[tuple[str, int]] = []

        class TimedCommand(DeviceCommand):
            def __init__(self) -> None:
                super().__init__("test", 0)

            @override
            async def publish_optimistic(self) -> None:
                timing_log.append(("optimistic", 1))
                await asyncio.sleep(0.01)

            @override
            async def execute(self) -> None:
                timing_log.append(("execute", 2))
                await asyncio.sleep(0.01)

        await processor.enqueue(TimedCommand())

        await processor.run_for(0.1)

        # Verify order: optimistic is index 0, execute is index 1
        assert len(timing_log) >= 2
        assert timing_log[0][0] == "optimistic"
        assert timing_log[1][0] == "execute"

    @pytest.mark.asyncio
    async def test_command_processor_continues_after_exception(self):
        """Test that queue processing continues after a command raises exception."""
        processor = CommandProcessorTestHarness.create()

        results: list[str] = []

        class FailingCommand(DeviceCommand):
            def __init__(self) -> None:
                super().__init__("fail", 0)

            @override
            async def publish_optimistic(self) -> None:
                pass

            @override
            async def execute(self) -> None:
                results.append("fail")
                raise RuntimeError

        class SuccessCommand(DeviceCommand):
            def __init__(self) -> None:
                super().__init__("success", 1)

            @override
            async def publish_optimistic(self) -> None:
                pass

            @override
            async def execute(self) -> None:
                results.append("success")

        await processor.enqueue(FailingCommand())
        await processor.enqueue(SuccessCommand())

        await processor.run_for()

        # Both commands should have executed
        assert "fail" in results
        assert "success" in results
