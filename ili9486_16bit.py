# ILI9486 nano-gui driver for ili9486 displays

# Copyright (c) Peter Hinch 2022-2024
# Released under the MIT license see LICENSE

# Much help provided by @brave-ulysses in this thread
# https://github.com/micropython/micropython/discussions/10404 for the special handling
# required by the Waveshare Pi HAT.

# This driver configures the chip in portrait mode with rotation performed in the driver.
# This is done to enable default values to be used for the Column Address Set and Page
# Address Set registers. This avoids having to use commands with multi-byte data values,
# which would necessitate special code for the Waveshare Pi HAT (see DRIVERS.md).

# ------
# adapted from https://github.com/peterhinch/micropython-touch/blob/master/drivers/ili94xx/ili9486.py
# Adds 16-bit RGB565 direct color mode

from time import sleep_ms
import gc
import framebuf
import asyncio
from lib.drivers.boolpalette import BoolPalette

# Portrait mode - direct 16-bit RGB565 color
@micropython.viper
def _lcopy_16bit(dest: ptr16, source: ptr16, length: int, invert_mask: int):
    # Direct copy with optional color inversion
    n: int = 0
    while length:
        dest[n] = source[n] ^ invert_mask
        n += 1
        length -= 1


# FB is in landscape mode, hence issue a column at a time to portrait mode hardware.
@micropython.viper
def _lscopy_16bit(dest: ptr16, source: ptr16, ch: int, invert_mask: int):
    col = ch & 0x1FF  # Unpack (viper 4 parameter limit)
    height = (ch >> 9) & 0x1FF
    wbytes = ch >> 19  # Width in bytes is width * 2
    # Direct copy with optional color inversion
    n = 0
    idx = col * 2  # 2 bytes per pixel
    while height:
        dest[n] = source[idx >> 1] ^ invert_mask
        n += 1
        idx += wbytes
        height -= 1


