#!/usr/bin/env python
"""
Diagnose script to check if qrcode is available in the current Python environment.
Run this with the same Python that Gunicorn uses.
"""
import sys
import os

print("=" * 60)
print("QRCode Installation Check")
print("=" * 60)
print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")
print(f"Python path: {sys.path}")
print()

# Check for qrcode
try:
    import qrcode
    print("✅ qrcode module found")
    print(f"   Location: {qrcode.__file__}")
    print(f"   Version: {getattr(qrcode, '__version__', 'unknown')}")
except ImportError as e:
    print(f"❌ qrcode module NOT found: {e}")

print()

# Check for PIL/Pillow
try:
    from PIL import Image
    print("✅ PIL/Pillow module found")
    print(f"   Location: {Image.__file__}")
    try:
        import PIL
        print(f"   Version: {PIL.__version__}")
    except:
        pass
except ImportError as e:
    print(f"❌ PIL/Pillow module NOT found: {e}")

print()

# Try to actually generate a QR code
try:
    import qrcode
    from PIL import Image
    import io
    
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data("test")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    print("✅ QR code generation test: SUCCESS")
except Exception as e:
    print(f"❌ QR code generation test: FAILED - {e}")

print()
print("=" * 60)
print("To install qrcode, run:")
print("  pip install qrcode[pil]==7.4.2")
print("=" * 60)
