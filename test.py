
from touch_setup import ssd
from lib.gui.core.tgui import Screen, ssd, display, touch
from wifi import Wifi
import lib.gui.fonts.font10 as font
from lib.gui.core.colors import *
import urequests
from secrets import ADHOC_HOST

wri = CWriter(ssd, font, GREEN, BLACK, verbose=False)

class MyScreen(Screen):
    def __init__(self):
        super().__init__()

    def after_open(self):
        fn = "tokyo_l.bin"  # Image created by`img_cvt.py`
        # The following line is required if a 4-bit driver is in use
        # ssd.greyscale(True)
        with open(fn, "rb") as f:
            _ = f.read(4)  # Read and discard rows and cols
            f.readinto(ssd.mvb)  # Read the image into the frame buffer

class MyScreenDownload(Screen):
    def __init__(self):
        super().__init__()

    def after_open(self):
        host = f"http://{ADHOC_HOST}"
        response = None
        try:
            print(f"Downloading image from {host}")
            response = urequests.get(host)
            raw = response.raw
            _ = raw.read(4)  # Read and discard rows and cols
            raw.readinto(ssd.mvb)  # Read the image into the frame buffer
            print("Downloaded image into frame buffer")
        except Exception as e:
            print(f"Failed: {e}")
        finally:
            if response is not None:
                response.close()


# Screen.change(MyScreen)

wifi = Wifi()
ipAddr = wifi.connect()

display.print_left(wri, 10, 10, f"IP Address: {ipAddr}")
ssd.show()

print("hello")

Screen.change(MyScreenDownload)


# host = f"http://{ADHOC_HOST}"

# response = None
# try:
#     response = urequests.get(host)
#     txt = response.text
#     print(txt)
# except Exception as e:
#     print(f"Failed: {e}")
# finally:
#     if response is not None:
#         response.close()
