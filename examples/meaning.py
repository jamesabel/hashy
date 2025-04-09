from hashy import get_dls_sha256

d = {"meaning": "life",
     "version": "0.0.1"}

print(get_dls_sha256(d))
