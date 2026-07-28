import sys
print("Python:", sys.executable)
try:
    import win32com.client
    print("win32com OK")
except ImportError as e:
    print("win32com FAIL:", e)
try:
    from PIL import Image
    print("Pillow OK")
except ImportError as e:
    print("Pillow FAIL:", e)
