import hashlib

def identicon(n: int):
    white = "⬜"
    blocks = "🟥🟧🟨🟩🟦🟪🟫⬛"
    div, mod = divmod(int(hashlib.md5(str(n).encode()).hexdigest(), 16), 2)
    icon = ""
    for i in range(4):
        icon += str(mod)
        div, mod = divmod(div, 2)
    div, mod = divmod(div, len(blocks))
    block = blocks[mod]
    icon = icon.replace("0", white)
    icon = icon.replace("1", block)
    return icon
