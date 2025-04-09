from functools import cache
from hashy import cachy

@cache
def this_will_not_work(data: dict[str: int]) -> int:
    return sum(data.values())

@cachy()
def this_will_work(data: dict[str: int]) -> int:
    return sum(data.values())

d = {"a": 1, "b": 2, "c": 3}

result = this_will_work(d)
print(result)

result = this_will_not_work(d)
print(result)