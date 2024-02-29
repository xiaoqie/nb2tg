from pathlib import Path

path = Path("/usr/local/lib/python3.11/site-packages/nonebot/adapters/telegram/bot.py")
code = path.read_text()
code = code.replace('offset=sum(map(len, message[:i])),', 
                    'offset=sum(len(str(m).encode("utf-16-le")) // 2 for m in message[:i]),')
code = code.replace('length=len(entity.data["text"]),',
                    'length=len(entity.data["text"].encode("utf-16-le")) // 2,')
path.write_text(code)
