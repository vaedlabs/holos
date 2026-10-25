`fb374d419588a4632f3f557e76b4b70aebbca790` is OpenAI's `o200k_base.tiktoken`, unchanged,
saved under tiktoken's cache name (sha1 of its download URL). `tests/contract/conftest.py`
points `TIKTOKEN_CACHE_DIR` here so the size-rule test never downloads it (Plan Phase 2
exit: no test on push makes a network call). Source:
https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken
