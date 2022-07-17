import json
import os
import queue
import socket
import subprocess
import sys
import threading
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union


MAGIC_STR = b"i3-ipc"
MAGIC_STR_LEN = len(MAGIC_STR)
PAYLOAD_LENGTH_LEN = 4
PAYLOAD_TYPE_LEN = 4
PAYLOAD_LENGTH_BEGIN = MAGIC_STR_LEN
PAYLOAD_LENGTH_END = PAYLOAD_LENGTH_BEGIN + PAYLOAD_LENGTH_LEN
PAYLOAD_TYPE_BEGIN = PAYLOAD_LENGTH_END
PAYLOAD_TYPE_END = PAYLOAD_TYPE_BEGIN + PAYLOAD_TYPE_LEN
HEADER_LEN = MAGIC_STR_LEN + PAYLOAD_LENGTH_LEN + PAYLOAD_TYPE_LEN


class SwayMessage(Enum):
    """Represents the types of Sway messages that can be dispatched."""
    RUN_COMMAND = 0
    GET_WORKSPACES = 1
    SUBSCRIBE = 2
    GET_OUTPUTS = 3
    GET_TREE = 4
    GET_MARKS = 5
    GET_BAR_CONFIG = 6
    GET_VERSION = 7
    GET_BINDING_MODES = 8
    GET_CONFIG = 9
    SEND_TICK = 10
    SYNC = 11
    GET_BINDING_STATE = 12
    GET_INPUTS = 100
    GET_SEATS = 101


class SwayEvent(Enum):
    """Represents the types of Sway events that can be subscribed to."""
    WORKSPACE = int("80000000", 16)
    MODE = int("80000002", 16)
    WINDOW = int("80000003", 16)
    BARCONFIG_UPDATE = int("80000004", 16)
    BINDING = int("80000005", 16)
    SHUTDOWN = int("80000006", 16)
    TICK = int("80000007", 16)
    BAR_STATE_UPDATE = int("80000014", 16)
    INPUT = int("80000015", 16)

    def __str__(self) -> str:
        """Convert the Sway event to its string representation.

        Returns:
            str: The string representation of the Sway event.
        """
        return self.name.lower()


SwayResPayload = Union[Dict[str, Any], List[Any]]
SwayResHandler = Callable[[SwayMessage, SwayResPayload], None]
SwayEventHandler = Callable[[SwayEvent, SwayResPayload], None]
SwayMessageQueue = queue.Queue[tuple[SwayMessage, str, SwayResHandler]]


def _do_nothing(*_) -> None:
    return


class SwayClient:
    _consumer_thread: Optional[threading.Thread]
    """Thread that consumes and sends Sway messages from the message queue."""

    _consumer_stop: Optional[threading.Event]
    """Thread event for stopping the consumer thread."""

    _event_thread: Optional[threading.Thread]
    """Thread that waits for and handles events from Sway."""

    _event_stop: Optional[threading.Event]
    """Thread event for stopping the event thread."""

    _message_queue: SwayMessageQueue
    """Queue of messages to be dispatched to Sway."""

    def __init__(self) -> None:
        """Initialize the Sway client.

        Initialize the Sway client and open a connection to Sway for sending
        messages.
        """
        self._message_queue = queue.Queue()
        self._consumer_stop = threading.Event()
        self._consumer_thread = threading.Thread(
            target=message_dispatch_worker,
            args=(self._message_queue, self._consumer_stop),
            daemon=True,
        )
        self._consumer_thread.start()

    def send(
        self,
        msg: SwayMessage,
        payload: str,
        res_handler: SwayResHandler = _do_nothing,
    ) -> None:
        """Send a message with the given payload to Sway via the IPC socket.

        Args:
            msg (SwayMessage): The message type to send.
            payload (str): The payload to send with the message.
            res_handler (SwayResHandler): The callable that is called when
                the response is received. The callable must be thread-safe.
        """
        self._message_queue.put((msg, payload, res_handler))

    def subscribe(
        self,
        events: list[SwayEvent],
        event_handler: SwayEventHandler,
    ) -> None:
        """Subscribe to the given events from Sway.

        When an event is received, the given event handler is called.

        Args:
            events (list[SwayEvent]): The list of events to subscribe to.
            event_handler (SwayEventHandler): The event handler that is called
                when an event is received.
        """
        self._event_stop = threading.Event()
        self._event_thread = threading.Thread(
            target=event_worker,
            args=(events, event_handler, self._event_stop),
            daemon=True,
        )
        self._event_thread.start()

    def unsubscribe(self):
        """Unsubscribe from receiving all events from Sway."""
        if self._event_stop:
            self._event_stop.set()
            self._event_stop = None

        self._event_thread = None

    def shutdown(self) -> None:
        """Shutdown the Sway client.

        No more messages will be dispatched to Sway through the client after it
        has been shutdown.
        """
        if self._consumer_stop:
            self._consumer_stop.set()
            self._consumer_stop = None

        self._consumer_thread = None

        self.unsubscribe()


