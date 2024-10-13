from pathlib import Path

path = Path("/usr/local/lib/python3.11/site-packages/nonebot/adapters/telegram/message.py")
code = path.read_text()
code = code.replace('offset=sum(map(len, entities[:i])),', 
                    'offset=sum(len(str(m).encode("utf-16-le")) // 2 for m in entities[:i]),')
code = code.replace('length=len(entity.data["text"]),',
                    'length=len(entity.data["text"].encode("utf-16-le")) // 2,')
path.write_text(code)

path = Path("/usr/local/lib/python3.11/site-packages/nonebot/adapters/telegram/model.py")
code = path.read_text()
code = code.replace('media: str\n', 'media: str | bytes\n')
path.write_text(code)
