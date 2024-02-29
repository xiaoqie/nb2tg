#!/bin/sh

# apk add gcc ffmpeg-dev python3-dev linux-headers libc-dev
pip install aiohttp imageio av nonebot-adapter-onebot nonebot-adapter-telegram nonebot-plugin-localstore nonebot2
python patch.py
python bot.py

