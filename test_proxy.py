import aiohttp, asyncio

async def test():
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get('https://api.telegram.org', proxy='http://127.0.0.1:1080', timeout=aiohttp.ClientTimeout(total=10))
            print(f"HTTP proxy OK: {r.status}")
            await r.release()
    except Exception as e:
        print(f"HTTP proxy failed: {e}")

    try:
        from python_socks.async_.asyncio import Proxy
        proxy = Proxy.from_url('socks5://127.0.0.1:1080')
        sock = await proxy.connect(dest_host='api.telegram.org', dest_port=443)
        sock.close()
        print("SOCKS5 proxy OK")
    except Exception as e:
        print(f"SOCKS5 proxy failed: {e}")

asyncio.run(test())
