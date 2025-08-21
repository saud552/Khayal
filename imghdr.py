# Lightweight shim for Python 3.13 where stdlib imghdr was removed
# Provides basic imghdr.what(filename, h=None) used by some libraries

_MAGIC = [
    (b"\xff\xd8\xff", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"BM", "bmp"),
    (b"RIFF", "webp"),  # Needs further check but acceptable as shim
]

def what(file, h=None):
    try:
        if h is None:
            with open(file, 'rb') as f:
                head = f.read(16)
        else:
            head = h
        for magic, name in _MAGIC:
            if head.startswith(magic):
                return name
    except Exception:
        pass
    return None