def get_sway_socket_path() -> str:
    """Find and return the Sway socket path.

    Attemps to read the Sway socket path from the SWAYSOCK env var first. If
    not found in the SWAYSOCK env var, attempt to get the socket by calling
    `sway --get-socketpath`.

    Returns:
        str: The Sway socket path.

    Raises:
        RunTimeError: If the Sway socket path cannot be determined.
    """
    path = os.environ.get("SWAYSOCK")

    if path is None:
        proc = subprocess.run(
            ["sway", "--get-socketpath"],
            capture_output=True,
            text=True,
        )
        path = proc.stdout.strip()

    if path is None:
        raise RuntimeError("SWAYSOCK env var is not set")
    return path


def message_dispatch_worker(
    messages: SwayMessageQueue,
    stop_event: threading.Event,
) -> None:
    """Worker for dispatching messages to Sway from the given queue.

    This worker continuously reads messages from the SwayMessageQueue and
    dispatches them to Sway through a unix domain socket. Responses are handled
    by the res_handler callable provided with the message.

    Args:
        messages (SwayMessageQueue): The queue of messages to be dispatched.
        stop_event (thread.Event): When set, stop_event will stop the worker.
    """
    cmd_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    cmd_sock.connect(get_sway_socket_path())

    while True:
        # Set a timeout in order to stop reading from the message queue if the
        # thread is stopped.
        try:
            message, payload, res_handler = messages.get(block=True, timeout=1)
        except queue.Empty:
            # End the thread if the thread has been marked as stopped.
            if stop_event.is_set():
                return
            else:
                continue

        send_sway_msg(cmd_sock, message, payload)

        res_type, res_payload = recv_sway_msg(cmd_sock)
        if isinstance(res_type, SwayMessage):
            res_handler(res_type, res_payload)


def event_worker(
    events: list[SwayEvent],
    event_handler: SwayEventHandler,
    stop_event: threading.Event,
) -> None:
    """Worker for subscribing to Sway events.

    This worker continuously listens for events from Sway and calls the given
    event handler callable when events are received.

    Args:
        events (list[SwayEvent]): The list of Sway events to subscribe to.
        event_handler (SwayEventHandler): The callable that is called when Sway
            event is received. The callable must be thread safe.
        stop_event (thread.Event): When set, stop_event will stop the worker.
    """
    sub_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sub_sock.connect(get_sway_socket_path())

    # Set a timeout in order to stop reading from the socket if the thread is
    # stopped.
    sub_sock.settimeout(1)

    str_events = list(map(lambda e: str(e), events))
    send_sway_msg(sub_sock, SwayMessage.SUBSCRIBE, json.dumps(str_events))
    _, res_payload = recv_sway_msg(sub_sock)

    if not res_payload.get("success"):
        raise RuntimeError("Failed to subscribe to Sway events.")

    while True:
        try:
            event_type, event_payload = recv_sway_msg(sub_sock)
        except socket.timeout:
            # End the thread if the thread has been marked as stopped.
            if stop_event.is_set():
                return
            else:
                continue

        if isinstance(event_type, SwayEvent):
            event_handler(event_type, event_payload)


def send_sway_msg(sock: socket.socket, msg: SwayMessage, payload: str) -> None:
    """Send a Sway message through the given socket.

    Args:
        sock (socket.socket): The socket through which to send the message.
        msg (SwayMessage): The Sway message to be sent.
        payload (str): The payload to be sent along with the Sway message.
    """
    payload_length = len(payload)
    payload_type = msg.value

    # Encode and send the message
    data = MAGIC_STR
    data += payload_length.to_bytes(PAYLOAD_LENGTH_LEN, sys.byteorder)
    data += payload_type.to_bytes(PAYLOAD_TYPE_LEN, sys.byteorder)
    data += payload.encode()

    sock.sendall(data)


def recv_sway_msg(sock: socket.socket) -> tuple[SwayMessage | SwayEvent, dict]:
    """Receive a response to a Sway message from the given socket.

    Args:
        sock (socket.socket): The socket from which to receive the response.

    Returns:
        tuple[SwayMessage | SwayEvent, dict]: A tuple containing the type of
            response and a dictionary containing the response payload.

    Raises:
        RuntimeError: If the Sway response type cannot be determined.
    """
    # Receive the response header, which is always the same length
    recv_header = b""
    while len(recv_header) < HEADER_LEN:
        recv_header += sock.recv(HEADER_LEN-len(recv_header))

    # Pull the response payload length out of the response header
    recv_payload_len = int.from_bytes(
        recv_header[PAYLOAD_LENGTH_BEGIN:PAYLOAD_LENGTH_END],
        sys.byteorder,
    )

    # Pull the response payload type out of the response header
    recv_payload_type = int.from_bytes(
        recv_header[PAYLOAD_TYPE_BEGIN:PAYLOAD_TYPE_END],
        sys.byteorder,
    )

    # Receive response payload in full
    recv_payload = b""
    while len(recv_payload) < recv_payload_len:
        recv_payload += sock.recv(recv_payload_len-len(recv_payload))

    payload_type = None
    if any(i.value == recv_payload_type for i in SwayMessage):
        payload_type = SwayMessage(recv_payload_type)
    elif any(i.value == recv_payload_type for i in SwayEvent):
        payload_type = SwayEvent(recv_payload_type)
    else:
        raise RuntimeError(
            "Unexpected payload type received: {}".format(recv_payload_type)
        )

    return payload_type, json.loads(recv_payload)
