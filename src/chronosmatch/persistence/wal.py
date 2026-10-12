"""High-speed binary Write-Ahead Log (WAL) for auditability and deterministic replay."""

import ctypes
import os
import struct
from typing import Iterator, Optional, Tuple, Union

from chronosmatch.protocol.messages import (
    CancelOrderMsg,
    ExecutionReportMsg,
    NewOrderMsg,
)
from chronosmatch.protocol.types import MsgType

WAL_MAGIC = 0x57414C31  # "WAL1"
RECORD_HEADER_STRUCT = struct.Struct("<IBBHI")  # magic (4), msg_type (1), pad (1), length (2), seq_no (4)
HEADER_SIZE = RECORD_HEADER_STRUCT.size


class WriteAheadLog:
    """Append-only binary journal for zero-copy state persistence and replay."""

    __slots__ = ("file_path", "_file", "_seq_no")

    def __init__(self, file_path: str, mode: str = "a+b") -> None:
        self.file_path = file_path
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        self._file = open(file_path, mode, buffering=64 * 1024)  # 64 KB write buffer
        self._seq_no = 0

    def append(self, msg: Union[NewOrderMsg, CancelOrderMsg, ExecutionReportMsg]) -> int:
        """Appends a binary message directly to the WAL."""
        msg_bytes = bytes(msg)
        length = len(msg_bytes)
        self._seq_no += 1

        header = RECORD_HEADER_STRUCT.pack(WAL_MAGIC, msg.msg_type, 0, length, self._seq_no)
        self._file.write(header)
        self._file.write(msg_bytes)
        return self._seq_no

    def flush(self) -> None:
        """Flushes in-memory stream buffers to persistent disk."""
        self._file.flush()
        os.fsync(self._file.fileno())

    def close(self) -> None:
        """Flushes and closes the log file."""
        if self._file and not self._file.closed:
            self._file.flush()
            self._file.close()

    @classmethod
    def read_records(cls, file_path: str) -> Iterator[Tuple[int, int, bytes]]:
        """Yields (seq_no, msg_type, raw_bytes) for every record in the WAL."""
        if not os.path.exists(file_path):
            return

        with open(file_path, "rb") as f:
            while True:
                hdr_bytes = f.read(HEADER_SIZE)
                if len(hdr_bytes) < HEADER_SIZE:
                    break

                magic, msg_type, _, length, seq_no = RECORD_HEADER_STRUCT.unpack(hdr_bytes)
                if magic != WAL_MAGIC:
                    raise ValueError(f"Corrupt WAL magic {hex(magic)} at seq {seq_no}")

                payload = f.read(length)
                if len(payload) < length:
                    raise ValueError(f"Truncated WAL record payload at seq {seq_no}")

                yield seq_no, msg_type, payload
