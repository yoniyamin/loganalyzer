import httpx

tests = [
    ("max_tokens", {"max_tokens": 50}),
    ("maxTokens", {"maxTokens": 50}),
    ("reasoning_off", {"reasoning": "off"}),
    ("baseline", {}),
]
for name, extra in tests:
    p = {"input": "Say OK", "temperature": 0, **extra}
    try:
        r = httpx.post("http://localhost:1234/api/v1/chat", json=p, timeout=60)
        print(name, r.status_code, r.text[:300].replace("\n", " "))
    except Exception as e:
        print(name, "ERR", e)
