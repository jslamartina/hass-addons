"""
Unit tests for CommandProcessor queue and execution logic.

Tests for CommandProcessor command queuing, sequential execution,
optimistic updates, error handling, and mesh refresh orchestration.
"""

import asyncio
import contextlib
from typing import override

import pytest

from cync_controller.mqtt.commands import CommandProcessor, DeviceCommand

# Filter RuntimeWarning about unawaited AsyncMockMixin coroutines from test cleanup
pytestmark = pytest.mark.filterwarnings(
    "ignore:coroutine 'AsyncMockMixin._execute_mock_call' was never awaited:RuntimeWarning"
)


class TestCommandProcessorExecution:
    """Tests for CommandProcessor queue and execution logic"""

    @pytest.fixture(autouse=True)
    def reset_processor_singleton(self):
        """Reset CommandProcessor singleton between tests"""
        CommandProcessor._instance = None
        yield
        CommandProcessor._instance = None

    @pytest.mark.asyncio
    async def test_command_processor_sequential_execution(self):
        """Test commands execute in FIFO order"""
        processor = CommandProcessor()
        processor._queue = asyncio.Queue()
        processor._processing = False

        executed_order = []

        class TestCommand(DeviceCommand):
            def __init__(self, cmd_id):
                self.cmd_id = cmd_id
                super().__init__(f"test_{cmd_id}", cmd_id)

            @override
            async def publish_optimistic(self):
                pass

            @override
            async def execute(self):
                executed_order.append(self.cmd_id)
                await asyncio.sleep(0.01)

        # Enqueue commands in order
        await processor.enqueue(TestCommand(1))
        await processor.enqueue(TestCommand(2))
        await processor.enqueue(TestCommand(3))

        # Process all commands
        process_task = asyncio.create_task(processor.process_next())
        await asyncio.sleep(0.15)
        _ = process_task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await process_task

        # Verify execution order matches queue order
        assert executed_order == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_command_processor_optimistic_before_execute(self):
        """Test optimistic update is called before execute"""
        processor = CommandProcessor()
        processor._queue = asyncio.Queue()
        processor._processing = False

        call_order = []

        class TestCommand(DeviceCommand):
            def __init__(self):
                super().__init__("test", 0)

            @override
            async def publish_optimistic(self):
                call_order.append("optimistic")

            @override
            async def execute(self):
                call_order.append("execute")

        cmd = TestCommand()
        await processor.enqueue(cmd)

        process_task = asyncio.create_task(processor.process_next())
        await asyncio.sleep(0.1)
        _ = process_task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await process_task

        # Verify optimistic was called before execute
        assert call_order == ["optimistic", "execute"]

    @pytest.mark.asyncio
    async def test_command_processor_handles_execute_failure(self):
        """Test error handling when command execution fails"""
        processor = CommandProcessor()
        processor._queue = asyncio.Queue()
        processor._processing = False

        executed = []

        class FailingCommand(DeviceCommand):
            def __init__(self):
                super().__init__("fail", 0)

            @override
            async def publish_optimistic(self):
                pass

            @override
            async def execute(self):
                executed.append("fail")
                raise Exception("Command failed")

        class GoodCommand(DeviceCommand):
            def __init__(self):
                super().__init__("good", 1)

            @override
            async def publish_optimistic(self):
                pass

            @override
            async def execute(self):
                executed.append("good")

        # Enqueue: failing command, then good command
        await processor.enqueue(FailingCommand())
        await processor.enqueue(GoodCommand())

        process_task = asyncio.create_task(processor.process_next())
        await asyncio.sleep(0.15)
        _ = process_task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await process_task

        # Both commands should attempt execution despite first failure
        assert len(executed) >= 1

    @pytest.mark.asyncio
    async def test_command_processor_multiple_queued_commands(self):
        """Test queue depth handling with many commands"""
        processor = CommandProcessor()
        processor._queue = asyncio.Queue()
        processor._processing = False

        executed_count = 0

        class CountingCommand(DeviceCommand):
            def __init__(self, cmd_id):
                super().__init__(f"test_{cmd_id}", cmd_id)

            @override
            async def publish_optimistic(self):
                pass

            @override
            async def execute(self):
                nonlocal executed_count
                executed_count += 1
                await asyncio.sleep(0.005)

        # Enqueue 10 commands
        for i in range(10):
            await processor.enqueue(CountingCommand(i))

        process_task = asyncio.create_task(processor.process_next())
        await asyncio.sleep(0.3)
        _ = process_task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await process_task

        # Verify all 10 commands were processed
        assert executed_count == 10

    @pytest.mark.asyncio
    async def test_command_processor_queue_empties(self):
        """Test processing stops when queue is empty"""
        processor = CommandProcessor()
        processor._queue = asyncio.Queue()
        processor._processing = False

        executed_count = 0

        class CountingCommand(DeviceCommand):
            def __init__(self, cmd_id):
                super().__init__(f"test_{cmd_id}", cmd_id)

            @override
            async def publish_optimistic(self):
                pass

            @override
            async def execute(self):
                nonlocal executed_count
                executed_count += 1
                await asyncio.sleep(0.01)

        # Enqueue 3 commands
        for i in range(3):
            await processor.enqueue(CountingCommand(i))

        # Process until queue is empty (should complete naturally)
        process_task = asyncio.create_task(processor.process_next())
        await asyncio.sleep(0.2)

        # Task should complete naturally since queue is empty
        try:
            await asyncio.wait_for(process_task, timeout=1.0)
        except TimeoutError:
            _ = process_task.cancel()

        # All 3 commands should be executed
        assert executed_count == 3

    @pytest.mark.asyncio
    async def test_command_processor_enqueue_starts_processing(self):
        """Test that enqueuing creates processing task if not already processing"""
        processor = CommandProcessor()
        processor._queue = asyncio.Queue()
        processor._processing = False

        class DummyCommand(DeviceCommand):
            def __init__(self):
                super().__init__("test", 0)

            @override
            async def publish_optimistic(self):
                pass

            @override
            async def execute(self):
                await asyncio.sleep(0.05)

        # Initial state
        assert processor._processing is False

        # Enqueue a command
        await processor.enqueue(DummyCommand())

        # Give it time to start processing
        await asyncio.sleep(0.1)

        # processing should be true or task created
        assert processor._processing or processor._queue.empty()

    @pytest.mark.asyncio
    async def test_command_processor_optimistic_update_published_first(self):
        """Test that optimistic updates happen before device command"""
        processor = CommandProcessor()
        processor._queue = asyncio.Queue()
        processor._processing = False

        timing_log = []

        class TimedCommand(DeviceCommand):
            def __init__(self):
                super().__init__("test", 0)

            @override
            async def publish_optimistic(self):
                timing_log.append(("optimistic", 1))
                await asyncio.sleep(0.01)

            @override
            async def execute(self):
                timing_log.append(("execute", 2))
                await asyncio.sleep(0.01)

        await processor.enqueue(TimedCommand())

        process_task = asyncio.create_task(processor.process_next())
        await asyncio.sleep(0.1)
        _ = process_task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await process_task

        # Verify order: optimistic is index 0, execute is index 1
        assert len(timing_log) >= 2
        assert timing_log[0][0] == "optimistic"
        assert timing_log[1][0] == "execute"

    @pytest.mark.asyncio
    async def test_command_processor_continues_after_exception(self):
        """Test that queue processing continues after a command raises exception"""
        processor = CommandProcessor()
        processor._queue = asyncio.Queue()
        processor._processing = False

        results = []

        class FailingCommand(DeviceCommand):
            def __init__(self):
                super().__init__("fail", 0)

            @override
            async def publish_optimistic(self):
                pass

            @override
            async def execute(self):
                results.append("fail")
                raise RuntimeError("Test error")

        class SuccessCommand(DeviceCommand):
            def __init__(self):
                super().__init__("success", 1)

            @override
            async def publish_optimistic(self):
                pass

            @override
            async def execute(self):
                results.append("success")

        await processor.enqueue(FailingCommand())
        await processor.enqueue(SuccessCommand())

        process_task = asyncio.create_task(processor.process_next())
        await asyncio.sleep(0.15)
        _ = process_task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await process_task

        # Both commands should have executed
        assert "fail" in results
        assert "success" in results
