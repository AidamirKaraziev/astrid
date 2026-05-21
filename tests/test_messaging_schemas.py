from datetime import date
from uuid import uuid4

from astra.messaging.schemas import TaskMessage, TaskType


def test_task_message_roundtrip() -> None:
    msg = TaskMessage(
        type=TaskType.PREDICTION_GENERATE,
        user_id=uuid4(),
        prediction_date=date(2026, 5, 18),
    )
    raw = msg.model_dump_json()
    restored = TaskMessage.model_validate_json(raw)
    assert restored.type == TaskType.PREDICTION_GENERATE
    assert restored.prediction_date == date(2026, 5, 18)
