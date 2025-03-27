from hashy import get_bytes_md5, get_bytes_sha256, get_bytes_sha512

zero_md5 = "93b885adfe0da089cdf634904fd59f71"
zero_sha256 = "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d"
zero_sha512 = "b8244d028981d693af7b456af8efa4cad63d282e19ff14942c246e50d9351d22704a802a71c3580b6370de4ceb293c324a8423342557d4e5c38438f0e36910ee"

abe1_md5 = "ecfcf68c2eab18a750db426cebd352bf"
abe1_sha256 = "0663afdbff5f0572ee5b5950731d981e31e7c3a9b669ae5cca69363e5c4ff861"
abe1_sha512 = "2c5e4c145b810b16426f57b2f3f627c5c1a686b24f576f420570c46099e9b3d2b56663e55473a9e01dc504acbab17897c80c8312c91b54bc28db94e0985d5ff5"


def test_zero_byte():
    zero = b"\0"
    assert get_bytes_md5(zero) == zero_md5
    assert get_bytes_sha256(zero) == zero_sha256
    assert get_bytes_sha512(zero) == zero_sha512


def test_abe1_byte():
    abe1 = b"\xab\xe1"
    assert get_bytes_md5(abe1) == abe1_md5
    assert get_bytes_sha256(abe1) == abe1_sha256
    assert get_bytes_sha512(abe1) == abe1_sha512
