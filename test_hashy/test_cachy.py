from datetime import timedelta
from hashy import cachy

cache_life = timedelta(days=1)


def test_a_cachy_zero_life():
    @cachy(timedelta(seconds=0))
    def func(p):
        return p

    assert func(1) == 1
    assert func(1) == 1


def test_cachy_simple():
    @cachy(cache_life)
    def func(p):
        return p

    assert func(1) == 1
    assert func(1) == 1


def test_cachy_dict():
    @cachy(cache_life)
    def func(p):
        return p

    data = {"a": 1, "b": 2}
    assert func(data) == data
    assert func(data) == data


def test_cachy_complex():
    @cachy(cache_life)
    def func(a, b, c):
        return [a, b, c]

    data = {"a": 1, "b": 2}
    assert func(data, data, c=data) == [data, data, data]
