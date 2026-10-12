"""Zero-Copy Single-Producer Single-Consumer (SPSC) Circular Ring Buffer using Shared Memory."""

import ctypes
import math
import struct
from multiprocessing import shared_memory
from typing import Optional, Union

# Cache-line alignment padding (64 bytes) to avoid CPU false sharing
CACHE_LINE_SIZE = 64
HEADER_RESERVED_SIZE = 256  # 4 cache lines for head, tail, capacity, slot_size

# Offsets inside shared memory
OFFSET_HEAD = 0           # Consumer read index (uint64)
OFFSET_TAIL = 64          # Producer write index (uint64)
OFFSET_CAPACITY = 128     # Total slot count (power of 2)
OFFSET_SLOT_SIZE = 136    # Fixed byte size of each slot
OFFSET_DATA = HEADER_RESERVED_SIZE


class SharedRingBuffer:
    """Zero-copy lockless SPSC circular ring buffer backed by shared memory."""

    __slots__ = (
        "name",
        "capacity",
        "slot_size",
        "mask",
        "shm",
        "buf",
        "is_creator",
        "_head_view",
        "_tail_view",
    )

    def __init__(
        self,
        name: str,
        capacity: int = 1024,
        slot_size: int = 128,
        create: bool = True,
    ) -> None:
        self.name: str = name
        self.is_creator: bool = create

        if create:
            # Round capacity up to next power of 2 for bitwise masking
            if capacity < 2 or (capacity & (capacity - 1)) != 0:
                capacity = 1 << math.ceil(math.log2(max(capacity, 2)))

            self.capacity = capacity
            self.slot_size = slot_size
            self.mask = capacity - 1

            total_bytes = HEADER_RESERVED_SIZE + (self.capacity * self.slot_size)
            self.shm = shared_memory.SharedMemory(name=name, create=True, size=total_bytes)
            self.buf = self.shm.buf

            # Initialize header fields
            struct.pack_into("<Q", self.buf, OFFSET_HEAD, 0)
            struct.pack_into("<Q", self.buf, OFFSET_TAIL, 0)
            struct.pack_into("<Q", self.buf, OFFSET_CAPACITY, self.capacity)
            struct.pack_into("<Q", self.buf, OFFSET_SLOT_SIZE, self.slot_size)
        else:
            self.shm = shared_memory.SharedMemory(name=name, create=False)
            self.buf = self.shm.buf

            self.capacity = struct.unpack_from("<Q", self.buf, OFFSET_CAPACITY)[0]
            self.slot_size = struct.unpack_from("<Q", self.buf, OFFSET_SLOT_SIZE)[0]
            self.mask = self.capacity - 1

    @property
    def head(self) -> int:
        """Current consumer read sequence."""
        return struct.unpack_from("<Q", self.buf, OFFSET_HEAD)[0]

    @head.setter
    def head(self, val: int) -> None:
        struct.pack_into("<Q", self.buf, OFFSET_HEAD, val)

    @property
    def tail(self) -> int:
        """Current producer write sequence."""
        return struct.unpack_from("<Q", self.buf, OFFSET_TAIL)[0]

    @tail.setter
    def tail(self, val: int) -> None:
        struct.pack_into("<Q", self.buf, OFFSET_TAIL, val)

    def size(self) -> int:
        """Returns the number of unconsumed slots currently in the buffer."""
        return self.tail - self.head

    def is_empty(self) -> bool:
        """Returns True if there are no pending messages to consume."""
        return self.head >= self.tail

    def is_full(self) -> bool:
        """Returns True if buffer has reached capacity."""
        return (self.tail - self.head) >= self.capacity

    def acquire_write_slot(self) -> Optional[memoryview]:
        """Producer: Claims the next slot in the ring buffer without copying memory.

        Returns a memoryview slicing into the shared memory slot, or None if full.
        """
        curr_head = self.head
        curr_tail = self.tail

        if (curr_tail - curr_head) >= self.capacity:
            return None  # Ring buffer is saturated

        slot_idx = curr_tail & self.mask
        start_offset = OFFSET_DATA + (slot_idx * self.slot_size)
        return self.buf[start_offset : start_offset + self.slot_size]

    def commit_write(self) -> int:
        """Producer: Commits the written slot by publishing the updated tail sequence."""
        new_tail = self.tail + 1
        self.tail = new_tail
        return new_tail

    def peek_read_slot(self) -> Optional[memoryview]:
        """Consumer: Returns a zero-copy memoryview to the unconsumed head slot, or None."""
        curr_head = self.head
        curr_tail = self.tail

        if curr_head >= curr_tail:
            return None  # No pending messages

        slot_idx = curr_head & self.mask
        start_offset = OFFSET_DATA + (slot_idx * self.slot_size)
        return self.buf[start_offset : start_offset + self.slot_size]

    def advance_read(self) -> int:
        """Consumer: Advances the read head sequence after consuming the message."""
        new_head = self.head + 1
        self.head = new_head
        return new_head

    def __enter__(self) -> "SharedRingBuffer":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        """Releases memoryview slices and closes shared memory handles."""
        import gc

        if self.buf is not None:
            try:
                self.buf.release()
            except Exception:
                pass
            self.buf = None

        gc.collect()

        try:
            self.shm.close()
        except (BufferError, Exception):
            pass

        if self.is_creator:
            try:
                self.shm.unlink()
            except (FileNotFoundError, Exception):
                pass
