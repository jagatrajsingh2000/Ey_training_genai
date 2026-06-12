import json
import os
import random
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


DEFAULT_QUEUE_NAME = "payments"
MAX_DELIVERY_COUNT = 3


class PaymentRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount in GBP")
    currency: str = "GBP"
    account_id: str
    reference: str | None = None
    force_failure: bool = False


@dataclass
class PaymentMessage:
    message_id: str
    body: dict[str, Any]
    delivery_count: int


def serialize_payment(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"))


def deserialize_payment(payload: str | bytes) -> dict[str, Any]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    return json.loads(payload)


def service_bus_message_to_payment(message) -> PaymentMessage:
    body = b"".join(bytes(part) for part in message.body)
    return PaymentMessage(
        message_id=str(message.message_id),
        body=deserialize_payment(body),
        delivery_count=int(getattr(message, "delivery_count", 0) or 0),
    )


class AzureServiceBusBroker:
    def __init__(self, connection_string: str, queue_name: str = DEFAULT_QUEUE_NAME):
        try:
            from azure.servicebus import ServiceBusClient, ServiceBusMessage
            from azure.servicebus import ServiceBusSubQueue
        except ImportError as exc:
            raise RuntimeError(
                "azure-servicebus is not installed. Run pip install -r requirements.txt."
            ) from exc

        self.connection_string = connection_string
        self.queue_name = queue_name
        self.service_bus_client = ServiceBusClient
        self.service_bus_message = ServiceBusMessage
        self.service_bus_sub_queue = ServiceBusSubQueue

    def publish(self, payload: dict[str, Any]) -> str:
        message_id = str(uuid.uuid4())
        message = self.service_bus_message(
            serialize_payment(payload),
            message_id=message_id,
            content_type="application/json",
        )
        with self.service_bus_client.from_connection_string(
            self.connection_string
        ) as client:
            with client.get_queue_sender(self.queue_name) as sender:
                sender.send_messages(message)
        return message_id

    async def process_one(self) -> dict[str, Any]:
        with self.service_bus_client.from_connection_string(
            self.connection_string
        ) as client:
            with client.get_queue_receiver(
                self.queue_name,
                max_wait_time=5,
            ) as receiver:
                messages = receiver.receive_messages(
                    max_message_count=1,
                    max_wait_time=5,
                )
                if not messages:
                    return {"status": "queue_empty", "queue": self.queue_name}

                raw_message = messages[0]
                payment_message = service_bus_message_to_payment(raw_message)

                try:
                    result = await process_payment(payment_message)
                    self.complete(receiver, raw_message)
                    return {"acked": payment_message.message_id, "result": result}
                except Exception as exc:
                    if payment_message.delivery_count >= MAX_DELIVERY_COUNT:
                        self.dead_letter(receiver, raw_message, str(exc))
                        return {
                            "dead_lettered": payment_message.message_id,
                            "reason": str(exc),
                        }

                    self.abandon(receiver, raw_message)
                    return {
                        "nacked": payment_message.message_id,
                        "attempt": payment_message.delivery_count,
                        "reason": str(exc),
                    }

    def complete(self, receiver, message) -> None:
        receiver.complete_message(message)

    def abandon(self, receiver, message) -> None:
        receiver.abandon_message(message)

    def dead_letter(self, receiver, message, reason: str) -> None:
        receiver.dead_letter_message(
            message,
            reason="payment_processing_failed",
            error_description=reason[:4096],
        )

    def peek_dlq(self, limit: int) -> list[PaymentMessage]:
        with self.service_bus_client.from_connection_string(
            self.connection_string
        ) as client:
            with client.get_queue_receiver(
                self.queue_name,
                sub_queue=self.service_bus_sub_queue.DEAD_LETTER,
                max_wait_time=5,
            ) as receiver:
                messages = receiver.peek_messages(max_message_count=limit)
                return [service_bus_message_to_payment(message) for message in messages]

    def replay_dlq(self, limit: int) -> list[str]:
        replayed = []
        with self.service_bus_client.from_connection_string(
            self.connection_string
        ) as client:
            with client.get_queue_sender(self.queue_name) as sender:
                with client.get_queue_receiver(
                    self.queue_name,
                    sub_queue=self.service_bus_sub_queue.DEAD_LETTER,
                    max_wait_time=5,
                ) as receiver:
                    messages = receiver.receive_messages(
                        max_message_count=limit,
                        max_wait_time=5,
                    )
                    for message in messages:
                        payment_message = service_bus_message_to_payment(message)
                        replay_message_id = str(uuid.uuid4())
                        sender.send_messages(
                            self.service_bus_message(
                                serialize_payment(payment_message.body),
                                message_id=replay_message_id,
                                content_type="application/json",
                            )
                        )
                        receiver.complete_message(message)
                        replayed.append(replay_message_id)
        return replayed

    def check_connection(self) -> None:
        with self.service_bus_client.from_connection_string(
            self.connection_string
        ) as client:
            with client.get_queue_receiver(self.queue_name, max_wait_time=1):
                return None


def create_broker() -> AzureServiceBusBroker:
    connection_string = os.getenv("SB_CONN_STR")
    if not connection_string:
        raise RuntimeError("Set SB_CONN_STR before using Azure Service Bus endpoints.")
    queue_name = os.getenv("SB_QUEUE_NAME", DEFAULT_QUEUE_NAME)
    return AzureServiceBusBroker(connection_string, queue_name)


async def process_payment(message: PaymentMessage) -> dict[str, str]:
    if message.body.get("force_failure"):
        raise ValueError(f"Forced processor failure for {message.body.get('account_id')}")
    if random.random() < 0.2:
        raise ValueError(f"Fraud check timeout for {message.body.get('account_id')}")
    return {"processed_id": str(uuid.uuid4()), "status": "settled"}


def broker_or_503() -> AzureServiceBusBroker:
    try:
        return create_broker()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


app = FastAPI(title="EY Payment Azure Service Bus API", version="2.0.0")


@app.post("/payments", status_code=202)
async def enqueue_payment(payment: PaymentRequest):
    broker = broker_or_503()
    message_id = broker.publish(payment.model_dump())
    return {
        "message_id": message_id,
        "status": "queued",
        "queue": broker.queue_name,
    }


@app.get("/payments/worker")
async def process_one_payment():
    broker = broker_or_503()
    return await broker.process_one()


@app.get("/health/live")
async def liveness():
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness():
    checks = {"db": "ok"}

    try:
        broker = create_broker()
        broker.check_connection()
        checks["mq"] = "ok"
        checks["queue"] = broker.queue_name
    except Exception as exc:
        checks["mq"] = f"error: {exc}"

    all_ok = checks["mq"] == "ok"
    return JSONResponse(
        content={"status": "ready" if all_ok else "not_ready", **checks},
        status_code=200 if all_ok else 503,
    )


@app.get("/admin/dlq")
async def inspect_dlq(limit: int = Query(default=10, ge=1, le=50)):
    broker = broker_or_503()
    messages = broker.peek_dlq(limit)
    return {
        "queue": broker.queue_name,
        "messages": [
            {
                "id": message.message_id,
                "body": message.body,
                "delivery_count": message.delivery_count,
            }
            for message in messages
        ],
    }


@app.post("/admin/dlq/retry")
async def replay_dlq(limit: int = Query(default=5, ge=1, le=20)):
    broker = broker_or_503()
    replayed = broker.replay_dlq(limit)
    return {
        "queue": broker.queue_name,
        "replayed": len(replayed),
        "message_ids": replayed,
    }
