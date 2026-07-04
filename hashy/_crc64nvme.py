"""
CRC-64/NVME implementation with a hashlib-style interface.

CRC-64/NVME is the CRC used by the NVMe specification and by AWS S3 (as
"CRC64NVME") for object integrity checking. Parameters (per the reveng CRC
catalogue): poly=0xad93d23594c93659, init=0xffffffffffffffff, refin=true,
refout=true, xorout=0xffffffffffffffff, check("123456789")=0xae8b14860a799888.

``Crc64Nvme`` mimics the small subset of the hashlib interface that
``_hash_core`` uses (no-arg constructor, ``update``, ``hexdigest``) so the
string/bytes/file helpers can treat it exactly like ``hashlib.sha256`` et al.
Pure Python and table-driven; fine for typical use, but much slower than
hashlib's C implementations on very large inputs.
"""

_XOR = 0xFFFFFFFFFFFFFFFF

# Bit-reversed (reflected) form of the CRC-64/NVME polynomial 0xad93d23594c93659.
_REFLECTED_POLY = 0x9A6C9329AC4BC9B5


def _make_table() -> list[int]:
    table = []
    for byte_value in range(256):
        crc = byte_value
        for _ in range(8):
            crc = ((crc >> 1) ^ _REFLECTED_POLY) if crc & 1 else (crc >> 1)
        table.append(crc)
    return table


_TABLE = _make_table()


class Crc64Nvme:
    """CRC-64/NVME with a minimal hashlib-like interface (update/hexdigest)."""

    def __init__(self) -> None:
        self._crc = _XOR  # init value

    def update(self, data: bytes) -> None:
        crc = self._crc
        table = _TABLE
        for byte_value in data:
            crc = table[(crc ^ byte_value) & 0xFF] ^ (crc >> 8)
        self._crc = crc

    def hexdigest(self) -> str:
        """Return the 16-character lower-case hex digest."""
        return format(self._crc ^ _XOR, "016x")