class ILI9486_16bit(framebuf.FrameBuffer):

    lut = bytearray(32)
    COLOR_INVERT = 0

    # Convert r, g, b in range 0-255 to a 16 bit RGB565 colour value
    # Stored in little-endian format for the hardware
    @classmethod
    def rgb(cls, r, g, b):
        return (r & 0xF8) | (g & 0xE0) >> 5 | (g & 0x1C) << 11 | (b & 0xF8) << 5

    # Transpose width & height for landscape mode
    def __init__(
        self, spi, cs, dc, rst, height=320, width=480, usd=False, mirror=False, init_spi=False
    ):
        self._spi = spi
        self._cs = cs
        self._dc = dc
        self._rst = rst
        self.lock_mode = False  # If set, user lock is passed to .do_refresh
        self.height = height  # Logical dimensions for GUIs
        self.width = width
        self._long = max(height, width)  # Physical dimensions of screen and aspect ratio
        self._short = min(height, width)
        self._spi_init = init_spi
        self.mode = framebuf.RGB565
        self.palette = BoolPalette(self.mode)
        gc.collect()
        # 16-bit RGB565: 2 bytes per pixel
        buf = bytearray(height * width * 2)
        self.mvb = memoryview(buf)
        super().__init__(buf, width, height, self.mode)  # Logical aspect ratio
        self._linebuf = bytearray(self._short * 2)

        # Hardware reset
        self._rst(0)
        sleep_ms(50)
        self._rst(1)
        sleep_ms(50)
        if self._spi_init:  # A callback was passed
            self._spi_init(spi)  # Bus may be shared
        self._lock = asyncio.Lock()
        # Send initialization commands

        self._wcmd(b"\x01")  # SWRESET Software reset
        sleep_ms(100)
        self._wcmd(b"\x11")  # sleep out
        sleep_ms(20)
        self._wcd(b"\x3a", b"\x55")  # interface pixel format
        # Normally use defaults. This allows it to work on the Waveshare board with a
        # shift register. If size is not 320x480 assume no shift register.
        # Default column address start == 0, end == 0x13F (319)
        if self._short != 320:  # Not the Waveshare board: no shift register
            self._wcd(b"\x2a", int.to_bytes(self._short - 1, 4, "big"))
        # Default page address start == 0 end == 0x1DF (479)
        if self._long != 480:
            self._wcd(b"\x2b", int.to_bytes(self._long - 1, 4, "big"))  # SET_PAGE ht
        madctl = 0x48 if usd else 0x88
        if mirror:
            madctl ^= 0x80
        self._wcd(b"\x36", madctl.to_bytes(1, "big"))  # MADCTL: RGB portrait mode
        self._wcmd(b"\x11")  # sleep out
        self._wcmd(b"\x29")  # display on

    # Write a command.
    def _wcmd(self, command):
        self._dc(0)
        self._cs(0)
        self._spi.write(command)
        self._cs(1)

    # Write a command followed by a data arg.
    def _wcd(self, command, data):
        self._dc(0)
        self._cs(0)
        self._spi.write(command)
        self._cs(1)
        self._dc(1)
        self._cs(0)
        self._spi.write(data)
        self._cs(1)

    def show(self):  # Physical display is in portrait mode
        lb = self._linebuf
        buf = self.mvb
        if self._spi_init:  # A callback was passed
            self._spi_init(self._spi)  # Bus may be shared
        self._wcmd(b"\x2c")  # WRITE_RAM
        self._dc(1)
        self._cs(0)
        if self.width < self.height:  # Portrait
            wd = self.width
            ht = self.height
            for start in range(0, wd * ht * 2, wd * 2):  # For each line (16-bit pixels)
                _lcopy_16bit(lb, buf[start:], wd, self.COLOR_INVERT)
                self._spi.write(lb)
        else:  # Landscape
            width = self.width
            wd = width - 1
            cargs = (self.height << 9) + (width << 20)  # Viper 4-arg limit
            for col in range(width):  # For each column of landscape display
                _lscopy_16bit(lb, buf, wd - col + cargs, self.COLOR_INVERT)
                self._spi.write(lb)
        self._cs(1)

    def short_lock(self, v=None):
        if v is not None:
            self.lock_mode = v  # If set, user lock is passed to .do_refresh
        return self.lock_mode

    # nanogui apps typically call with no args. ugui and tgui pass split and
    # may pass a Lock depending on lock_mode
    async def do_refresh(self, split=4, elock=None):
        if elock is None:
            elock = asyncio.Lock()
        async with self._lock:
            lines, mod = divmod(self._long, split)  # Lines per segment
            if mod:
                raise ValueError("Invalid do_refresh arg.")
            lb = self._linebuf
            buf = self.mvb
            self._wcmd(b"\x2c")  # WRITE_RAM
            self._dc(1)
            if self.width < self.height:  # Portrait: write sets of rows
                wd = self.width
                line = 0
                for _ in range(split):  # For each segment
                    async with elock:
                        if self._spi_init:  # A callback was passed
                            self._spi_init(self._spi)  # Bus may be shared
                        self._cs(0)
                        for start in range(wd * line * 2, wd * (line + lines) * 2, wd * 2):  # For each line
                            _lcopy_16bit(lb, buf[start:], wd, self.COLOR_INVERT)
                            self._spi.write(lb)
                        line += lines
                        self._cs(1)  # Allow other tasks to use bus
                    await asyncio.sleep_ms(0)
            else:  # Landscape: write sets of cols.
                cargs = (self.height << 9) + (self.width << 20)  # Viper 4-arg limit
                sc = self.width - 1  # Start and end columns
                ec = sc - lines  # End column
                for _ in range(split):  # For each segment
                    async with elock:
                        if self._spi_init:  # A callback was passed
                            self._spi_init(self._spi)  # Bus may be shared
                        self._cs(0)
                        for col in range(sc, ec, -1):  # For each column of landscape display
                            _lscopy_16bit(lb, buf, col + cargs, self.COLOR_INVERT)
                            self._spi.write(lb)
                        sc -= lines
                        ec -= lines
                        self._cs(1)  # Allow other tasks to use bus
                    await asyncio.sleep_ms(0)
